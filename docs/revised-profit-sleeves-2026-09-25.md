# Revised profit sleeves — 2026-09-25

This report records the first implementation pass for seven research
directions: same-venue cash-and-carry, slow liquid momentum, market-neutral
residual pairs, defensive crash-state allocation, execution/liquidity gating,
lead-lag screening, and options volatility research.

The results are research evidence, not a profitability claim. A positive
historical backtest is not proof of live tradability.

## What was implemented

| Sleeve | Implementation | Runtime | Data requirement |
| --- | --- | --- | --- |
| Same-venue cash-and-carry | `evaluate_carry_contract` | Offline research | Synchronized spot, perpetual, index, funding, margin and cost history |
| Slow liquid momentum | `LiquidMomentumWeeklySpot` | Freqtrade spot | Static configured universe, 4h candles, costs |
| Market-neutral residual pairs | `simulate_two_leg_residual` | Offline research | Same-venue synchronized legs, two-leg fills and hedge ratio |
| Defensive crash-state allocation | `BreakoutCrashStateSpot` | Freqtrade spot | BTC market-state overlay plus spot candles |
| Execution/liquidity overlay | `CostAwareBreakoutEnsembleSpot`, `apply_execution_gate` | Freqtrade and offline | Volume, expected move, fees, spread and slippage assumptions |
| Lead-lag execution | `lead_lag_screen` | Offline diagnostic | Timestamped trades or book events; not OHLCV reconstruction |
| Options volatility | `fetch_deribit_option_chain.py`, `evaluate_delta_hedged_straddle` | Offline diagnostic | Historical option marks, paired calls/puts and hedge fills |

The first five can be evaluated against candle research. Lead-lag and options
are deliberately not represented as ordinary OHLCV strategies: their signal
and fill semantics require event-level data that candles cannot recreate.

The existing Freqtrade `FundingBasisCarry` lane was also run on the OKX
2024–2025 backtest window. It produced zero trades because the required
funding and index files did not overlap that window. That zero is an expected
fail-closed outcome, not a carry loss estimate.

## Data acquisition and provenance

The OKX backfill downloaded spot and perpetual BTC candles plus perpetual mark
and index candles for `2024-06-01` through `2025-12-02`. The exchange rate limit
was encountered during retrieval, but the resulting candle files cover the
requested range. OKX funding history returned only a recent 2026 slice, not an
overlapping historical series. The carry evaluator therefore rejects the
historical run rather than borrowing a rate from another venue.

The repository also contains ignored local captures from Coinbase, Kraken and
OKX public trade/order-book channels. They are short discovery captures, not
historical execution truth. Binance public WebSocket capture was unavailable
in the run because the endpoint returned HTTP 451.

Options use a bounded public Deribit chain snapshot. Deribit documents its
public HTTP and WebSocket APIs in the [official API documentation](https://docs.deribit.com/index.html).
The snapshot is useful for validating the schema and discovering instruments;
it is not a historical option surface or a fill dataset.

## Native Freqtrade results

These runs use the local six-pair spot universe, 4h candles, a 0.10% fee per
side, 1,000 USDT starting balance and at most two open trades. The files are
historical venue-labelled research data; execution-grade venue provenance is
not re-established by this report.

| Strategy | Full `2024-06-01`–`2026-04-13` | Locked forward `2025-07-01`–`2026-04-13` | Max forward drawdown | Reading |
| --- | ---: | ---: | ---: | --- |
| `LiquidMomentumWeeklySpot` | +3.71%, 189 trades | **-0.39%, 69 trades** | 1.79% | Reject as a standalone sleeve until a new independent dataset supports it |
| `BreakoutCrashStateSpot` | +4.43%, 95 trades | **+1.35%, 35 trades** | 0.51% | Best revised candidate, but still too small and venue-specific to promote |

The crash-state strategy is a risk overlay on the existing breakout ensemble,
not a claim that a regime detector creates new alpha. It suppresses entries and
scales stake when BTC is below its broad trend or has entered a drawdown state.

## Offline lane results

### Cash-and-carry: data-gated

The exact-venue OKX run found no overlap between the 2024–2025 spot/perpetual/
index candles and the available funding observations. Result: **ineligible,
no exact overlap**. This is a useful negative result: carry cannot be evaluated
without same-venue funding and financing history.

### Residual pair: negative screen

The synchronized OKX-labelled BTC/ETH perpetual candle screen used a 240-bar
rolling hedge ratio, 1.8 entry z-score, 0.35 exit z-score, 0.75 minimum
correlation, 120-bar maximum half-life and 30 bps two-leg cost. It produced 12
entries over 13,198 observations and a **-9.74%** close-price screen result,
with approximately 9.74% maximum drawdown. This is not a reason to discard
market-neutral research permanently, but it is a reason not to promote this
pair or retune it on the same window.

### Execution/liquidity gate: useful filter, not a profit result

On the OKX BTC 4h breakout feature screen, an all-in round-trip assumption of
55 bps accepted 55 of 90 candidate signals at a 1.0x rolling quote-volume
floor. This measures how many signals survive a cost/liquidity gate; it does
not measure the profitability of the filtered strategy. The gate must be
connected to a full trade replay before promotion.

### Lead-lag: diagnostic only

The Coinbase BTC-USD to ETH-USD public trade capture produced only 25 one-second
bars of overlap. At a 4 bps modeled round-trip cost, the best lag screen was
**-1.72%** at five seconds. The result is not statistically meaningful and the
capture is explicitly labelled non-historical. Longer same-session or archived
trade data is required before a lead-lag sleeve can be judged.

### Options: schema validated, history absent

The Deribit snapshot returned eight current instruments and validates the
option fields, but each instrument has one observation. The delta-hedged
straddle evaluator therefore produces zero simulated holding periods. Paired
call/put history, underlying hedge fills, IV surface history, and transaction
costs are required before options research is eligible.

## Bias and stability checks

`BreakoutCrashStateSpot` passed the Freqtrade lookahead analysis on the locked
forward sample and its indicator-only recursive analysis reported no variance.
The same recursive check reported no variance for the weekly momentum EMA.

`LiquidMomentumWeeklySpot` was flagged by Freqtrade's lookahead tool on the
cross-sectional `lms_universe_median` and derived signal columns. The strategy
uses only same-timestamp, backward-return calculations, but the Freqtrade
lookahead tool slices the verification run down to individual pairs; that
changes the available cross-sectional universe and therefore changes the
median. This is a real validation limitation, not a pass. The weekly
cross-sectional lane remains unpromoted until it has a dedicated multi-pair,
point-in-time walk-forward validator that preserves the universe on every
slice.

## Promotion decisions

1. Keep `BreakoutCrashStateSpot` as a frozen candidate for a second venue and
   measured spread/slippage test.
2. Keep `CostAwareBreakoutEnsembleSpot` as an execution-control component, not
   as independent alpha.
3. Do not promote `LiquidMomentumWeeklySpot` based on the full-window result;
   its locked forward result is negative.
4. Do not tune the residual pair on this same sample. Acquire a separate
   formation/evaluation split and implement actual two-leg execution before
   revisiting it.
5. Acquire historical same-venue funding, borrow/collateral and liquidation
   data before claiming cash-and-carry economics.
6. Acquire timestamped trades and L2 books before claiming lead-lag or market-
   making economics.
7. Treat the Deribit option capture as a contract/discovery check only.

## Reproduction

Run the focused contracts and layout checks:

```bash
python -m pytest tests/test_revised_sleeves.py tests/test_recommended_lanes.py tests/test_project_layout.py
```

Capture a bounded options snapshot:

```bash
python scripts/fetch_deribit_option_chain.py \
  --currency BTC --limit 12 \
  --output user_data/data/options/deribit-btc-snapshot.json
```

Run the native strategies through the separately installed Freqtrade checkout:

```bash
freqtrade backtesting \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.binanceus.spot.example.json" \
  --datadir "$LAB_ROOT/user_data/data" \
  --strategy BreakoutCrashStateSpot \
  --timerange 20250701-20260413 \
  --fee 0.001 --export none
```

Local market data, captures, snapshots and generated backtest files remain
ignored and are not part of the public repository.
