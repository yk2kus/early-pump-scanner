#!/usr/bin/env python3
"""
Early Pump Scanner — external (all-coins) version.

Same 0-100 scoring as the TradingView 'Crypto Early Pump Scanner', but with NO
40-symbol limit: it scores EVERY coin in a data folder and ranks them.

Runs on local parquet (no exchange calls, no ban risk) so it works today and
proves the all-coins table. The scoring engine (score_df) is the reusable piece:
point it at live 5m klines later (on a clean IP / VPS, WebSocket-first) and it
behaves identically.

Descriptive, not predictive: a high score means many early-momentum conditions
are present now — not that the coin will pump. (We backtested this class; no edge.)

    python3 scanner.py                 # ranked console table + reports/early.html
    DATA_DIR=/path/to/parquet python3 scanner.py
"""
import glob
import os
import numpy as np
import pandas as pd

DATA_DIR = os.environ.get("DATA_DIR",
    "/home/ubuntu/Desktop/Projects/trading-lab/FuturesScan/data/raw/4h")
REPORTS = os.path.join(os.path.dirname(__file__), "reports")
RVOL_LEN, EMA_F, EMA_M, EMA_S, HH_LEN = 20, 9, 21, 50, 20


def ema(s, n):   return s.ewm(span=n, adjust=False).mean()
def rma(s, n):   return s.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma(-d.clip(upper=0), n)
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def score_df(df):
    """Return (score, metrics dict) for the LAST bar of an OHLCV frame."""
    if len(df) < 60:
        return None
    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"]
    e9, e21, e50 = ema(c, EMA_F), ema(c, EMA_M), ema(c, EMA_S)
    r = rsi(c, 14)
    macd = ema(c, 12) - ema(c, 26)
    hist = macd - ema(macd, 9)
    vol20 = v.rolling(RVOL_LEN).mean()
    rvol = (v / vol20).replace([np.inf, -np.inf], np.nan)
    tp = (h + l + c) / 3
    vwap = (tp * v).rolling(20).sum() / v.rolling(20).sum()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = rma(tr, 14)
    basis, sd = c.rolling(20).mean(), c.rolling(20).std()
    bbw = (4 * sd) / basis
    hh = h.rolling(HH_LEN).max().shift(1)
    chg5, chg15, chg1h = c / c.shift(1) - 1, c / c.shift(3) - 1, c / c.shift(12) - 1

    i = -1  # last bar
    def val(x): return float(x.iloc[i])
    cl, hhv, rv = val(c), val(hh), val(rvol)
    e9v, e21v, e50v, e21p = val(e9), val(e21), val(e50), float(e21.iloc[i - 3])
    rsv, histv, histp = val(r), val(hist), float(hist.iloc[i - 1])
    atrv, atrp = val(atr), float(atr.iloc[i - 5])
    bbwv, bbwp, bbwavg = val(bbw), float(bbw.iloc[i - 5]), float(bbw.rolling(50).mean().iloc[i])
    vw, ov = val(vwap), val(o)
    v5avg, c5, c15, c1h = float(v.rolling(5).mean().iloc[i]), val(chg5), val(chg15), val(chg1h)

    tS = 5*(cl > e50v) + 5*(e9v > e21v) + 5*(e21v > e50v) + 5*(e21v > e21p)
    vS = (6 if 1.0 <= rv < 1.5 else 0) + (12 if 1.5 <= rv < 2.0 else 0) + \
         (15 if 2.0 <= rv < 3.0 else 0) + (10 if rv >= 3.0 else 0) + (10 if v5avg > val(vol20) else 0)
    vS = min(vS, 25)
    mS = (8 if 55 <= rsv <= 70 else 0) + (4 if 50 <= rsv < 55 else 0) + (2 if rsv > 75 else 0) + \
         (6 if histv > 0 else 0) + (3 if histv > histp else 0) + (3 if (e9v > e21v > e50v) else 0)
    mS = min(mS, 20)
    near = cl < hhv and cl > hhv * 0.98
    broke = cl > hhv
    bS = (8 if near else 0) + (10 if broke else 0) + (4 if broke and rv > 2 else 0) + \
         (2 if broke and val(l) <= hhv * 1.005 else 0)
    bS = min(bS, 20)
    volS = (4 if atrv > atrp else 0) + (4 if bbwv > bbwp else 0) + (2 if bbwp < bbwavg else 0)
    volS = min(volS, 10)
    pen = (8 if c5 > 0.10 else 0) + (8 if c15 > 0.15 else 0) + (10 if c1h > 0.25 else 0) + \
          (5 if vw > 0 and (cl - vw) / vw > 0.08 else 0) + (5 if ov > 0 and abs(cl - ov) / ov > 0.08 else 0)
    score = max(0.0, min(100.0, tS + vS + mS + bS + volS - pen))
    trend = "UP" if (cl > e50v and e9v > e21v > e50v) else ("up?" if cl > e50v else "flat")
    brk = "BRK" if broke else ("near" if near else "-")
    return score, dict(rvol=rv, rsi=rsv, c5=c5, c15=c15, c1h=c1h, trend=trend, brk=brk,
                       t=tS, v=vS, m=mS, b=bS, vol=volS, pen=pen)


def sig(s): return "EARLY" if s >= 85 else "STRONG" if s >= 75 else "WATCH" if s >= 60 else "WEAK" if s >= 40 else "IGNORE"


def main():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.parquet")))
    rows = []
    for f in files:
        sym = os.path.basename(f).replace(".parquet", "")
        try:
            res = score_df(pd.read_parquet(f))
        except Exception:
            continue
        if res is None:
            continue
        sc, m = res
        rows.append((sym, sc, m))
    rows.sort(key=lambda x: x[1], reverse=True)

    print(f"Early Pump Scanner · {len(rows)} coins · data: {DATA_DIR}")
    print(f"(columns chg1/chg3/chg12 = moves over 1/3/12 bars of this timeframe)\n")
    print(f"{'symbol':<14}{'score':>6}{'sig':>8}{'chg1':>8}{'chg3':>8}{'chg12':>8}{'RVOL':>6}{'RSI':>5}{'trend':>6}{'brk':>6}")
    for sym, sc, m in rows[:25]:
        print(f"{sym:<14}{sc:>6.0f}{sig(sc):>8}{m['c5']*100:>7.1f}%{m['c15']*100:>7.1f}%"
              f"{m['c1h']*100:>7.1f}%{m['rvol']:>6.1f}{m['rsi']:>5.0f}{m['trend']:>6}{m['brk']:>6}")

    # HTML
    os.makedirs(REPORTS, exist_ok=True)
    body = ""
    for sym, sc, m in rows:
        col = "#26d07c" if sc >= 85 else "#3fb950" if sc >= 75 else "#f5b544" if sc >= 60 else "#8b949e" if sc >= 40 else "#5a6372"
        body += (f"<tr><td>{sym}</td><td style='color:{col};font-weight:700'>{sc:.0f}</td>"
                 f"<td>{sig(sc)}</td><td>{m['c5']*100:.1f}%</td><td>{m['c15']*100:.1f}%</td>"
                 f"<td>{m['c1h']*100:.1f}%</td><td>{m['rvol']:.1f}</td><td>{m['rsi']:.0f}</td>"
                 f"<td>{m['trend']}</td><td>{m['brk']}</td>"
                 f"<td class=bd>T{m['t']:.0f} V{m['v']:.0f} M{m['m']:.0f} B{m['b']:.0f} Vol{m['vol']:.0f} −{m['pen']:.0f}</td></tr>")
    html = f"""<!doctype html><html><head><meta charset=utf-8><meta http-equiv=refresh content=120>
<title>Early Pump Scanner — all coins</title><style>
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:24px;font-size:13px}}
h1{{font-size:19px}}.sub{{color:#8b949e;margin-bottom:14px}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:6px 10px;text-align:right;border-bottom:1px solid #21262d}}
th{{color:#8b949e;font-size:12px;text-transform:uppercase}}td:first-child,th:first-child{{text-align:left}}
tr:hover td{{background:#161b22}}.bd{{color:#8b949e;font-family:ui-monospace,monospace;font-size:11px}}
</style></head><body>
<h1>🚀 Early Pump Scanner <span class=sub>— all {len(rows)} coins, ranked</span></h1>
<div class=sub>data: {os.path.basename(DATA_DIR)} · descriptive conditions, NOT a prediction · breakdown col = T/V/M/B/Vol −penalty</div>
<table><thead><tr><th>Symbol</th><th>Score</th><th>Signal</th><th>chg1</th><th>chg3</th><th>chg12</th>
<th>RVOL</th><th>RSI</th><th>Trend</th><th>Brk</th><th>Breakdown</th></tr></thead><tbody>{body}</tbody></table>
</body></html>"""
    with open(os.path.join(REPORTS, "early.html"), "w") as f:
        f.write(html)
    print(f"\nreport: {os.path.join(REPORTS, 'early.html')}")


if __name__ == "__main__":
    main()
