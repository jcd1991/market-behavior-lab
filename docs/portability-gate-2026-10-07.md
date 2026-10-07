# Portability gate: native OKX spot

This report records the frozen portability test for the two lanes that remain
worth carrying forward: the slower cross-sectional portfolio and a shared
wallet containing the slow breakout and volatility-managed trend sleeves.

The reproducible command is:

```bash
.venv/bin/python3 \
  scripts/run_portability_gate.py
```

The command reads the ignored local OKX 15-minute candle cache and writes the
generated JSON report to:

```text
research/reports/generated/portability-gate-2026-10-07.json
```

The checked-in findings below are reproduced from that run. A positive result
is still a portable research screen, not a profitability or execution claim.

## Data and method

The test used five synchronized native OKX spot files:

| Field | Value |
| --- | --- |
| Venue | OKX spot |
| Native data | 15-minute OHLCV |
| Pairs | BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT, DOGE/USDT |
| Window | 2024-06-01 00:00 UTC to 2026-09-22 17:30 UTC |
| Rows per pair | 80,999 |
| Evaluation bars | 1h for cross-sectional; 4h for slow breakout; 1h for VMT |
| Universe | Static five-pair screen; PIT listing/liquidity history unavailable |
| Fill model | Next-bar open; modeled fees, spread, and slippage |

The OKX venue was not globally unseen in the project, but these exact frozen
policies were not tuned on this OKX panel. The native files are therefore
`unseen_for_frozen_policies`, not a claim of a never-used venue.

The short OKX public websocket capture contains 337 messages over 20 seconds
for BTC/USDT and ETH/USDT. It is marked `execution_truth: false`, and there is
no full-period minute-trade or L2 history. It was included in the JSON report
as a data-quality reference only; it does not set the historical cost model.

## Results

### Slower cross-sectional portfolio

The policy was frozen from the earlier screen:

```text
lookback=168, reversal_window=24, volatility_window=168,
rebalance_every=42, longs=2, shorts=0, target_vol=0.30,
max_pair_weight=0.25, max_abs_beta=0.35
```

At the base modeled cost of 10 bps per side plus 5 bps spread and 5 bps
slippage round trip:

| Window | Return | Max drawdown |
| --- | ---: | ---: |
| 2024-06-01 to 2026-09-22 | -9.10% | 31.92% |
| 2024-06-01 to 2025-12-01 | +4.82% | 20.30% |
| 2025-12-01 to 2026-09-22 | -11.86% | 24.43% |

The cross-sectional policy is not portable on this evidence. The failure is
not explained only by costs: the later OKX window is negative at the base cost
case, and the return deteriorates to -17.64% under the 50 bps stress case.
The cross-sectional screen also lagged the no-trading-cost equal-weight
buy-and-hold reference, which returned +27.05% over the same full window.

### Breakout plus volatility-managed trend

The breakout sleeve used the frozen slow horizons `(18, 36, 72, 144)` on 4h
bars, two votes, a 0.2% breakout buffer, ATR cap 0.20, and EMA-24 exit. The
volatility sleeve reconstructed the saved `VolatilityManagedTrendCashSpot`
parameters without retuning: fast 72, slow 281, annualized volatility cap 2.33,
target volatility 0.14, score threshold 0.92, liquidity ratio 1.95, and the
saved 0.5% minimum cost-plus-edge gate.

The shared wallet used equal 50/50 sleeve budgets, three open positions, and a
25% per-pair cap. The trade panel contained 252 breakout trades and 198
volatility-managed trades before overlap/cap rejection.

| Cost case | Full window | Forward from 2025-12-01 | Forward max drawdown |
| --- | ---: | ---: | ---: |
| 10 bps/side + 5 bps spread + 5 bps slippage | +19.92% | +1.11% | 6.99% |
| 15 bps/side + 10 bps spread + 10 bps slippage | +12.76% | -1.28% | 8.72% |
| 20 bps/side + 20 bps spread + 20 bps slippage | +2.79% | -4.77% | 11.47% |

The breakout sleeve supplied most of the result. At the base cost it produced
about +47.74% as a standalone shared-wallet screen, while the reconstructed
volatility sleeve produced +6.29%. In the combined forward window, the
breakout sleeve contributed +25.59 balance units while the volatility sleeve
lost 14.53 balance units. This is diversification/risk-control evidence, not
proof that the volatility sleeve adds alpha.

## Decision

The cross-sectional portfolio should not be promoted to a portable product
based on this OKX run. The breakout/volatility combination is the stronger
portable lead, but only at the base modeled cost and with a very small forward
margin. It fails the conservative 50 bps forward stress, so it has not passed
the portable-profitability gate.

The next gate is not more parameter tuning. It is venue-matched minute trades,
L2 books, fee tiers, and a second frozen forward window. The exact signals and
fills must be reconciled against those observations before this result can be
called execution-relevant.
