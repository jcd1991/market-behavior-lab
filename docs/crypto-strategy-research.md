# Crypto strategy research log

This document records the current research lanes and the evidence required
before treating any result as credible. All returns below are historical
backtests, not forecasts or investment advice.

## Current data lanes

- OKX perpetual futures: BTC, ETH, SOL, XRP, ADA, DOGE, and LTC.
- Coinbase Advanced spot: BTC/USD, ETH/USD, SOL/USD, and XRP/USD.
- Freqtrade exchange candles are the execution truth for each venue.
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
  uncertainty with reproducible IID bootstrap intervals; it is not a future
  performance guarantee.
- `RegimeRoutedSpotLiquidity` adds spot-only volume/liquidity and ATR guards,
  plus optional UTC-session and weekend sizing.
- `RegimeRoutedLongOnly` and `RegimeRoutedShortOnly` provide side-attribution
  lanes without changing the parent strategy's indicators or exits.
- Missing funding data is now left missing in `QuietBreakoutSwing` and
  `SlowResidualRotation`; it is never replaced with price data.

## Sleeve comparison

A 70/15/15 approximation using `RegimeRouted`, `QuietBreakoutSwing`, and
`SlowResidualRotation` produced +3.610 USDT (+0.36%) with a 6.548 USDT maximum
drawdown. A 50/25/25 blend of `RegimeRouted`, `RelativeValueBucket`, and
`CrossSectionalRotation` produced -12.283 USDT (-1.23%). These are not proof
that the first allocation is optimal; they show that diversification only helps
when the added sleeves do not dilute the stronger sleeve with persistent losses.

## Next acceptance gates

1. Run `RegimeRoutedSpotLiquidity` on native Coinbase-supported timeframes or
   document the resampling boundary in every run artifact.
2. Add complete venue-specific spread, fee, slippage, funding, and open-interest
   inputs before testing carry or liquidation signals.
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
