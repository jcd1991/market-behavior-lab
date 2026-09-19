# Crypto strategy research log

This document records the current research lanes and the evidence required
before treating any result as credible. All returns below are historical
backtests, not forecasts or investment advice.

## Current data lanes

- OKX perpetual futures: BTC, ETH, SOL, XRP, ADA, DOGE, and LTC.
- Coinbase Advanced spot: BTC/USD, ETH/USD, SOL/USD, and XRP/USD.
- Freqtrade exchange candles are the execution truth for each venue.
- Kraken was probed separately through its raw-trade download path; standard
  historical klines are unavailable through its adapter, and the bounded
  BTC/USD probe did not provide a strategy-length validation window.
- Derived Coinbase 4-hour candles are created from Coinbase 1-hour OHLCV only
  to satisfy the strategy's higher-timeframe context. They are not native
  exchange 4-hour candles.
- The current OKX files contain full historical OHLCV and mark candles, but no
  index-price or open-interest files. Funding files contain roughly 100 rows
  from June-July 2026, outside the 2024-2025 backtest windows.

## Results so far

### OKX perpetual futures, 1-hour, 2024-06-13 through 2025-12-02

| Strategy | Trades | Profit | Profit factor | Sharpe |
| --- | ---: | ---: | ---: | ---: |
| `RegimeRouted` | 46 | +8.183 USDT (+0.82%) | 1.45 | 0.18 |
| `RegimeRoutedLongOnly` | 33 | +0.961 USDT (+0.10%) | 1.06 | 0.02 |
| `RegimeRoutedShortOnly` | 13 | +7.221 USDT (+0.72%) | 4.36 | 0.14 |
| `RelativeValueBucket` | 152 | -19.405 USDT (-1.94%) | 0.12 | -3.77 |
| `CrossSectionalRotation` | 483 | -46.093 USDT (-4.61%) | 0.36 | -5.98 |

`RegimeRouted` remained positive in rolling windows:

- 2024-06-13 through 2024-12-31: +0.393 USDT, 15 trades.
- 2025-01-01 through 2025-06-30: +1.976 USDT, 10 trades.
- 2025-07-01 through 2025-12-02: +5.814 USDT, 21 trades.

Overlapping six-month windows show why the full-period result should not be
treated as a stable forecast:

| Window | Trades | Result | Bootstrap profit interval | Profitable resamples |
| --- | ---: | ---: | ---: | ---: |
| 2024-06-13 to 2024-12-13 | 15 | +0.04% | -0.53% to +0.60% | 55.1% |
| 2024-09-01 to 2025-03-01 | 14 | -0.33% | -0.88% to +0.21% | 16.0% |
| 2024-12-01 to 2025-06-01 | 10 | +0.20% | -0.16% to +0.59% | 80.3% |
| 2025-03-01 to 2025-09-01 | 19 | +0.35% | -0.30% to +1.04% | 80.5% |
| 2025-06-01 to 2025-12-02 | 21 | +0.58% | -1.02% to +2.37% | 69.8% |

Every interval includes zero and every window has fewer than 22 trades. The
late-2024 overlap is negative and has only 16.0% profitable bootstrap
resamples. The apparent improvement in later 2025 is therefore a hypothesis
about the tested market regime, not evidence of persistent future alpha.

### OKX universe sensitivity

The same strategy, dates, timeframe, fee model, and wallet were rerun with
explicit static-pair configurations:

| Universe | Trades | Profit | Profit factor | Bootstrap profit interval | Profitable resamples |
| --- | ---: | ---: | ---: | ---: | ---: |
| BTC/ETH | 18 | +6.232 USDT (+0.62%) | 3.29 | +0.05% to +1.19% | 96.3% |
| BTC/ETH/SOL/XRP | 31 | -1.095 USDT (-0.11%) | 0.90 | -0.95% to +0.71% | 41.3% |
| Seven-pair universe | 46 | +8.183 USDT (+0.82%) | 1.45 | -0.91% to +2.77% | 76.3% |

The BTC/ETH-only result is the cleanest of these samples, but it still has
only 18 trades and was selected after inspecting the broader results. The
majors result shows that adding SOL and XRP diluted the result; adding ADA,
DOGE, and LTC restored aggregate performance. This is universe-selection
sensitivity, not evidence that the strategy has a general crypto edge.

Pair-level bootstrap attribution of the seven-pair export makes the
concentration clearer. Intervals below are conditional on each pair's observed
trades and use a common hypothetical 1,000-unit starting balance; they are not
portfolio allocations:

| Pair | Trades | Observed result | Bootstrap profit interval | Profitable resamples |
| --- | ---: | ---: | ---: | ---: |
| BTC | 14 | +0.35% | -0.15% to +0.86% | 87.6% |
| ETH | 4 | +0.27% | +0.07% to +0.49% | 98.2% |
| DOGE | 3 | +0.63% | +0.06% to +1.20% | 100.0% |
| LTC | 9 | +0.25% | -0.70% to +1.63% | 60.7% |
| ADA | 3 | +0.05% | -0.49% to +0.59% | 62.6% |
| SOL | 10 | -0.55% | -0.96% to -0.16% | 0.8% |
| XRP | 3 | -0.18% | -0.33% to -0.03% | 0.0% |

ETH and DOGE look positive in this resampling, but their trade counts are too
small for strong inference. SOL and XRP are consistently negative in the
sample and account for much of the majors-universe dilution.

### Buy-and-hold context on the same OKX candles

The `benchmark_buy_hold.py` utility measured a one-entry/one-exit benchmark
using the exact 1-hour candles and a 5-bps fee per side:

| Pair | Net buy-and-hold return | Max drawdown |
| --- | ---: | ---: |
| BTC | +26.44% | 34.77% |
| ETH | -21.57% | 65.29% |
| SOL | -17.79% | 66.08% |
| XRP | +311.51% | 51.05% |
| ADA | -11.80% | 71.40% |
| DOGE | -7.39% | 72.31% |
| LTC | -1.11% | 55.67% |

This is not a recommendation to buy and hold: the benchmark has very large
drawdowns and benefits from knowing the full historical interval. It is a
context check showing that the +0.82% `RegimeRouted` result is not evidence of
capturing the broadest asset trend, especially when XRP is included.

### Cost and path-risk sensitivity

For the expanded `RegimeRouted` run, applying additional round-trip execution
costs produced:

| Additional cost | Result |
| ---: | ---: |
| 0 bps | +0.82% |
| 10 bps | +0.50% |
| 20 bps | +0.19% |
| 40 bps | -0.44% |
| 60 bps | -1.07% |

Trade-order Monte Carlo kept the 46 observed outcomes fixed and permuted their
order. The 95th-percentile maximum drawdown was 1.06%, with an eight-trade
losing streak. This measures path risk only; it does not establish a future
edge or account for parameter uncertainty.

The sample is still too small for a profitability claim. In particular, the
full-period result is sensitive to pair universe, leverage, fees, and venue.

An IID bootstrap of the 46 observed trade outcomes (20,000 resamples, fixed
seed) produced a 5th-95th percentile total-profit interval of -0.91% to
+2.77%; 76.3% of resamples were profitable. This is consistent with a
positive observed sample but a fragile estimate whose uncertainty includes a
loss.

The side-attribution lanes show that nearly all of the observed result came
from short entries. `RegimeRoutedShortOnly` was positive in the three rolling
windows: +0.21% in 2024 H2, +0.04% in 2025 H1, and +0.47% in 2025 H2. It also
remained positive under the tested additional round-trip cost assumptions up to
60 bps. This is a useful hypothesis, not proof of a stable short alpha: it has
only 13 trades, is exposed to borrow/funding/liquidation mechanics, and was
tested on one perpetual venue.

### OKX perpetual futures, 4-hour, seven pairs

With the required 1-day context data available:

- `QuietBreakoutSwing`: 13 trades, -3.047 USDT (-0.30%).
- `SlowResidualRotation`: 31 trades, -11.075 USDT (-1.11%).

Their earlier zero-trade result was not valid evidence because the required
1-day informative candles were absent.

### Coinbase Advanced spot, 1-hour, 2025-01-26 through 2025-12-02

`RegimeRoutedSpotLiquidity` produced 3 trades across BTC, ETH, SOL, and XRP,
for -1.845 USD (-0.18%). This is an early validation lane with a small sample.
The Coinbase 4-hour context was resampled from 1-hour data because the exchange
adapter did not expose native 4-hour candles.

Additional cost sensitivity made the spot result worse: it was -0.21% with
10 bps of extra round-trip cost and -0.30% with 40 bps.

### Session attribution

For the expanded OKX `RegimeRouted` run, the 46 trades grouped as follows:

- Asia/overnight: 17 trades, +13.052 USDT.
- Europe: 7 trades, -2.040 USDT.
- U.S. session: 22 trades, -2.829 USDT.
- Weekday: 40 trades, +13.191 USDT.
- Weekend: 6 trades, -5.008 USDT.

The short-only lane showed the same directional pattern: +7.892 USDT in
Asia/overnight and -0.671 USDT during the U.S. session. This is a hypothesis
for session-aware sizing, not enough evidence to prohibit U.S.-session trades.

That hypothesis was tested with a separate `RegimeRoutedAsiaWindow` lane that
allows entries only from 00:00 through 07:00 UTC. On the same expanded OKX
window it produced 15 trades, +1.026 USDT (+0.10%), and a 1.51 profit factor.
Its bootstrap profit interval was -0.26% to +0.44%, with 69.6% profitable
resamples. The session restriction therefore did not improve the baseline
`RegimeRouted` result and remains an exploratory lane rather than a default
filter.

### Binance.US spot, native 4-hour candles, 2024-02-20 through 2025-12-02

The same U.S.-spot validation was repeated across BTC, ETH, SOL, BNB, XRP,
and DOGE:

- `RegimeRoutedSpot`: 1 BTC trade, -0.093 USDT (-0.01%).
- `RegimeRoutedSpotLiquidity`: 1 BTC trade, -0.073 USDT (-0.01%).
- `PortfolioAllocatorSpot`: 402 trades, -75.505 USDT (-7.55%), profit factor
  0.13, Sharpe -8.63.

The Binance.US result is a useful negative control: the strategies did not
transfer from the OKX perpetual environment into a broad U.S. spot portfolio.
The one-trade regime-lane results are inactive rather than statistically
validated.

Bootstrap cross-checks reinforce the distinction between lanes:

- OKX `RegimeRoutedShortOnly` (13 trades): observed +0.72%, bootstrap interval
  -0.18% to +2.00%, with 86.7% profitable resamples. This remains a small,
  venue-specific hypothesis exposed to funding, liquidation, and shorting
  mechanics.
- Coinbase `RegimeRoutedSpotLiquidity` (3 trades): observed -0.18%, interval
  -0.34% to -0.03%, with 3.8% profitable resamples. The sample is too small
  for a strong inference, but it provides no positive spot evidence.
- Binance.US `PortfolioAllocatorSpot` (402 trades): observed -7.55%, interval
  -8.39% to -6.71%, with no profitable resamples. This is a robust negative
  result for that configuration and venue window, not evidence that every
  spot strategy fails.

### Derivatives-feature validation status

Funding, index, and open-interest strategies are not yet validated. The
available funding timestamps do not overlap the historical backtests, and
open-interest/index data is absent. Until a venue-specific historical dataset
is added, missing derivatives features must remain unavailable rather than be
filled from price or another venue.

The repository now includes two explicitly opt-in validation lanes:

- `RegimeRoutedFundingFilter` requires a non-null, historical funding candle
  for each entry and blocks missing funding. It does not use the live-only
  funding API as a backtest substitute.
- `RegimeRoutedBasisOI` requests mark, index, funding, and open-interest
  candle types and requires basis/OI quality. It remains inactive until the
exact venue supplies overlapping OI history.

It also includes `HurstRegimeSwitch`, an OHLCV-only research lane inspired by
work that uses Hurst-style persistence classification to select momentum or
mean reversion. On the expanded OKX seven-pair 1h window from 2024-06-08
through 2025-12-02, the unoptimized implementation made 862 trades and lost
88.626 USDT (-8.86%) from a 1,000 USDT starting balance, with a 0.70 profit
factor, -4.21 Sharpe, and 9.00% maximum drawdown. This is a failed transfer
test, not a reason to optimize the same window until it looks profitable.

Run `research/evaluation/derivative_manifest.py` before either lane. It
reports file coverage and overlap with the OHLCV window. The
`scripts/backfill_okx_derivatives.sh` helper downloads futures, mark, index,
and funding candles into a caller-selected directory without deleting local
data. Open-interest support is exchange- and Freqtrade-version-dependent; no
OI values are inferred when the CLI does not expose that candle type.

Liquidations are a separate event-data lane. The fixture and validator under
`research/evaluation/liquidation_events.py` require venue, timestamp, side,
quantity, price, and source provenance, but deliberately mark the lane as not
backtest-ready until a licensed historical event source covers the same venue
and dates as execution candles. An OHLCV wick is not treated as a liquidation.

## Implemented research utilities

- `research/evaluation/resample_ohlcv.py` creates a clearly labeled higher-
  timeframe OHLCV file from a lower-timeframe source.
- `research/evaluation/combine_sleeves.py` combines independent Freqtrade
  exports using explicit capital weights. It is an approximate diversification
  study, not a synchronized multi-strategy execution simulation.
- `research/evaluation/cost_sensitivity.py` applies additional round-trip
  execution costs to exported trades.
- `research/evaluation/session_sensitivity.py` attributes exported trades to
  UTC sessions and weekday/weekend buckets.
- `research/evaluation/data_quality.py` audits optional derivative-data
  coverage and date overlap before those fields can be used.
- `research/evaluation/bootstrap_trades.py` estimates trade-outcome
  uncertainty with reproducible IID bootstrap intervals, including optional
  pair-level attribution; it is not a future performance guarantee.
- `research/evaluation/walk_forward_report.py` produces labeled rolling-window
  summaries from Freqtrade exports and applies the same bootstrap protocol.
- `research/evaluation/benchmark_buy_hold.py` compares exact venue candles to
  a fee-adjusted one-entry/one-exit benchmark with drawdown.
- `research/evaluation/simulate_sleeves.py` merges entry/exit timestamps,
  applies capital weights, and enforces a shared maximum-open-position limit.
- `RegimeRoutedSpotLiquidity` adds spot-only volume/liquidity and ATR guards,
  plus optional UTC-session and weekend sizing.
- `RegimeRoutedLongOnly` and `RegimeRoutedShortOnly` provide side-attribution
  lanes without changing the parent strategy's indicators or exits.
- `RegimeRoutedAsiaWindow` provides a fixed 00:00-07:00 UTC session hypothesis
  test without changing the baseline strategy defaults.
- Missing funding data is now left missing in `QuietBreakoutSwing` and
  `SlowResidualRotation`; it is never replaced with price data.
- `research/evaluation/derivative_features.py` computes nullable basis/OI
  interactions and side-aware funding policies without cross-venue filling.
- `RegimeRoutedFundingFilter` and `RegimeRoutedBasisOI` are research-only
  derivatives lanes; the baseline `RegimeRouted` defaults are unchanged.

## Sleeve comparison

A 70/15/15 approximation using `RegimeRouted`, `QuietBreakoutSwing`, and
`SlowResidualRotation` produced +3.610 USDT (+0.36%) with a 6.548 USDT maximum
drawdown. A 50/25/25 blend of `RegimeRouted`, `RelativeValueBucket`, and
`CrossSectionalRotation` produced -12.283 USDT (-1.23%). These are not proof
that the first allocation is optimal; they show that diversification only helps
when the added sleeves do not dilute the stronger sleeve with persistent losses.

Using the BTC/ETH-only `RegimeRouted` lane as the stronger sleeve changed the
capital-weighted approximation to:

- 70/15/15 with `QuietBreakoutSwing` and `SlowResidualRotation`: +2.244 USDT
  (+0.22%), 62 combined trades, and 1.152 USDT maximum drawdown.
- 50/25/25 with `RelativeValueBucket` and `CrossSectionalRotation`: -13.258
  USDT (-1.33%), 653 combined trades, and 13.361 USDT maximum drawdown.

The first blend is positive only because the BTC/ETH sleeve dominates its
allocation; the second demonstrates that adding high-turnover negative sleeves
can materially worsen both return and drawdown. The evaluator combines closed
trade outcomes from independent runs and does not model a synchronized
multi-strategy allocator, shared open-trade capacity, correlated intrabar
losses, funding, or order contention.

The synchronized-capacity approximation was then run on the 70/15/15 blend.
With a shared two-position limit it accepted 60 trades, rejected two
overlapping entries, and returned +2.168 USDT (+0.217%). With a four-position
limit it accepted all 62 trades and returned +2.244 USDT (+0.224%). The small
difference indicates that capacity contention was not the main source of risk
in this sample; sleeve quality and universe selection were.

## Next research lanes: residual GHE and frequency sensitivity

`RelativeValueGHE` keeps the existing fixed leader map and residual entry/exit
rules from `RelativeValueBucket`, then allows entries only when a causal
generalized-Hurst estimate of the residual is at or below the anti-persistence
threshold. This tests whether the residual process is currently more
mean-reverting without introducing a rolling pair optimizer or future-informed
pair selection. It is a research filter, not evidence that a generalized
Hurst exponent predicts returns.

```bash
freqtrade backtesting --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.okx.expanded.example.json" \
  --datadir "$LAB_ROOT/user_data/data" --strategy RelativeValueGHE \
  --timerange 20240613-20251202 --export trades
```

Frequency sensitivity is evaluated from native Freqtrade candles, not by
pretending that a resampled series is a new execution venue. The helper runs
`RegimeRouted` at 1h, 4h, and 1d by default and reports trade count, return,
win rate, profit factor, and sequential max drawdown:

```bash
FREQTRADE_ROOT=/path/to/freqtrade \
LAB_ROOT=/path/to/market-behavior-lab \
scripts/run_frequency_sensitivity.sh
```

The 1d lane may be rejected or be statistically thin for a given timerange;
that is a result to document, not a reason to substitute a different venue or
fill missing candles. Frequency findings remain conditional on the exact
exchange, pair universe, dates, fees, and native candle availability.

On the expanded OKX seven-pair window (`2024-06-13` through `2025-12-02`,
1,000 USDT starting balance, 0.05% worst-case fee), the first comparison was:

| Native timeframe | Trades | Profit | Profit factor | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| 1h | 46 | +8.183 USDT (+0.818%) | 1.451 | 0.857% |
| 4h | 3 | -5.435 USDT (-0.543%) | 0.000 | 0.543% |
| 1d | 0 | 0.000 USDT | n/a | 0.000% |

The 1h result matches the existing baseline record. The 4h and 1d rows are
frequency observations, not meaningful out-of-sample validation: the 4h row is
only three trades and the daily lane generated none. The comparison therefore
does not justify claiming that 1h is universally superior.

The first strict `RelativeValueGHE` run on the same OKX 1h universe generated
zero trades. Its residual GHE values stayed above the default anti-persistence
cutoff (`0.48`) in the observed sample, so the selector correctly failed
closed rather than relaxing the threshold until trades appeared. This is a
negative validation result and a reason to investigate estimator choice,
residual construction, and other venues—not a profitability claim.

A bounded threshold sensitivity check (`q=1.0`, 96-candle window) tested
cutoffs of `0.55`, `0.60`, and `0.70`:

| GHE cutoff | Trades | Profit | Profit factor | Interpretation |
| ---: | ---: | ---: | ---: | --- |
| 0.55 | 0 | 0.000 USDT | n/a | No activation |
| 0.60 | 2 | +0.089 USDT (+0.009%) | 2.340 | Too few trades |
| 0.70 | 9 | -0.960 USDT (-0.096%) | 0.141 | More activity, negative result |

The `0.60` result is not promoted to a default. In a chronological split,
`0.60` returned +0.155 USDT on the earlier window with one trade and -0.066
USDT on the later window with one trade. The `0.70` cutoff returned +0.129 USDT
on three earlier trades and -1.089 USDT on six later trades. These samples are
far too small to support tuning claims; the practical finding is that relaxing
the cutoff increases activity before it demonstrates robustness.

Order-flow and reinforcement-learning candidates remain deferred until the
research stack has tick, trade, or order-book data with exact venue and time
coverage. OHLCV candles cannot recreate those inputs.

## Advanced OHLCV research lanes

Six additional experimental lanes are included without changing the baseline
defaults:

1. `RegimeRoutedVolTarget` scales the existing regime-router stake by causal
   realized volatility.
2. `JumpAwareRegimeRouted` vetoes entries after unusually negative standardized
   returns.
3. `CryptoFactorEnsemble` combines momentum, reversal, liquidity, and
   volatility ranks transparently.
4. `VolatilityManagedMomentum` applies volatility-managed sizing to the slower
   momentum/residual sleeve.
5. `ClusterRotation` adds a conservative concentration veto; full cross-pair
   cluster labels are available in `advanced_strategies.py` for portfolio-level
   research.
6. `KalmanResidual` replaces the fixed residual hedge estimate with a causal
   adaptive hedge-ratio experiment.

These are research lanes, not six independent profitability claims. Each must
be tested with native venue candles, fees, slippage, pair-universe controls,
and chronological splits. The factor, jump, volatility, cluster, and Kalman
helpers are intentionally dependency-light so their behavior can be unit
tested separately from Freqtrade execution.

The first OKX comparison used the expanded seven-pair universe, a 1,000 USDT
starting balance, and the same fee assumptions as the baseline. Results were:

| Lane | 1h trades | 1h profit | 4h trades | 4h profit |
| --- | ---: | ---: | ---: | ---: |
| `RegimeRoutedVolTarget` | 46 | +11.497 USDT | 3 | -8.176 USDT |
| `JumpAwareRegimeRouted` | 46 | +8.183 USDT | 3 | -5.435 USDT |
| `CryptoFactorEnsemble` | 470 | -46.180 USDT | 347 | -55.383 USDT |
| `VolatilityManagedMomentum` | 8 | -3.470 USDT | 31 | -17.330 USDT |
| `ClusterRotation` | 111 | -11.311 USDT | 39 | -3.668 USDT |
| `KalmanResidual` | 8 | +0.109 USDT | 2 | -0.175 USDT |

The apparent 1h improvement from volatility targeting came with higher
drawdown (1.32% versus 0.86% for the baseline) and disappeared at 4h. A
bounded 1h target-volatility sweep (`0.15`, `0.25`, `0.35`) produced identical
results because the configured stake ceiling saturated the sizing multiplier.
That is an implementation/tuning limitation, not evidence that the target is
optimal. Jump veto thresholds of `2.0`, `3.0`, and `4.0` also produced the
same trades, indicating that the default signal set rarely crossed the veto.

No lane is promoted to a default. The factor and cluster wrappers should be
reworked at the portfolio level before further tuning, and Kalman residuals
need more observations and a second venue. These results are historical
backtests, not performance promises.

## Native shorter-candle validation

The OKX downloader was run for the same seven perpetual pairs and historical
window at native `30m` and `15m` resolutions. Each pair produced 26,399
30-minute candles and 52,799 15-minute candles. Local validation found no
duplicate timestamps, internal gaps, null OHLCV fields, or invalid high/low
relationships. These files remain local research inputs and are ignored by
Git; they are not bundled as a public data distribution.

The first shorter-frequency results were:

| Lane | 15m trades | 15m profit | 30m trades | 30m profit |
| --- | ---: | ---: | ---: | ---: |
| `RegimeRouted` | 109 | -6.785 USDT (-0.678%) | 67 | -12.239 USDT (-1.224%) |
| `RegimeRoutedVolTarget` | 109 | -10.840 USDT (-1.084%) | 67 | -18.472 USDT (-1.847%) |
| `JumpAwareRegimeRouted` | 103 | -0.124 USDT (-0.012%) | not run | — |
| `KalmanResidual` | 30 | -2.358 USDT (-0.236%) | not run | — |

This does not show that shorter candles are inherently worse. It shows that
the current configuration did not transfer from 1h to 15m or 30m without
retuning signal horizons, stops, fees, and execution assumptions. The 15m
jump-aware result is only a follow-up hypothesis: its drawdown was still 1.56%
and the result is venue- and window-specific.

The first short-timeframe run also exposed and fixed two project-specific
runtime issues: a nanosecond-versus-millisecond UTC merge-key mismatch and an
all-warmup-NaN informative fallback. The fixes preserve causal ordering and do
not fill from future candles.

### Other finer-grained sources

Alternative native sources are available, but they must remain separate
validation lanes:

- Binance documents native `1m`, `3m`, `5m`, `15m`, and `30m` klines for spot
  and derivative products. See the [Binance market-data documentation](https://developers.binance.com/en/docs/products/spot/rest-api/market-data-endpoints).
- Coinbase Advanced provides public market-data REST and WebSocket interfaces,
  but Coinbase spot pairs must be tested as spot pairs such as `BTC/USD`, not
  substituted for OKX perpetual candles. See the [Coinbase Advanced Trade
  documentation](https://docs.cdp.coinbase.com/advanced-trade/docs/ws-overview/).
- Kraken Futures documents native `1m`, `5m`, `15m`, and `30m` market candles,
  including separate spot, mark, and trade tick types. See the [Kraken Futures
  candle documentation](https://docs.kraken.com/api/docs/futures-api/charts/candles).

Binance, Coinbase, and Kraken data can answer venue-transfer questions, but
they cannot repair missing OKX execution history. CoinGecko remains reference
data only. For 5m research, trade-level or order-book data is preferable for
spread and slippage estimation; OHLCV-only 5m results should be treated as
screening evidence, not execution evidence.

## Next acceptance gates

1. Run `RegimeRoutedSpotLiquidity` on native Coinbase-supported timeframes or
   document the resampling boundary in every run artifact.
2. Complete venue-specific spread, fee, slippage, funding, and open-interest
   inputs before treating carry or liquidation signals as validated. The
   current Freqtrade checkout cannot download `open_interest` through its CLI;
   this is a documented blocker, not a reason to backfill from another venue.
3. Run walk-forward windows with a minimum trade-count threshold and bootstrap
   confidence intervals. The bootstrap utility is now available, but its
   intervals remain conditional on the observed trade sample.
4. Compare long-only, short-only, and long/short results separately.
5. Validate the same configuration on a second U.S.-accessible spot venue.
6. Keep leveraged derivatives research separate from the U.S. spot execution
   lane and obtain venue/legal review before any live use.

Useful background research includes [Momentum and liquidity in
cryptocurrencies](https://arxiv.org/abs/1904.00890), [Coinbase's primer on
perpetual futures](https://www.coinbase.com/institutional/research-insights/research/market-intelligence/a-primer-on-perpetual-futures),
and [session-based momentum and reversal research for Bitcoin and
Ethereum](https://www.mdpi.com/1911-8074/19/9/692).
