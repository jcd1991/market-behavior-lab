# Binance sleeve refresh — 2026-09-28

This report records a fresh Binance.US-labelled spot screening pass and a
shared-wallet replay of the existing positive research lane with additional
strategies. It is a research result, not a live-trading recommendation.

The local Freqtrade configuration identifies the venue as `binanceus`, and the
backtests use the existing local candle cache. The project does not claim that
every cached file is execution-grade Binance.US history; venue provenance must
be re-verified before promotion. The runs used six USDT pairs, a simulated
1,000 USDT wallet, two Freqtrade slots, and a 0.10% fee. The shared-wallet
replays add a 20 bps round-trip stress on top of each export and cap any one
pair at 40% of the wallet.

## Fresh Binance-labelled strategy screens

Window: **2024-06-13 through 2025-12-02**. Parameters were not retuned for
this report.

| Sleeve | Timeframe | Trades | Return | Max drawdown | Profit factor | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `StandaloneBreakoutTrendSpot` | 4h | 104 | +5.95% | 1.17% | 2.38 | Positive screen; must pass forward data |
| `BreakoutCrashStateSpot` | 4h | 78 | +4.77% | 0.96% | 2.80 | Positive screen; overlaps breakout |
| `RiskManagedCrossSectionalTrendSpotTuned` | 1h | 203 | +3.21% | 1.42% | 1.55 | Positive but higher turnover |
| `LiquidMomentumSpot` | 4h | 225 | +2.80% | 1.48% | 1.32 | Weak positive; do not promote yet |
| `VolatilityManagedTrendCashSpot` | 1h | 59 | +0.48% | 0.36% | 1.47 | Defensive/near-flat sleeve |

These are direct Freqtrade results with the same cost configuration, not the
older historical momentum export. The older `MomentumRegimeBasket15mLb30`
archive remains a separate provenance lane and must not be treated as a
reproduction of the new strategy implementation.

## 2026 forward check

Window: **2025-12-02 through 2026-04-13**, using the available 4-hour data.

| Sleeve | Trades | Return | Max drawdown | Result |
| --- | ---: | ---: | ---: | --- |
| `StandaloneBreakoutTrendSpot` | 21 | -0.36% | 0.39% | Failed this forward window |
| `BreakoutCrashStateSpot` | 15 | -0.45% | 0.45% | Failed this forward window |
| `LiquidMomentumSpot` | 51 | -1.49% | 1.67% | Failed this forward window |

The 1-hour cache used by the other two sleeves ends on 2025-12-09, so their
apparent “2026” run is only a seven-day fragment: `RiskManagedCrossSectionalTrendSpotTuned`
made 0 trades and `VolatilityManagedTrendCashSpot` made 2 trades for -0.03%.
That is insufficient to call either a 2026 forward result. More complete
1-hour venue data is required.

## Shared-wallet combinations

The earlier archived momentum export was combined with the fresh sleeves using
UTC event ordering, overlap rejection, three global slots, 40% pair caps, and
the additional 20 bps round-trip stress.

| Combination | Full-window return | Full-window DD | 2025 holdout return | 2025 holdout DD |
| --- | ---: | ---: | ---: | ---: |
| Momentum 70% + crash 30% | **+65.87%** | 14.21% | **+6.87%** | 13.68% |
| Momentum 70% + standalone breakout 30% | +56.77% | 13.70% | +3.07% | 13.49% |
| Momentum 55% + crash 25% + breakout 20% | +47.28% | 11.07% | +3.52% | 10.92% |
| Momentum 60% + crash 25% + RCT 15% | +43.01% | 10.38% | +2.20% | 9.98% |
| Momentum 60% + crash 25% + VMT 15% | +47.75% | 12.39% | +1.65% | 12.29% |
| Extended six-sleeve mix | +42.09% | **5.26%** | +4.43% | **5.04%** |

At 40 bps of extra round-trip stress, the 2025 holdout was +4.56% for the
momentum/crash pair, +1.64% for the three-sleeve momentum/crash/breakout mix,
and +3.24% for the extended mix. At 60 bps, the three-sleeve mix was -0.20%
while the extended mix remained +2.07%. The extended mix buys drawdown
reduction, not maximum return, and its result is still dependent on the old
momentum export.

## Frozen allocation search

The predeclared grid now includes standalone breakout and liquid momentum as
optional sleeves. It searched 336 allocation/cost-control combinations on
2024-06-13 through 2025-01-01 and froze the selected result for the 2025
holdout. Selection was based on training return minus half the training
drawdown, with at least 25 accepted trades.

The selected allocation was still the simple momentum/crash pair:

- 70% historical momentum export;
- 30% crash-state breakout;
- no liquidity gate, volatility target, or cash reserve;
- training: +56.04% with 4.43% drawdown;
- locked 2025 holdout: +6.87% with 13.68% drawdown.

That is evidence against adding sleeves merely because their full-window
curves are positive. The added sleeves are currently better viewed as
diversification candidates or defensive risk controls, not proven return
enhancers.

## How new strategies should be added

New strategies should enter as independent, venue-labelled exports rather than
being folded directly into `RegimeRouted`:

1. Implement or import the strategy with its original parameters and explicit
   spot/futures compatibility.
2. Run it natively in Freqtrade on the same venue, pair universe, fees, and
   timerange as the comparison lanes.
3. Export trades and add it to the shared-wallet matrix as a named sleeve.
4. Reconcile overlapping trades, shared capital, pair caps, and extra
   spread/slippage cost.
5. Freeze allocations on a training window and judge only the untouched
   holdout and a second venue.
6. Promote a sleeve only if it contributes after costs without requiring the
   older momentum winner to carry the result.

The matrix now supports `--breakout` and `--lms` inputs in addition to the
existing `--momentum`, `--crash`, `--vmt`, and `--rct` inputs. Its optional
scenarios include `core_plus_standalone_breakout`,
`core_plus_liquid_momentum`, and `extended_all_alpha`.

## Next research gate

The Binance forward screen does not justify adding another trend copy. The
next useful work is:

- acquire complete 1-hour and 15-minute venue-matched Binance data through the
  forward period;
- measure actual spread and slippage instead of a generic stress;
- restore or replace the missing exact source for the historical momentum
  winner;
- test an independent sleeve with different payoff mechanics, such as
  same-venue cash-and-carry or true two-leg residual hedging, only when its
  required history is complete;
- keep the 2026 forward window locked while researching, and do not retune it.

If this makes money, tell me lol. If it loses money, tell me that too—the point
is to measure reality, not promise returns.
