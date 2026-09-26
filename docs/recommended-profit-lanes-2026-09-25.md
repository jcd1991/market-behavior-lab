# Recommended profit lanes — 2026-09-25

This report records the implementation and first validation pass for the
research lanes recommended after the standalone breakout result. It is a
screening report, not a profitability claim.

## Scope and data

- Freqtrade: `2026.2-dev-d07ba71e3`.
- Local Freqtrade-style spot candles for BTC, ETH, SOL, XRP, BNB and DOGE.
- Native timeframe: `4h`.
- Available window: `2024-06-01` through `2026-04-13`.
- Freqtrade fee: `0.10%` per side.
- Starting balance: `1,000 USDT`.
- Maximum open trades: `2`.
- Forward lock: parameters selected on `2024-06-01` through `2025-06-30`,
  then evaluated without retuning from `2025-07-01` through `2026-04-13`.
- Additional cost sensitivity is modeled after the Freqtrade export; it is not
  timestamp-matched spread or slippage.

The local files carry historical venue labels from prior research. This pass
does not re-verify that every file is execution-grade Binance.US history. The
results must therefore be treated as local labeled screens until matched venue
provenance is re-established.

## Implemented lanes

### Multi-horizon breakout

Added:

- `user_data/strategies/BreakoutEnsembleSpot.py`
- `user_data/strategies/BreakoutEnsembleSpotSlow.py`

The default uses 12/24/48/96-bar Donchian horizons and requires three of four
breakouts. The slow candidate uses 18/36/72/144 bars and two votes. The slow
candidate is a separate class so its parameters are visible and frozen during
forward testing.

### Crash-state and liquidity controls

Added:

- `user_data/strategies/CostAwareBreakoutEnsembleSpot.py`
- Existing `user_data/strategies/StandaloneBreakoutTrendSpotGuarded.py` was
  re-run as the broad BTC trend guard.
- `research/evaluation/recommended_lanes.py` includes a causal trend/drawdown
  position-size overlay and a shared-wallet approximation.

The cost-aware lane requires a rolling quote-volume ratio and a minimum
breakout move. The overlay is tested as a sizing control, not as a new signal.

### Liquid cross-sectional momentum

Added:

- `user_data/strategies/LiquidMomentumSpot.py`

The strategy ranks each pair against the contemporaneous configured universe,
rebalances on a UTC schedule, requires positive local trend and a rolling
quote-volume ratio, and exits when relative momentum or trend fails.

The independent portfolio evaluator in
`research/evaluation/recommended_lanes.py` also tests holdings, rebalance
frequency, lookback and liquidity-floor combinations. That evaluator uses a
static local universe and is not yet a point-in-time membership test.

## Native Freqtrade results

All results below use the same spot configuration, fee and two-trade limit.

| Lane | Full window | Forward window | Full +40 bps extra cost | Reading |
| --- | ---: | ---: | ---: | --- |
| `BreakoutEnsembleSpot` | +4.09% / 107 trades | +1.04% / 37 | +3.24% | Positive screen, modest forward edge |
| `BreakoutEnsembleSpotSlow` | +5.73% / 127 | +1.22% / 46 | +4.72% | Best new breakout candidate, late weakness remains |
| `CostAwareBreakoutEnsembleSpot` | +4.19% / 106 | +1.04% / 37 | not separately promoted | Filters removed little because the local candles already passed them |
| `StandaloneBreakoutTrendSpotGuarded` | +5.95% / 108 | +1.49% / 41 | prior report: positive at +40 bps | BTC trend guard improves the full screen versus some baselines but does not eliminate forward risk |
| `LiquidMomentumSpot` | +1.52% / 279 | -1.59% / 114 | -0.70% | Reject as a standalone sleeve for now |

The slow breakout's sequential native Freqtrade windows were:

| Window | Return | Trades | Max drawdown |
| --- | ---: | ---: | ---: |
| 2024-06-01–2025-01-01 | +4.90% | 44 | 0.51% |
| 2025-01-01–2025-10-01 | +1.38% | 54 | 1.23% |
| 2025-10-01–2026-04-13 | -0.68% | 31 | 0.85% |

The momentum windows were +3.69%, +0.12% and -2.30% respectively. The final
window is negative for both lanes, so neither is portable-proof.

## Bounded tuning

The offline evaluator ran a predeclared grid of:

- Breakout horizons: 12/24/48/96, 18/36/72/144 and 24/48/96/192.
- Breakout votes: 2 or 3.
- Minimum observed move: 0, 20 or 40 bps.
- Momentum lookbacks: 18, 42 or 84 bars.
- Momentum rebalance intervals: 3, 6 or 12 bars.
- One or two holdings.
- Quote-volume floors: 0.5x or 1.0x rolling median.

The selected slow breakout grid winner was positive in its training window and
returned +12.12% in the independent offline forward simulation. The native
Freqtrade implementation returned +1.22% in the same broad forward period.
This difference is expected: the offline evaluator uses next-open fills and a
shared-wallet allocation, while the Freqtrade run uses the documented
`stake_amount` and Freqtrade's own trade scheduler. The native Freqtrade
number is the one to use for strategy comparison.

The selected momentum grid winner returned +102.19% in the training window but
-17.13% in its forward simulation. This is a clear overfitting warning, not a
tuning success.

## Data-blocked lanes

### Cash-and-carry

The existing fail-closed carry evaluator was run against the available BTC
spot, perpetual and funding files. It rejected the run because a same-venue
historical index file was missing. No CoinGecko, other-venue index, or current
snapshot was substituted.

Carry remains a worthwhile next lane only after acquiring synchronized same-
venue spot, perpetual, index, mark, funding, fees, borrow/collateral and
liquidation-buffer history.

### Order-flow and market making

The checkout still lacks a complete timestamp-matched historical trade and L2
replay set. OHLCV cannot reconstruct queue position, aggressor flow, depth or
liquidation events. Those lanes remain deferred.

### Point-in-time universe

The momentum implementation uses the configured six-pair static universe. It
must not be presented as a point-in-time universe result until listing,
delisting and liquidity membership snapshots are available.

## Decision

The slower breakout ensemble is the only new candidate worth carrying forward,
and it should remain a research sleeve rather than replace the current
baseline. The crash-state overlay reduced the offline late-window drawdown but
did not make the late window profitable. The liquidity filter did not change
the native forward result on these candles. Liquid momentum failed its locked
forward test and should not be combined into a shared wallet yet.

Next gates are venue-matched minute costs, a second independent venue, and a
larger point-in-time liquid universe. The next portfolio combination should be
tested only after those data gates, with frozen breakout parameters and explicit
shared-wallet concentration caps.

## Reproduction

Native strategy discovery:

```bash
freqtrade list-strategies --userdir "$LAB_ROOT/user_data"
```

Native Freqtrade example:

```bash
freqtrade backtesting \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.binanceus.spot.example.json" \
  --datadir "$LAB_ROOT/user_data/data" \
  --strategy BreakoutEnsembleSpotSlow \
  --timerange 20240601-20260414 \
  --export trades
```

Offline lane report:

```bash
python research/evaluation/recommended_lanes.py \
  --data-dir user_data/data \
  --output research/reports/generated/recommended-lanes.json \
  --start 2024-06-01 \
  --end 2026-04-14
```

The generated JSON is intentionally ignored because local market data and
machine-specific backtest artifacts are not part of the public repository.
