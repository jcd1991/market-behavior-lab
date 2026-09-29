# Practical profitability order — 2026-09-28

This pass implemented the next three research lanes in the agreed order:

1. restore a reviewable momentum-basket implementation;
2. evaluate same-venue spot/perpetual cash and carry;
3. tune a low-turnover, point-in-time cross-sectional portfolio.

The results below are screening evidence, not a profitability claim.

The ordered screen can be rerun against the local ignored data cache with:

```bash
python scripts/run_practical_profitability.py \
  --carry-spot user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT-1m.feather \
  --carry-perp user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-1m-futures.feather \
  --carry-funding user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-funding.feather \
  --carry-index user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-index-1m.feather
```

The script accepts explicit data roots and writes no market data to the
repository.

## 1. Momentum basket reconstruction

The historical `MomentumRegimeBasket15mLb30` export cannot be replayed exactly:
its archived subclass imported a base module that is not present in the
checkout. The new
[`MomentumRegimeBasket15m.py`](../user_data/strategies/MomentumRegimeBasket15m.py)
therefore implements a clearly marked reconstruction with the documented
mechanics:

- previous-closed-day cross-sectional momentum;
- previous-closed-day asset trend and BTC regime filters;
- top-N long selection;
- four-hour rebalance cadence on a 15-minute Freqtrade feed;
- a causal quote-volume stake cap.

Freqtrade discovery succeeds for both `MomentumRegimeBasket15m` and
`MomentumRegimeBasket15mLb30`.

The direct Binance.US-labelled 15-minute Freqtrade screen used the native
local candles from 2024-09-01 through 2025-12-02, six USDT pairs, two open
slots, and a 0.10% fee. It produced 3 trades, -0.28% total return, and 0.40%
maximum drawdown. This is not an exact replay of the earlier +84.62% archived
result; it is evidence that the restored implementation is materially
different from, or less complete than, the missing historical source.

The separate causal daily tuner tried four predeclared policies on the same
native candle family. The selected policy was the short 14/30/60-day variant,
which produced +131.09% in the 2024-06-01 through 2024-12-31 training window
but -25.43% in the frozen 2025 holdout. That is a classic overfit signal, so
the tuned policy is rejected for promotion.

Freezing that signal policy and changing only the venue cost model produced
the following daily screening results:

| Native candle set | Available window | Return | Max drawdown | 2026 segment |
| --- | --- | ---: | ---: | ---: |
| Binance.US-labelled spot | 2024-06-01 through 2025-12-05 | +62.62% | 40.08% | Not available in this local set |
| Coinbase spot | 2025-01-01 through 2026-09-20 | -86.20% | 88.91% | -54.90% |
| OKX spot | 2024-06-01 through 2026-09-22 | +1.82% | 65.13% | -23.46% |

This is a portability failure, not a product result. The screen is a daily
research approximation of the 15-minute strategy and should not be compared
directly to the Freqtrade export percentages.

Coinbase and OKX native 15-minute files are present, but Freqtrade’s exchange
startup-history guard rejects this reconstruction’s 4,000-candle warmup on
those venues (their configured five-batch limits are lower). Reducing the
warmup would silently remove the long daily lookbacks. Those lanes remain
runtime/data-contract work, not positive results.

## 2. Same-venue cash and carry

[`cash_carry.py`](../research/evaluation/cash_carry.py) now supports:

- native index fields such as `index_close`;
- explicit loaded-frame evaluation for train/holdout tuning;
- funding income summed from observed funding events during the held period;
- a frozen threshold tuner with adverse-basis and venue-failure stress.

The expanded Binance global sample now covers June through August 2026 for
BTC and ETH with native spot, perpetual, index, mark, funding, and 5-minute
open-interest context. The full default gate produced no entries. A
deliberately loose screen produced one basis trade per asset: about +1.60% for
BTC and +0.81% for ETH before stress, but about -0.40% and -1.19% after the
configured 1% adverse-basis and 1% venue-failure deductions. Zero funding
income was observed during those held intervals. Margin/liquidation-buffer
observations are absent. Full acquisition details are in the [free derivatives
acquisition report](free-derivatives-acquisition-2026-09-28.md).

The frozen threshold tuner selected the loose policy only because the train
window had no eligible entries. The 2026-08-19 onward holdout had one trade
and the same +1.765% pre-stress result. With one event, no observed funding
income, and no margin buffer, this lane is **data-ready but unvalidated**.

## 3. Low-turnover cross-sectional portfolio

[`cross_sectional_portfolio.py`](../research/evaluation/cross_sectional_portfolio.py)
now includes a small frozen train/holdout tuner. It retains the existing
point-in-time membership join, momentum/reversal/liquidity/volatility factors,
BTC beta control, concentration caps, and shared-wallet cost accounting.

The screen used Coinbase-native 4-hour candles from 2025-01-01 through
2026-09-26 for BTC, ETH, SOL, XRP, and DOGE. Because a sourced historical
listing registry was not available for this local screen, membership was a
static research fixture effective from 2025-01-01; this is not yet a
point-in-time universe proof.

With a Coinbase-style 60 bps fee, 5 bps spread, and 10 bps slippage, the
selected low-turnover policy used 168-bar momentum, 168-bar volatility,
two longs, and a 42-bar rebalance. It returned -9.34% in the 2025 training
window and -13.90% in the 2026 holdout, with 23.84% holdout drawdown. The
cross-sectional sleeve is therefore not a current profit candidate at the
tested cost assumptions.

## Decision and next gate

| Lane | Implementation | Frozen result | Decision |
| --- | --- | ---: | --- |
| Momentum reconstruction | Freqtrade strategy plus causal tuner | Freqtrade -0.28%; tuned holdout -25.43% | Reject as a historical-winner replay; keep as a source-restoration scaffold |
| Same-venue carry | Spot/perp/index/funding evaluator, tuner, and metrics context | 1 loose trade per asset; stressed BTC -0.40%, ETH -1.19% | Block until margin data, measured costs, and funding-duration trades |
| Cross-sectional portfolio | PIT-aware evaluator plus cost-aware tuner | -13.90% 2026 holdout | Reject at Coinbase-style costs; improve universe and execution inputs before retuning |

The practical conclusion is not “tune harder.” The first lane needs the exact
missing source or a deliberately new specification. Carry needs months of
venue-matched spot/perpetual/index/funding/open-interest and liquidation data.
The portfolio lane needs a real historical membership file, venue-specific
execution curves, and a shared-wallet replay before any new parameter search.

If this makes money, tell me lol. If it loses money, tell me that too—the point
is to measure reality, not promise returns.
