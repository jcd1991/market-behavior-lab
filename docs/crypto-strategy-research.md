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
- `research/evaluation/orderbook_cost_snapshot.py` records current public
  order-book spread and depth slippage for cost calibration only.
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

## Independent strategy families

Because `RegimeRouted` combines too many hypotheses, the next experiment split
the research into independent lanes rather than adding more router filters:

- `CryptoMomentumRotation`: cross-sectional momentum versus the universe
  median, with scheduled UTC entries.
- `ScheduledPortfolioRotation`: lower-turnover, long-only rotation on a
  4-hour rebalance schedule.
- `StandaloneBreakoutTrend`: Donchian/ATR trend following without a regime
  detector.
- `RelativeValueStatArb`: fixed BTC-leader residual mean reversion with rolling
  beta and z-score.
- `FundingBasisCarry`: funding, mark, and index carry that fails closed when
  exact-venue historical derivatives data is missing.
- `VolatilityCrashGuard`: long-only trend participation gated by BTC trend and
  realized-volatility conditions.

The initial comparison used the expanded OKX seven-pair universe, a common
2024-06-13 through 2025-12-02 window, and `--fee 0.001` (0.10% per side):

| Lane | Timeframe | Trades | Profit | Max drawdown |
| --- | --- | ---: | ---: | ---: |
| `CryptoMomentumRotation` | 1h | 408 | -47.324 USDT (-4.73%) | 5.88% |
| `ScheduledPortfolioRotation` | 4h | 137 | +3.277 USDT (+0.33%) | 2.58% |
| `StandaloneBreakoutTrend` | 4h | 190 | +58.365 USDT (+5.84%) | 1.17% |
| `RelativeValueStatArb` | 1h | 404 | -57.514 USDT (-5.75%) | 7.57% |
| `FundingBasisCarry` | 1h | 0 | unavailable | 0.00% |
| `VolatilityCrashGuard` | 1h | 8 | -0.215 USDT (-0.02%) | 0.07% |

The breakout result is the most interesting screening lead, but it is not a
profitability claim. A ten-epoch Sharpe-oriented parameter search found an
in-sample candidate with 230 trades and +3.83%; when retested on the held-out
2025-06-01 through 2025-12-02 window it produced 23 trades and -0.18% with
0.49% drawdown. The scheduled rotation search found an in-sample +2.19%; its
held-out result was 33 trades and -0.35% with 1.65% drawdown. The tuned files
were kept outside the public tree so the repository defaults remain transparent
and do not silently encode an overfit result.

### Additional candidate lanes

Five further candidates were implemented and screened against the exact local
OKX perpetual candle files. The test window was 2024-06-13 through 2025-12-02,
with 0.10% per-side fees and no synthetic derivatives fields. The reversal lane
uses native 15-minute candles on the original seven-pair universe. The other
four use native 1-hour or 4-hour candles on a synchronized 12-pair universe:
BTC, ETH, SOL, XRP, ADA, DOGE, LTC, LINK, DOT, NEAR, UNI, and ATOM.

`SizeLiquidityDualSignal` uses rolling dollar volume as a reproducible liquidity
proxy; it is not a claim that exchange market-cap or true institutional size was
measured. `BetaNeutralResidualPortfolio` applies a rolling BTC beta cap at the
signal level; it does not guarantee that the aggregate open portfolio is beta
neutral without an allocator.

| Lane | Native timeframe | Trades | Profit | Max drawdown | Screening read |
| --- | --- | ---: | ---: | ---: | --- |
| `VolatilityConditionedReversal` | 15m | 901 | -56.357 USDT (-5.64%) | 5.83% | Reject at baseline |
| `SizeLiquidityDualSignal` | 1h | 206 | +3.666 USDT (+0.37%) | 2.16% | Weak, unstable |
| `DispersionConditionedMomentum` | 4h | 136 | +19.055 USDT (+1.91%) | 1.11% | Promising but not robust |
| `MultiHorizonTrendReversal` | 1h | 1224 | +20.257 USDT (+2.03%) | 6.99% | Positive aggregate, regime-sensitive |
| `BetaNeutralResidualPortfolio` | 1h | 302 | -41.635 USDT (-4.16%) | 5.21% | Reject at baseline |

The split-window check shows why the positive aggregate results are not yet
portable evidence:

| Lane | 2024-06-13 to 2024-12-31 | 2025-01-01 to 2025-12-02 |
| --- | ---: | ---: |
| `VolatilityConditionedReversal` | -2.22% | -3.41% |
| `SizeLiquidityDualSignal` | +1.85% | -1.49% |
| `DispersionConditionedMomentum` | +2.47% | -0.56% |
| `MultiHorizonTrendReversal` | +8.74% | -6.51% |
| `BetaNeutralResidualPortfolio` | -2.25% | -1.88% |

These are research screens, not tuned production candidates. The next gate for
the two positive full-window lanes is a pre-registered walk-forward test on a
third venue with measured spread and slippage. Order-flow, liquidation, and
reinforcement-learning variants remain deferred until reliable event-level data
is available.

### 2026 research-inspired strategy screens

The following lanes were implemented from recent 2026 working papers and
research preprints. The implementations are deliberately narrower than the
papers where the local data cannot support an exact reproduction.

| Lane | Data used | Trades | Full-window result | Split result | Status |
| --- | --- | ---: | ---: | --- | --- |
| `CrossSectionalReversal8W` | OKX 4h, 12 perpetuals | 124 | +0.38% | -1.55%, then +1.68% | Research lead, unstable |
| `AdaptiveTrendPortfolio` | OKX 1h, 12 perpetuals; 6h decision schedule | 1581 | -12.23% | -3.91%, then -8.14% | Reject baseline |
| `SymmetricTrendVeto` | OKX 1h, 12 perpetuals | 4160 | -8.35% | -2.40%, then -5.76% | Reject baseline |
| `CostAwareMomentumGate` | OKX 1h, 12 perpetuals | 782 | -2.43% | -1.10%, then -1.50% | Reject baseline |
| `VolumeProfileOHLCVProxy` | OKX native 5m, 7 perpetuals | 1715 | -11.66% | -7.00%, then -4.69% | Reject; proxy only |
| `MultiTimeframeConfirmation` | OKX native 5m + 15m, 7 perpetuals | 590 | -0.67% | +0.76%, then -0.83% | Control only |

All results use 0.10% per-side fees. The 5m volume-profile lane uses a
candle-volume proxy for tape speed and therefore does not reproduce a
trade-level tape-speed study. The adaptive trend implementation uses a 1-hour
data stream with entries restricted to six-hour UTC decision points; it does not
claim to reproduce a native six-hour exchange feed or the paper's point-in-time
market-cap universe.

The results reinforce the project's existing conclusion: adding complexity did
not automatically create profitability. Only the cross-sectional reversal lane
deserves a larger-data follow-up, and that follow-up requires at least 30
point-in-time assets, survivorship-aware membership, and another venue before
parameter tuning.

### Parameter-tuning audit

The six 2026-inspired lanes were tuned for 10 epochs on the first segment,
2024-06-13 through 2024-12-31, with the 2025 segment held out. The best
parameter set from each search was then frozen and rerun across the full
2024-06-13 through 2025-12-02 window:

| Lane | Tuned segment | Frozen 2025 holdout | Full window | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `CrossSectionalReversal8W` | +2.15% | -0.32% | -0.05% | Overfit / no edge |
| `AdaptiveTrendPortfolio` | +3.75% | -1.47% | +2.80% | Positive aggregate, failed holdout |
| `SymmetricTrendVeto` | -1.29% | -2.55% | -1.46% | No profitable parameter set found |
| `CostAwareMomentumGate` | +1.56% | -2.00% | -0.78% | Overfit / no edge |
| `VolumeProfileOHLCVProxy` | -2.91% | -2.05% | -5.26% | No edge in OHLCV proxy |
| `MultiTimeframeConfirmation` | +0.76% | -2.63% | -0.71% | Overfit / no edge |

The tuned files were temporary and were not committed. This audit confirms that
the full-window `AdaptiveTrendPortfolio` gain is driven by the training period
and should not be presented as a validated result. Freqtrade's own guidance
also warns that backtests can be distorted and recommends lookahead analysis,
recursive analysis, and dry-run comparison before trusting a strategy.

### Established Freqtrade baselines to investigate next

There is no official “tried and true” profitable Freqtrade strategy. The
official `SampleStrategy` is a development template, and the community
`freqtrade-strategies` repository explicitly describes its strategies as
starting points whose results depend on pair, timeframe, venue, and timerange.
The next baseline study should therefore test known strategy families rather
than import a claimed winner:

1. `SampleStrategy` / `FSampleStrategy` as implementation and futures
   compatibility baselines.
2. RSI plus Bollinger mean reversion with volume and trend filters.
3. EMA/ADX trend following with ATR stop and trailing exit.
4. Supertrend or Donchian trend following with volatility-scaled sizing.
5. Informative-timeframe confirmation using the official v3 strategy APIs.

Each baseline must be tested unchanged first, then with one controlled change at
a time. Public strategy repository backtests are not transferable evidence;
they must be rerun against the exact venue, pairlist, fee, slippage, and date
window used here.

### Baseline validation matrix

The baseline pass was run unchanged before any tuning. The full window was
2024-06-13 through 2025-12-02, with native OKX perpetual data for futures and
native Binance.US spot data for spot. Each backtest used a 0.10% fee per side,
the same static six-pair universe where available, and the market mode required
by the strategy. These are screening results, not claims that any strategy is
profitable.

| Lane | Venue/mode | Trades | Full-window result | Max drawdown |
| --- | --- | ---: | ---: | ---: |
| `SampleStrategy` | Binance.US spot | 95 | -0.73% | 1.03% |
| `FSampleStrategy` | OKX perpetual | 194 | +1.73% | 4.39% |
| `BaselineRSIBollinger` | OKX perpetual | 1,496 | -16.95% | 18.05% |
| `BaselineRSIBollingerSpot` | Binance.US spot | 109 | -2.73% | 3.17% |
| `BaselineEMAADX` | OKX perpetual | 806 | +2.38% | 4.39% |
| `BaselineEMAADXSpot` | Binance.US spot | 61 | +0.76% | 2.27% |
| `StandaloneBreakoutTrend` | OKX perpetual | 1,763 | -4.87% | 7.21% |
| `StandaloneBreakoutTrendSpot` | Binance.US spot | 104 | +5.95% | 1.17% |
| `MultiTimeframeConfirmation` | OKX perpetual | 590 | -0.67% | 1.95% |
| `MultiTimeframeConfirmationSpot` | Binance.US spot | 113 | +2.87% | 1.58% |

The walk-forward split was 2024-06-13 through 2024-12-31, followed by
2025-01-01 through 2025-12-02. The most important result is instability:

| Lane | First split | Second split |
| --- | ---: | ---: |
| `FSampleStrategy` / OKX | +3.19% | -1.42% |
| `BaselineEMAADX` / OKX | +4.57% | -1.99% |
| `StandaloneBreakoutTrend` / OKX | +0.03% | -4.73% |
| `StandaloneBreakoutTrendSpot` / Binance.US | +4.77% | +1.18% |
| `MultiTimeframeConfirmationSpot` / Binance.US | +3.58% | -0.66% |

The Binance.US spot breakout is the strongest screening lead because it stayed
positive in both sequential windows. It still has only 104 trades, did not
transfer to OKX futures, and has not yet passed a third-venue test.

#### Bias, recursion, and Monte Carlo checks

Lookahead analysis on a bounded 2025 Q1 window found no lookahead bias for any
of the ten venue/strategy lanes. Recursive analysis with startup-candle
settings of 30, 100, 300, 600, and 1,000 also found no recursive variance or
indicator lookahead. These checks show that the implementations are causal;
they do not show that the signals have predictive power.

An IID trade bootstrap used 10,000 resamples with seed 1337. The percentage of
profitable resamples was: `SampleStrategy` 17.0%, `FSampleStrategy` 61.3%,
RSI/Bollinger OKX 0.0%, RSI/Bollinger spot 1.5%, EMA/ADX OKX 71.1%, EMA/ADX
spot 55.7%, Donchian OKX 7.3%, Donchian spot 99.0%, informative confirmation
OKX 36.4%, and informative confirmation spot 78.3%. This is a conditional
resampling diagnostic, not an independent forward test and not a probability
of future profit.

#### Fees versus slippage

The backtests include the stated 0.10% per-side fee stress. Historical OHLCV
does not contain the bid/ask queue or market-impact path needed to measure the
slippage paid by each historical trade, so this matrix does **not** contain
measured historical slippage. Current order-book snapshots are useful for
calibration but cannot be backdated onto these trades. A future execution-grade
pass must join venue- and timestamp-matched trades with spread/depth or trade-
level data; modeled cost sensitivity must remain labeled as modeled.

#### Dry-run comparison

Credential-free Binance.US spot dry-run startup reached exchange and strategy
resolution for the tested spot lanes. OKX futures initialization was limited
by the exchange's leverage-tier endpoint rate limit while resolving roughly
467 markets in the local dry-run environment. Backtesting completed normally;
the OKX dry-run result is therefore a runtime/setup limitation, not evidence
for or against strategy performance. It must be rerun with a cached or
venue-approved leverage-tier snapshot before treating the futures dry-run as
fully validated.

The official `SampleStrategy` is a template, and the community
`FSampleStrategy` is distributed as a starting point. Neither should be
described as a proven or “tried-and-true” profitable strategy. The official
[Freqtrade strategy guidance](https://www.freqtrade.io/en/stable/strategy-101/)
recommends treating backtests cautiously and comparing lookahead analysis,
recursive analysis, and dry-run behavior.

### Controlled enhancement lanes

The next pass converted reusable findings from this project into explicit
strategy classes in `BaselineEnhancedLanes.py`. Each class keeps the matching
baseline's indicators and exits, then adds one causal gate. Long and short legs
are filtered independently: long signals require the positive directional
condition and short signals require the negative directional condition. Spot
variants disable the short leg entirely.

| Enhancement lane | Existing research idea reused |
| --- | --- |
| `BaselineRSIBollingerRegime` | Slow regime alignment from regime-routed research |
| `BaselineEMAADXVolatility` | Volatility and liquidity gates from crash/liquidity lanes |
| `StandaloneBreakoutTrendRegime` | Directional trend guard from the guarded breakout lane |
| `MultiTimeframeConfirmationVolatility` | Volatility/liquidity gate layered onto informative confirmation |

Derivative-feature lanes were deliberately not used as enhancements: funding,
basis, index, and open-interest history does not overlap the tested windows
sufficiently to support a fair comparison.

The enhanced full-window runs used the same exact venue data and 0.10%
per-side fee stress as the controls:

| Lane | Venue/mode | Trades | Result | Bootstrap profitable resamples |
| --- | --- | ---: | ---: | ---: |
| `BaselineRSIBollingerRegime` | OKX perpetual | 89 | -0.07% | 45.9% |
| `BaselineRSIBollingerRegimeSpot` | Binance.US spot | 46 | -0.62% | 6.2% |
| `BaselineEMAADXVolatility` | OKX perpetual | 407 | -1.05% | 33.9% |
| `BaselineEMAADXVolatilitySpot` | Binance.US spot | 216 | +2.77% | 81.8% |
| `StandaloneBreakoutTrendRegime` | OKX perpetual | 174 | +5.25% | 97.7% |
| `StandaloneBreakoutTrendRegimeSpot` | Binance.US spot | 92 | +6.53% | 99.7% |
| `MultiTimeframeConfirmationVolatility` | OKX perpetual | 7,796 | -19.60% | 0.0% |
| `MultiTimeframeConfirmationVolatilitySpot` | Binance.US spot | 4,839 | -9.02% | 0.0% |

The Donchian regime gate is the only enhancement that improved both venues
and both sequential windows:

| Lane | 2024-06-13 to 2024-12-31 | 2025-01-01 to 2025-12-02 |
| --- | ---: | ---: |
| `BaselineRSIBollingerRegime` / OKX | -0.27% | +0.22% |
| `BaselineRSIBollingerRegimeSpot` / Binance.US | -0.27% | -0.19% |
| `BaselineEMAADXVolatility` / OKX | +0.73% | -1.53% |
| `BaselineEMAADXVolatilitySpot` / Binance.US | +3.41% | -0.82% |
| `StandaloneBreakoutTrendRegime` / OKX | +4.56% | +0.84% |
| `StandaloneBreakoutTrendRegimeSpot` / Binance.US | +5.01% | +1.39% |
| `MultiTimeframeConfirmationVolatility` / OKX | -6.90% | -12.66% |
| `MultiTimeframeConfirmationVolatilitySpot` / Binance.US | -2.87% | -6.13% |

This makes `StandaloneBreakoutTrendRegimeSpot` the strongest current research
candidate, but it remains a screening result. It has not passed a third venue,
and the fee stress still is not a historical bid/ask or market-impact model.
The EMA/ADX spot result is positive in aggregate but fails the second window;
the RSI/Bollinger gate mostly removes trades without creating a stable edge.

#### Corrected informative-timeframe baseline

The unchanged informative-timeframe control was rerun with the exact current
native 5m/15m datasets. It produced 7,819 OKX trades and 5,189 Binance.US
trades over the full window, with -19.54% and -10.28% respectively. The
enhanced version produced slightly fewer trades but remained negative. Earlier
lower trade counts came from a different prior local run context and are
superseded by this clean rerun. The current result confirms that the 5m
implementation has a turnover problem under this configuration; it should not
be promoted without an explicit signal-edge or cooldown redesign.

All eight enhanced lanes passed bounded 2025 Q1 lookahead analysis. Recursive
analysis with startup candles of 30, 100, 300, 600, and 1,000 found no
indicator lookahead; the two informative lanes also reported no recursive
variance. These are implementation-integrity checks, not profitability proof.

### Coinbase loss-reduction experiment

The original `StandaloneBreakoutTrendSpot` lost 9.94% in the Coinbase
2025-01-26 through 2025-05-01 window. A spot-only guarded variant,
`StandaloneBreakoutTrendSpotGuarded`, requires the BTC reference pair to be
above a causal EMA before allowing breakout entries. The simple guard reduced
the loss to 8.81%. A 60-epoch Sharpe-oriented search over channel, breakout
buffer, ATR limit, guard EMA, exit EMA, and stoploss produced a target-window
result of -2.46% with 59 trades and 4.03% drawdown.

The selected candidate was then held out:

- Coinbase 2025-05-01 through 2025-12-02: +2.68%, 136 trades, 1.92% drawdown.
- Binance.US 2024-06-13 through 2025-12-02: +4.95%, 155 trades, 0.73% drawdown.

With the repository-default guarded parameters rerun across the complete
available windows, the results were Coinbase 2025-01-26 through 2025-12-02:
-6.00% from 245 trades and 9.43% drawdown, versus Binance.US 2024-06-13
through 2025-12-02: +6.19% from 87 trades and 1.22% drawdown. The guard is a
small Coinbase loss reduction relative to the unguarded -7.64% full-window
result, not a profitable Coinbase solution.

This is risk reduction, not a successful repair of the target window. Making
the strategy break even there would require either overfitting the date range
or suppressing participation until the result is trivially zero. The guarded
variant is therefore retained as an experimental lane, while its tuned
parameters remain outside the public tree.

These results change the research priority, not the evidence standard:
standalone breakout trend deserves more independent venues and walk-forward
windows; scheduled rotation is a lower-turnover secondary lead; momentum and
residual stat-arb are rejected in this configuration; carry remains data
blocked; and crash protection should be evaluated as a portfolio overlay rather
than an alpha strategy. None of these lanes should be marketed as expected to
make money.

### Venue-transfer and walk-forward check

The independent lanes were then evaluated on locally available U.S.-accessible
spot data. The tests used the same 0.10% per-side fee stress, but venue and
timeframe are not interchangeable:

| Venue and lane | Timeframe | Window | Trades | Profit | Max drawdown |
| --- | --- | --- | ---: | ---: | ---: |
| Binance.US `CryptoMomentumRotationSpot` | 1h | 2024-06-13 to 2025-12-02 | 252 | -5.788 USDT (-0.58%) | 2.75% |
| Binance.US `ScheduledPortfolioRotation` | 4h | 2024-06-13 to 2025-12-02 | 119 | +18.775 USDT (+1.88%) | 1.66% |
| Binance.US `StandaloneBreakoutTrendSpot` | 4h | 2024-06-13 to 2025-12-02 | 104 | +59.502 USDT (+5.95%) | 1.17% |
| Binance.US `VolatilityCrashGuard` | 1h | 2024-06-13 to 2025-12-02 | 12 | -0.834 USDT (-0.08%) | 0.11% |
| Coinbase `CryptoMomentumRotationSpot` | 1h | 2025-01-26 to 2025-12-02 | 90 | -74.919 USD (-7.49%) | 8.45% |
| Coinbase `ScheduledPortfolioRotation` | 1h* | 2025-01-26 to 2025-12-02 | 41 | -76.849 USD (-7.68%) | 7.68% |
| Coinbase `StandaloneBreakoutTrendSpot` | 1h* | 2025-01-26 to 2025-12-02 | 273 | -76.388 USD (-7.64%) | 10.54% |
| Coinbase `VolatilityCrashGuard` | 1h | 2025-01-26 to 2025-12-02 | 14 | -3.842 USD (-0.38%) | 0.68% |

`*` Coinbase's Freqtrade adapter does not expose native `4h`, so those checks
used 1h and are not direct timeframe matches to the Binance.US rows. The
long-only wrappers `CryptoMomentumRotationSpot` and
`StandaloneBreakoutTrendSpot` exist to make spot compatibility explicit;
short-capable strategies are never silently run in spot mode.

The Binance.US breakout lane was also split into sequential windows:

| Window | Trades | Profit | Max drawdown |
| --- | ---: | ---: | ---: |
| 2024 H2 | 42 | +4.77% | 0.51% |
| 2025 H1 | 37 | -0.32% | 1.23% |
| 2025 H2 | 25 | +1.58% | 0.49% |

This is encouraging as a screening result because it is not confined to one
positive window, but it is still not validation: Coinbase did not reproduce it,
the windows are not independent market regimes, and the fee stress is not a
measured spread/slippage model. The next gate is trade-level cost estimation,
then a third venue or a longer rolling walk-forward with a minimum trade count.

### Execution-cost calibration snapshot

Historical OHLCV does not contain the bid/ask queue or market-impact path needed
to measure the spread paid by each historical trade. The new
`research/evaluation/orderbook_cost_snapshot.py` utility therefore records
timestamped public order-book observations for calibration only. It estimates
top-of-book spread and depth-based buy/sell slippage for a requested notional;
it does not modify candles or rewrite historical trade results.

A current USD 20 snapshot on 2026-09-19 UTC reported the following indicative
costs:

| Venue | Pair | Spread | Buy depth slippage | Sell depth slippage |
| --- | --- | ---: | ---: | ---: |
| Binance.US | BTC/USDT | 0.001 bps | 0.001 bps | 0.001 bps |
| Binance.US | ETH/USDT | 0.683 bps | 0.341 bps | 0.341 bps |
| Binance.US | SOL/USDT | 1.797 bps | 0.898 bps | 0.898 bps |
| Coinbase | BTC/USD | 0.001 bps | 0.001 bps | 0.001 bps |
| Coinbase | ETH/USD | 0.152 bps | 0.076 bps | 0.076 bps |
| Coinbase | SOL/USD | 0.899 bps | 0.449 bps | 0.449 bps |
| Kraken | BTC/USD | 0.012 bps | 0.006 bps | 0.006 bps |
| Kraken | ETH/USD | 0.038 bps | 0.019 bps | 0.019 bps |

These are live snapshots, not historical execution measurements, and can change
materially with volatility, order size, and time of day. The breakout
trade-level scenario check remained positive on the full Binance.US run at
additional round-trip costs of 10, 20, 40, 80, and 120 bps (+5.74%, +5.54%,
+5.13%, +4.31%, and +3.48%). Coinbase remained negative before any additional
cost (-7.64%), so current liquidity snapshots do not rescue that venue result.

An attempted Kraken OHLCV download exposed a separate data limitation: the
current Freqtrade/CCXT path reports that Kraken historical klines require
trade-download aggregation. No Kraken candles were used in the comparison, and
the live Kraken order-book snapshots must not be presented as a third historical
backtest venue.

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

### Native 5m screening experiment

The same OKX perpetual universe was downloaded at native `5m` resolution for
2024-06-01 through 2025-12-02. All seven pairs produced 158,399 candles. The
local checks found no duplicate timestamps, internal gaps, null OHLCV values, or
invalid high/low relationships. A temporary OKX timeout/rate-limit episode
affected pagination for SOL, but a pair-specific retry completed the file. The
mark/index/funding requests still returned no overlapping historical data, so
none of those fields were substituted into the test.

The screening backtests used 2024-06-13 through 2025-12-02, the same seven-pair
universe, and `--fee 0.001` (0.10% per side). That fee is a conservative cost
stress case, not a measured spread or slippage model:

| Lane | Trades | Profit | Profit factor | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| `RegimeRouted` | 152 | -33.162 USDT (-3.32%) | 0.448 | 3.75% |
| `JumpAwareRegimeRouted` | 149 | -32.285 USDT (-3.23%) | 0.455 | 3.66% |
| `RegimeRoutedVolTarget` | 152 | -49.461 USDT (-4.95%) | 0.455 | 5.59% |

The 5m lanes therefore fail this initial screening pass. They generated more
short-horizon turnover without demonstrating cost-adjusted edge, and the
volatility-targeting wrapper increased drawdown. These results do not prove
that 5m trading is impossible; they show that this configuration is not ready
for execution claims. Any follow-up must use trade-level or order-book data to
estimate spread and slippage, test fee sensitivity, and validate results on
separate windows and venues. The downloaded OHLCV files remain local and
ignored by Git; no market data was added to the public repository.

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

## External strategy validation batch

The September 2026 comparison batch tested public Freqtrade strategies in a
quarantined checkout. Their source files and original parameters were retained
outside this MIT repository because the official strategy collection is GPL,
the Nate Emma repository is GPL-3.0, and the other repositories did not expose
a license that was clear enough for redistribution. The batch therefore records
behavior and ideas, not copied source. The upstream repositories also describe
these strategies as educational starting points whose results depend on pair,
timeframe, timerange, and configuration.

The controls used native local Binance.US candles for BTC, ETH, SOL, BNB, XRP,
and DOGE, a 0.10% fee per side, and the full `2024-06-13` through
`2025-12-02` window unless noted. The five-minute BinHV45 lane additionally
used native 30m and 1h informative candles. Results below are historical
backtests, not live performance.

| External lane | Market | Original/control result | Later-window result | Bias check | Decision |
| --- | --- | ---: | ---: | --- | --- |
| `BinHV45_Regime_5m` | Binance.US spot | -0.91%, 221 trades, 1.46% DD | -1.24%, 135 trades | Lookahead: no bias detected | Reject for now |
| `Supertrend` (pta compatibility) | Binance.US spot | +1.17% control; tuned +0.65%, 722 trades, 3.16% DD | tuned -2.28%, 433 trades, 3.24% DD | Lookahead: no bias detected | Reject tuned parameters |
| `FSupertrendStrategy` (pta compatibility) | OKX perpetual | +3.70%, 706 trades, 1.13% DD | Not rerun in this batch | Not rerun | Futures-only research lead |
| `EMAcross_4h` | Binance.US spot | +0.10% control; tuned +0.24%, 37 trades, 0.17% DD | tuned +0.05%, 15 trades, 0.17% DD | No lookahead result: too few trades; recursive differences in regime features | Weak baseline |
| `MomentumRegimeBasket15mFast` | Binance.US spot, 3 slots | +47.36%, 72 trades, 17.78% DD | — | Lookahead run blocked by the source's slow custom data/callback path | Concentrated research lead |
| `MomentumRegimeBasket15mLb30` | Binance.US spot, 3 slots | +84.62%, 68 trades, 15.15% DD | +11.59%, 42 trades, 14.65% DD | Bounded lookahead run blocked by the same path; not cleared | Best candidate, not validated |
| `Solipsis_USD` | Binance.US spot | -0.69% on Q1 2025 smoke window | Full run blocked by callback/data compatibility | Not completed | Defer |

The source author's BinHV45 robustness variants did not change the conclusion:
`Downtrend` and `Persistence` were each -0.91%, while `Bounce` was -0.97%.
The Momentum basket's source-documented 21-day and 30-day lookbacks are useful
controlled experiments, but their apparent improvement comes with long holding
periods, high concentration, few winners, and material drawdown. On this
six-pair universe, the tested exit-rank variants were identical to the 21-day
result, so they were not treated as independent evidence.

The bounded tuning searches were deliberately small. EMAcross selected
`fast_period=17`, `slow_period=52`, and `rsi_buy=47` on the first half. The
Supertrend search selected buy multipliers/periods `(3,7), (3,7), (2,15)` and
sell `(1,20), (3,20), (7,9)`. Both tuned sets were then evaluated on the later
window; only EMAcross retained a small positive result, with too few trades to
call it a robust edge.

### Cross-research comparison

The strongest internal reference remains the regime-aligned Donchian lane from
the public research set: +5.25% on the full OKX perpetual window and +6.53% on
the full Binance.US spot window, with positive but uneven walk-forward windows.
The external batch adds two useful ideas without importing external code:

- multi-timeframe trend confirmation and explicit regime gating are already
  represented in the internal lanes and should be compared as feature toggles,
  not pasted from GPL code;
- slower cross-sectional momentum selection is a promising portfolio overlay,
  but must be tested with larger, survivorship-controlled universes and capped
  concentration before it can enhance a single-pair router.

The external batch did not establish a portable profit edge. It also did not
have measured historical spread or order-book slippage. Fee-only results are
therefore screening results. The next cost gate is to rerun the leading lanes
with venue-calibrated spread/slippage scenarios and require holdout survival.

The modeled cost sensitivity below raises the Freqtrade fee argument from
0.10% per side to 0.15% and 0.25% per side. It is a deliberately simple
spread/slippage stress, not a claim about the historical fill cost:

| Lane | 0.10% per side | 0.15% per side | 0.25% per side |
| --- | ---: | ---: | ---: |
| `BinHV45_Regime_5m` | -0.91% | -1.45% | -2.03% |
| tuned `EMAcross_4h` | +0.24% | +0.23% | +0.21% |
| tuned `Supertrend` | +0.65% | -1.56% | -3.66% |
| `MomentumRegimeBasket15mLb30` | +84.62% | +80.62% | +72.97% |

Momentum's apparent resilience here is not enough to promote it: the result is
dominated by a small number of long-duration trades and a concentrated six-pair
universe, and it still carries double-digit drawdown.

All Binance.US spot candidates in this batch are long-only; there is no
independent short leg to evaluate for them. The OKX `FSupertrendStrategy` lane
was also run as the source's long-only futures strategy, so its +3.70% result
must not be read as evidence for a short or long/short portfolio. The internal
Donchian and regime-router comparisons should continue to report long and
short legs separately when a strategy actually supports both.

### Provenance links

- [freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies),
  commit `f3340ce` — GPL-3.0; educational strategies, including Supertrend.
- [nateemma/strategies](https://github.com/nateemma/strategies), commit
  `26f1ae3` — GPL-3.0; includes the MomentumRegimeBasket research notes.
- [zevrichards/freqtrade-strategies](https://github.com/zevrichards/freqtrade-strategies),
  commit `9dc9ef2` — license not clear in the inspected checkout.
- [sevenpen/freqtrade-strategies_2024](https://github.com/sevenpen/freqtrade-strategies_2024),
  commit `397f254` — license not clear in the inspected checkout; Solipsis was
  only run as a compatibility smoke test.

Compatibility edits used only for local testing—`pandas_ta` in place of the
missing `technical` Supertrend helper, a current NumPy spelling, and a
Freqtrade callback bridge—are not original-source results and are not included
in this public repository.
