# Sleeve synergy screen — 2026-09-25

This screen tests whether the revised sleeves add useful diversification to
the strongest earlier research lane, `MomentumRegimeBasket15mLb30`.

It is a shared-wallet approximation using independent Freqtrade trade exports,
not a production multi-strategy bot. All candidates use the same Binance.US
spot universe and the same historical windows. The allocator uses a 1,000 USDT
wallet, three global positions, a 40% pair cap, overlap rejection, weighted
sleeve budgets, and 0/20/40 bps additional round-trip cost stress.

## Key comparison

| Combination | Full window at +20 bps | 2025 holdout at +20 bps | Holdout drawdown | Decision |
| --- | ---: | ---: | ---: | --- |
| MomentumRegime only | +66.30% | +8.68% | 14.16% | Baseline independent winner |
| MomentumRegime + original breakout | +56.77% | +6.29% | 13.42% | Lower return, modest risk reduction |
| MomentumRegime + crash-state breakout | **+65.87%** | **+10.39%** | 13.46% | Best current synergy candidate |
| MomentumRegime + weekly momentum | +41.57% | +3.27% | 14.02% | Reject; weak sleeve reduces quality |

The holdout result is the important one. The crash-state breakout is better
used as the replacement breakout sleeve, not stacked as a second copy of the
same breakout family. On the 2025 holdout it improved return by approximately
4.1 percentage points over the original breakout blend at the 20 bps stress
level while leaving drawdown essentially unchanged.

At 40 bps additional cost, the MomentumRegime + crash-state combination still
returned +8.01% on the holdout. That is encouraging screening evidence, not a
portable-profit claim: the MomentumRegime lane has its own provenance and
forward-validation limitations, and the allocator consumes precomputed trades.

## What should and should not be added

### Add now as a research portfolio candidate

Use:

- `MomentumRegimeBasket15mLb30` as the independent momentum sleeve;
- `BreakoutCrashStateSpot` as the single breakout/trend sleeve;
- the execution/liquidity gate as a portfolio-wide entry filter;
- shared capital, pair-overlap rejection, and concentration caps.

The initial frozen screen is 70% momentum and 30% crash-state breakout. The
weight is a research allocation, not a recommended investment allocation.

### Do not stack

`StandaloneBreakoutTrendSpot`, `BreakoutEnsembleSpotSlow`, and
`BreakoutCrashStateSpot` should not all run as separate alpha sleeves. The
original and slow breakout exports were identical on the 2025 holdout in this
dataset, demonstrating that they are operationally redundant there. The crash
state should replace the ordinary breakout sleeve or act as its risk overlay.

`LiquidMomentumWeeklySpot` should remain a shadow sleeve. Its locked forward
result was negative, and the Freqtrade lookahead tool flags its cross-sectional
universe calculation when the verification run is isolated to individual
pairs.

### Defer until data is complete

- Cash-and-carry: add only after same-venue funding, basis, borrow,
  collateral, and liquidation-buffer history overlaps the spot/perpetual data.
- Residual pairs: add only after the two-leg book is profitable on a frozen
  holdout with funding, borrow, and synchronized execution costs.
- Lead-lag: add only after archived timestamped trades or L2 books exist.
- Options: add only after paired call/put history, IV surfaces, hedge fills,
  and option transaction costs exist.

## Integration boundary

This should not be merged into `RegimeRouted` as another signal branch. The
positive result comes from sleeve separation and capital competition. The next
implementation should be a single synchronized allocator that receives frozen
signals from the momentum and crash-state sleeves, then applies one wallet,
one position budget, pair caps, costs, and execution gates. Until that exists,
the current result is a portfolio research screen only.

## Reproduction inputs

The screen used these local ignored exports:

- `MomentumRegimeBasket15mLb30`, Binance.US, 2024-06-13–2025-12-02;
- `StandaloneBreakoutTrendSpot`, Binance.US, same window;
- `BreakoutEnsembleSpotSlow`, same window;
- `BreakoutCrashStateSpot`, same window;
- `LiquidMomentumWeeklySpot`, same window.

The raw market data and backtest exports remain ignored and were not added to
the public repository.
