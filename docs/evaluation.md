# Evaluation and post-mortem

## Status

This project is an archived research artifact. The main lesson is venue and
market dependence: the most promising behavior in the research record did not
transfer cleanly to the intended deployment venue.

## Recorded results

The strongest late-stage spot salvage recorded in the archive was:

| Strategy | Scenario | Window | Profit | Sharpe | Profit factor | Max drawdown |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `RegimeRoutedSpotTrim` | `A4_deny8_toploss` | historical spot test | `+148.654 USDT` (`+14.87%`) | 0.437 | 3.373 | 1.40% |

The final spot architecture pass used OKX spot data from `2024-06-25` through
`2025-12-01`:

| Strategy | Best scenario | Profit | Trades | Sharpe | Profit factor | Max drawdown |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `CrossSectionalRotationSpot` | `XSR1_majors_tight` | -34.72% | 146 | -3.984 | 0.149 | 34.72% |
| `RelativeValueBucketSpot` | `RV4_core2_focus` | -0.05% | 4 | -0.087 | 0.040 | 0.05% |
| `PortfolioAllocatorSpot` | `AL7_liquid_top1_cash` | -66.21% | 191 | -9.284 | 0.061 | 66.54% |

## Interpretation

- OKX was the only venue in the research record showing strong economics.
- Kraken derivatives did not reproduce the same behavior.
- Hyperliquid history was insufficient for the same validation loop.
- The final spot rewrites did not uncover a robust spot-native edge.
- A nearly flat result with four trades is not evidence of robustness.

All figures are historical backtests and depend on the original data, fees,
slippage, pair universe, parameters, and Freqtrade revision. They are not live
results or a forecast.

## Validation approach

The research process used controlled A/B comparisons, lookahead and recursive
analysis, walk-forward windows, trade-order Monte Carlo path-risk analysis, and
default-off promotion gates. Features that were negative, inert, or too
data-dependent were retained only as research history or disabled by default.

## Reproduction limits

The public extraction intentionally excludes raw market data, private result
archives, databases, and live deployment material. The published tables are
historical research records with their original venue and window labels; they
are not reproduced automatically by cloning this repository. Re-run the
documented Freqtrade commands with your own downloaded data before comparing
results.

The primary strategy creates a large feature set, so pandas may emit
DataFrame-fragmentation performance warnings during indicator construction.
That is a known implementation trade-off in this experimental artifact, not a
claim that the strategy is production-optimized.

The latest seven-part free-data re-evaluation is recorded in
[`revaluation-2026-09-25.md`](revaluation-2026-09-25.md). It includes the
frozen-parameter matrix, walk-forward windows, modeled cost sensitivity, data
coverage, and the lanes that remain blocked by incomplete venue history.
