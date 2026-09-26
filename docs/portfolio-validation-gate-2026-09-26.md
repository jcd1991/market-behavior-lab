# Portfolio validation gate — 2026-09-26

This pass tests whether the current positive research lead is robust enough to
deserve another round of strategy work. The lead is the historical combination
of:

- `MomentumRegimeBasket15mLb30`, the higher-return momentum sleeve; and
- `BreakoutCrashStateSpot`, the crash-state breakout sleeve.

The standard is deliberately higher than “the equity curve went up.” The lead
must survive one shared wallet, a locked forward window, concentration checks,
and an exact replay on a third venue. A result that fails one of those checks
remains a research lead rather than a product claim.

## Validation inputs

| Lane | Venue/data | Window | Notes |
| --- | --- | --- | --- |
| Momentum primary | Binance.US-labelled spot | 2024-06-13 through 2025-12-02 | 68 exported trades, six USDT pairs |
| Crash sleeve | Binance.US-labelled spot | 2024-06-13 through 2025-12-02 | 78 exported trades, six USDT pairs |
| Momentum forward | Coinbase Advanced spot | 2026-01-01 through 2026-09-18 | 12 trades, five USD pairs, 0.6% fee scenario |
| Third-venue data | OKX spot | 2024-06-01 through 2026-09-22 | Five pairs of native 15-minute candles acquired; exact winner replay not yet possible |

The generated JSON is local and ignored:

`research/reports/generated/portfolio_validation_gate.json`

It records the trade-level concentration measures, seeded bootstrap
diagnostics, shared-wallet replay, priority-order sensitivity, and gate
statuses.

## Synchronized shared-wallet replay

The replay used one 1,000-unit wallet, 70% momentum / 30% crash-state budget,
three global positions, a 40% pair cap, pair-overlap rejection, and an
additional 20 bps round-trip stress on top of the Freqtrade exports. The
different 15-minute and 4-hour signal clocks were reconciled by UTC open and
close events. Close events are processed before new opens at the same time.

| Window | Return | Max drawdown | Accepted | Rejected |
| --- | ---: | ---: | ---: | ---: |
| Full 2024-06-13 to 2025-12-02 | **+65.87%** | 14.21% | 96 | 50 |
| Locked 2025 holdout | **+6.87%** | 13.68% | 67 | 24 |

The locked holdout is replayed by filtering the full-window exports rather
than opening a new strategy run after seeing the holdout. That is the more
conservative continuity test; it is why it is lower than a separately
generated, holdout-only screen.

Replaying the two sleeve-priority orders produced the same return and drawdown
because the exported events did not contain a materially ambiguous same-time
allocation decision under these caps. This is a pass for this specific replay,
not evidence that order priority can be ignored in a live executor.

## Concentration and path dependence

The full primary momentum export is not driven by one trade, but it is still
concentrated:

- 68 trades across six pairs;
- the largest winning trade contributed 30.72% of positive gains;
- the top three winners contributed 60.30% of positive gains;
- removing the top three winners changes the result to **-2.09%** on the
  1,000-unit export wallet;
- the top pair contributed 32.69% of positive gains.

The 2026 Coinbase forward is substantially less convincing:

- 12 trades, only four winners, across four active pairs;
- +1.64% after the 0.6% fee scenario;
- the largest trade and pair, `SOL/USD`, contributed 44.85% of positive gains;
- removing the largest winner changes the result to **-3.66%**;
- removing the top three winners changes it to **-8.37%**;
- April and May were negative, while August supplied the positive offset.

The forward result therefore passes a basic positive-return screen but fails a
reasonable evidence-quality threshold. It is a small, trend-sensitive sample
whose apparent profit depends on a few observations.

## Seeded Monte Carlo diagnostics

These are resampling diagnostics, not forecasts or confidence intervals.

| Lane | Trade-bootstrap probability of profit | Trade-bootstrap P05 / P50 / P95 | Month-block probability of profit |
| --- | ---: | ---: | ---: |
| Primary full | 88.00% | -24.31% / +80.17% / +214.99% | 81.24% |
| Coinbase 2026 forward | 56.68% | -10.25% / +1.26% / +14.69% | 70.84% |

The primary path has a positive resampling bias, but a very wide outcome range.
The forward path is close to a coin flip under trade resampling, and the
month-block result is based on only three active months. Neither supports a
profitability claim.

## Third venue result

The OKX acquisition succeeded as a data step. Native spot 15-minute candles
for BTC, ETH, SOL, XRP, and DOGE were downloaded through 2026-09-22. The
third-venue gate is still **blocked**, for a precise reason: the public
checkout does not contain the base `MomentumRegimeBasket15m` implementation
used by the historical `MomentumRegimeBasket15mLb30` export. The result ZIP
contains the thin subclass, but not the imported base module. Running a
different strategy or substituting OKX perpetual data would not be an exact
third-venue validation of this lead.

This is an intentional fail-closed outcome. The next implementation step is
to restore or independently reimplement the exact momentum sleeve under a
reviewable source file, then run it unchanged on the acquired OKX spot data.
Until that happens, OKX is a data-readiness result, not a performance result.

## Decision

The lead is **not yet a credible portable portfolio product**.

It passes the shared-wallet replay and the locked 2025 holdout. It only earns a
review status on the 2026 forward lane because the result is small and highly
concentrated, and it fails the third-venue gate because the exact strategy
source is incomplete. The work should now focus on source restoration,
venue-matched execution assumptions, and a pre-registered OKX replay—not more
parameter tuning.

The evidence bar for promotion is:

1. exact source restored and frozen;
2. at least one full calendar year of 2026 forward data with a meaningful
   trade count;
3. the same shared-wallet allocator on the third venue;
4. no single-trade or single-pair dependence that reverses the conclusion; and
5. measured venue-specific fees, spread, and slippage rather than a generic
   cost haircut.

If this makes money, tell me lol. If it loses money, tell me that too—the
point is to measure reality, not promise returns.
