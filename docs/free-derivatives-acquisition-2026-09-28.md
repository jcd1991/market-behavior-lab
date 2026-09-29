# Free derivatives acquisition — 2026-09-28

## What was pulled

The existing project cache already contained fragments from several public
derivatives sources. The usable same-venue expansion completed in this pass is
an official Binance Global USD-M panel for **BTCUSDT** and **ETHUSDT** covering
2026-06-01 through 2026-08-31:

| Artifact | BTC | ETH | Native resolution |
| --- | ---: | ---: | --- |
| Spot candles | 132,480 | 132,480 | 1 minute |
| Perpetual candles | 132,480 | 132,480 | 1 minute |
| Perpetual index | 131,040 | 131,040 | 1 minute |
| Perpetual mark | 131,040 | 131,040 | 1 minute |
| Funding observations | 276 | 276 | funding event |
| Derivatives metrics | 26,496 | 26,496 | 5 minutes |

The raw ZIP archives and their retrieval manifests are local under
`user_data/data/historical/raw/acquisition-2026-09-28/` and remain ignored by
Git. The normalized artifacts are under the matching
`user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/`
directory. Every normalized sidecar records `venue: binance-global`, the
original input list, UTC timestamps, and `execution_truth: false`.

The new daily-metrics path is reusable:

```bash
python scripts/fetch_free_historical.py \
  --output-root user_data/data/historical/raw/acquisition-2026-09-28 \
  binance --market-type futures --futures-market um \
  --dataset metrics --symbol BTCUSDT --date 2026-08-01

python scripts/normalize_binance_metrics_series.py \
  --input-dir user_data/data/historical/raw/acquisition-2026-09-28/binance/metrics \
  --symbol BTCUSDT --pair BTC/USDT:USDT \
  --output user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-metrics-5m.feather \
  --source binance-global-public-archive-metrics-acquisition-2026-09-28
```

The metrics file contains open interest, open-interest value, and the ratio
columns published by the archive. It is a context panel, not a liquidation
ledger or historical margin-state feed.

The pass also retained two official OKX BTC-USDT-SWAP 400-level L2 archives
for 2026-09-01 and 2026-09-02. They are compressed newline-delimited JSON
snapshots/updates with exchange timestamps, bids, asks, and update actions.
The pair of archives is approximately 738 MB and remains raw/ignored. It is
usable for a bounded spread, depth, and slippage-calibration experiment after
an L2 replay parser is added; it is not a substitute for a long-window
execution history.

## What it makes possible

This acquisition is now sufficient to study, on one venue and with aligned
spot/perpetual/index/mark/funding history:

- basis distribution and persistence;
- funding-conditioned entry filters;
- open-interest change as a contextual feature;
- mark/index divergence and stress diagnostics;
- BTC-versus-ETH cross-sectional derivatives context;
- conservative fee, spread, and slippage sensitivity around a carry screen.

It is not yet sufficient to claim a portable cash-and-carry product. The
strict carry audit reports:

```text
overlap: 91.67 days
funding events: 276
provenance: same Binance Global venue on all four core inputs
promotion result: blocked — margin_buffer_missing
```

The carry evaluator's default diagnostic produced no entries because its
conservative basis and funding thresholds were not met. A deliberately loose
screen produced one basis-convergence trade for each symbol: about **+1.60%**
for BTC and **+0.81%** for ETH before configured stress, but about **-0.40%**
and **-1.19%** after the adverse-basis and venue-failure stress. Funding income
was zero during those held intervals. These are pipeline diagnostics, not
profitability claims.

## What remains unavailable

- Binance Global is not Binance.US and cannot validate U.S. spot execution.
- The public metrics archive does not reconstruct margin requirements,
  liquidation distance, or liquidation events.
- Open interest is 5-minute context; it is not minute-level execution truth.
- The free panel does not include full historical L2 books or reliable
  venue-specific spread/slippage curves. The two-day OKX L2 sample is the
  exception, but it is too short to establish a persistent edge.
- Same-venue two-leg residual hedging still needs an explicitly shortable,
  provenance-labeled second leg and synchronized cost model.
- OKX public artifacts remain fragmented in this project; they do not yet form
  a complete spot/perpetual carry contract.

The next responsible step is to add a conservative, explicit margin/liquidation
model and measured fill-cost assumptions, then run a locked forward window. The
absence of a free historical liquidation ledger is recorded as a gate, not
filled with CoinGecko, another venue, or synthetic values.

## Source boundaries

The archive path is from the official [Binance Public Data repository](https://github.com/binance/binance-public-data/)
and the official public data host. The broader free-source inventory and
provider boundaries are documented in [free-data-sources.md](free-data-sources.md).
The research contract remains separate from Binance.US, Coinbase, OKX, and
CoinGecko data.

If this makes money, tell me lol. If it loses money, tell me that too—the point
is to measure reality, not promise returns.
