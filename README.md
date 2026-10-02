# early-pump-scanner

External (no 40-symbol limit) crypto **early-momentum scanner**. Scores every coin
in a data folder on the same 0–100 scale as the TradingView version — trend,
relative volume, momentum, breakout and volatility expansion, with an
anti-"already pumped" penalty — and ranks them.

> **Descriptive, not predictive.** A high score means many early-momentum
> conditions are present *now*, not that the coin will pump. Built alongside
> backtests that found no reliable edge in this class of signal. Education/paper
> only; not financial advice.

## Why external

A single TradingView Pine indicator can only watch ~40 symbols (the
`request.security` cap). This scores **all** coins in a folder, with no limit.

## Run

```bash
python3 scanner.py                      # ranked console table + reports/early.html
DATA_DIR=/path/to/parquet python3 scanner.py
```

Expects per-symbol OHLCV parquet files (`open, high, low, close, volume`) in
`DATA_DIR`. Runs entirely on local data — **no exchange calls, no rate-limit /
ban risk.**

## Going live

`score_df()` is the reusable scoring engine. To scan live markets, feed it fresh
5-minute klines per coin (WebSocket-first, on a clean IP / VPS) — it behaves
identically. The honest next step is **forward-testing**: log every ≥75 event and
measure the actual forward return to learn whether the score predicts anything.

## Output

Ranked table: `score · signal · chg(1/3/12 bars) · RVOL · RSI · trend · breakout`,
plus a per-coin point breakdown (Trend/Volume/Momentum/Breakout/Volatility −penalty)
so no score is a black box. HTML report auto-refreshes.
