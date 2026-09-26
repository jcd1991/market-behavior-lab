# Synergistic sleeve matrix — 2026-09-26

This report evaluates whether the newer defensive and data-driven sleeves add
anything to the two strongest current Binance.US-labelled spot research
lanes:

- `MomentumRegimeBasket15mLb30`;
- `BreakoutCrashStateSpot`.

The result is a shared-wallet approximation over independent Freqtrade trade
exports. It is not a production multi-strategy bot and is not a promise of
profitability.

## Matrix contract

Each run used a 1,000 USDT wallet, three global positions, a 40% pair cap,
pair-overlap rejection, weighted sleeve budgets, and an additional 20 bps
round-trip cost stress on top of the Freqtrade export. The full window is
2024-06-13 through 2025-12-02. The locked holdout is 2025-01-01 through
2025-12-02.

The matrix permits different signal timeframes to compete for the same wallet,
but it does not mix venues or market types. All alpha exports use the same
Binance.US-labelled spot universe. The trade exports are ignored local
artifacts; they are not public repository inputs.

## Frozen matrix results

| Scenario | Full return | Full DD | 2025 holdout return | Holdout DD | Reading |
| --- | ---: | ---: | ---: | ---: | --- |
| Momentum + crash-state breakout | **+65.87%** | 14.21% | **+10.39%** | 13.46% | Best current synergy |
| Add volatility-managed cash sleeve | +47.75% | 12.39% | +4.39% | 12.23% | Defensive but dilutive |
| Add baseline cross-sectional trend | +43.98% | 8.28% | +6.05% | 7.97% | Lower return, materially lower DD |
| Add all four alpha sleeves | +43.25% | 8.93% | +7.13% | 8.70% | Diversifies, but does not beat core |
| All alpha + liquidity gate | +5.78% | 7.47% | **-5.44%** | 7.46% | Current gate is too restrictive |
| All alpha + 25% volatility target | +30.44% | **2.78%** | +3.91% | **2.64%** | Useful risk overlay, not alpha |
| All alpha + gate + volatility target + 20% cash | +1.71% | 1.70% | **-0.73%** | 1.54% | Capital defense, not a return sleeve |

The central finding is unchanged: the crash-state breakout is useful when it
replaces the ordinary breakout sleeve. Adding every available positive screen
does not automatically improve the portfolio. Volatility targeting makes the
equity curve less exposed, but it also removes much of the return. The current
liquidity filter rejects too many signals and needs measured spread/slippage
calibration before it can be used as a hard gate.

## Parameter tuning

A coarse, pre-declared grid was tuned on 2024-06-13 through 2025-01-01. It
searched allocation choices, liquidity thresholds, volatility targets, and
cash reserves, then replayed the selected setting unchanged on 2025.

The training selection chose the existing 70% momentum / 30% crash-state
combination with no additional overlay. It produced +56.04% in the training
window and +6.87% when the same full-window exports were filtered to the
holdout. This is a useful anti-overfitting result: the grid did not discover a
new control that beat the frozen core under the stated score.

The cross-sectional sleeve received a separate 40-epoch Freqtrade hyperopt
screen on the 2024 training window. Its best configuration was preserved in
`RiskManagedCrossSectionalTrendSpotTuned` rather than replacing the baseline:

```text
momentum_bars=95
sharpe_bars=837
long_rank=0.63
short_rank=0.14
min_edge=0.010
min_liquidity_ratio=1.20
target_vol=0.52
```

The tuned lane improved its standalone native screen to +3.21% full and
+1.94% on the 2025 holdout, compared with +2.11% and +1.29% for the baseline
reproduction. Inside the shared wallet it was worse than the baseline
cross-sectional sleeve: the core-plus-cross-sectional blend returned +4.65%
on the 2025 holdout, versus +6.05% with the baseline. It remains a research
candidate, not a promoted portfolio component.

The volatility-managed cash sleeve produced no admissible improvement in its
40-epoch training hyperopt screen. Its frozen reproduction was approximately
+0.48% full and +0.07% on the 2025 holdout, so it remains a defensive shadow
sleeve.

## New same-venue data acquisition

To make the carry lane testable without cross-venue substitution, a bounded
Binance Global August 2026 sample was downloaded from the official public
archive and normalized separately:

- BTC/USDT spot 1-minute candles: 44,640 rows;
- BTC/USDT:USDT perpetual 1-minute candles: 44,640 rows;
- perpetual index 1-minute candles: 44,640 rows;
- perpetual mark 1-minute candles: 44,640 rows;
- funding observations: 93 rows.

The archives were checksum-verified. The local fetcher now namespaces spot
and USD-M futures files separately so a futures download cannot overwrite a
spot archive. The derivative normalizer preserves UTC, the pair contract,
venue, source, and `execution_truth: false`.

## Carry result: screened, not promoted

The one-month Binance Global sample was evaluated with 2 bps fee per side,
2 bps spread, 2 bps slippage, and 1 bps safety stress. With a 0.10% entry
basis, 0.03% exit basis, and 0.001% minimum funding signal, it produced:

- 5 entries and 5 exits;
- +2.33% cumulative close-price screen result;
- mean basis -0.0396%;
- no margin/liquidation buffer history;
- no borrow or collateral-cost history;
- no open-interest history;
- zero funding observations counted during the held intervals under these
  signals.

That last point matters: this sample is primarily a basis-convergence screen,
not evidence of a repeatable funding-income strategy. It is too short and
incomplete for promotion. The data is useful for validating the contract and
coverage pipeline, not for claiming carry profitability.

Cross-venue dispersion and options remain blocked. The current event captures
are short discovery sessions, and the options artifact is a current Deribit
chain snapshot rather than historical IV, paired option, and hedge-fill data.

## Decision

Keep the following as the current research portfolio candidate:

1. `MomentumRegimeBasket15mLb30` at the center of the allocation;
2. `BreakoutCrashStateSpot` as the single breakout sleeve;
3. shared-wallet overlap and concentration controls;
4. volatility targeting as an optional risk overlay when reducing drawdown is
   more important than maximizing return.

Do not promote the liquidity gate, VMT, tuned RCT, cross-venue dispersion,
options, or carry screen until they have longer venue-matched data and an
independent forward window. The next meaningful gate is measured fill quality
and a third venue, not another parameter sweep.

## Reproduction

Run the focused tests:

```bash
python -m pytest \
  tests/test_synergistic_matrix.py \
  tests/test_normalize_binance_derivatives.py \
  tests/test_revised_sleeves.py
```

The generated matrix files are local and ignored:

- `research/reports/generated/synergistic_matrix_full.json`;
- `research/reports/generated/synergistic_matrix_2025.json`;
- `research/reports/generated/synergistic_matrix_tuned_full.json`;
- `research/reports/generated/synergistic_matrix_tuned_2025.json`.

If this makes money, tell me lol. If it loses money, tell me that too—the
point is to measure reality, not promise returns.
