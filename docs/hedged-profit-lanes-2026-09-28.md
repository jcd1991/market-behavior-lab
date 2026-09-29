# Hedged profit lanes — investigation and implementation

## Objective

The next product direction is deliberately different from another trend
strategy:

1. same-venue cash-and-carry — long spot, short the same asset's perpetual or
   future, collect observed funding, and wait for basis convergence; and
2. true two-leg residual hedging — trade both legs of a residual signal with a
   causal hedge ratio, including the short leg, synchronized costs, and shared
   capital.

Neither lane is a profitability claim until its venue-matched history is
complete. A one-position Freqtrade strategy or a cross-venue price join is not
enough to establish a hedge.

## Investigation findings

The repository already contained diagnostic implementations in
`research/evaluation/cash_carry.py` and
`research/evaluation/cointegration_book.py`. The missing product-grade pieces
were the promotion gates and an executable path that could not silently turn
incomplete data into a market-neutral result.

The current local cache contains:

| Lane | Available evidence | Promotion status |
| --- | --- | --- |
| Binance Global BTC/ETH carry | 91.67 days of spot, perpetual, index, mark, and 276 funding observations, plus 5-minute open-interest context; no margin/liquidation buffer | Blocked: missing margin data |
| OKX BTC derivatives | Short futures/mark/index/funding fragments, no overlapping same-venue spot leg, and only one open-interest observation | Blocked: no complete carry contract |
| Two-leg residual | Long OHLCV histories exist for some local pairs, but no explicit venue manifests and no shortable reference-leg contract | Blocked: provenance and shortability are unverified |

The expanded Binance Global diagnostic remains useful only as a data-pipeline
check. With deliberately loose thresholds it produced one basis-convergence
trade for BTC at roughly **+1.60% before stress** and one for ETH at roughly
**+0.81% before stress**. Funding income was zero during both held intervals;
the configured adverse-basis and venue-failure stress reduced them to roughly
**-0.40%** and **-1.19%**. This is not a carry-income result and is not
promoted.

## Implemented changes

### Same-venue cash-and-carry

`cash_carry.py` now includes `audit_same_venue_inputs`, which requires:

- all four inputs: spot, perpetual/future, venue index, and funding;
- sidecar provenance identifying the same venue for every input;
- at least 90 overlapping days by default;
- a minimum funding-event count;
- margin or liquidation-buffer observations for promotion.

The normal evaluator remains available for short diagnostics, while
`evaluate_pair(..., strict_coverage=True)` fails closed at the promotion gate.
The executable basis is now calculated from the traded perpetual versus the
traded spot leg. The index remains a required same-venue oracle and risk input,
but is no longer silently used as a substitute for the spot execution leg.

### True two-leg residual hedging

`cointegration_book.py` now includes:

- `audit_two_leg_inputs`, which checks same-venue provenance, distinct legs,
  overlapping history, and a reference leg explicitly marked as
  futures/perpetual/swap when shortability is required;
- `simulate_pair_from_paths`, which refuses to simulate when that contract
  fails;
- Parquet input support in addition to Feather;
- a `--strict-contract` CLI option.

The existing simulator continues to calculate causal rolling beta, residual
z-score, correlation, and half-life. It sizes both legs from the hedge beta;
the strict path makes clear that this is a real two-leg research book only
when the data contract proves that both legs can be traded as modeled.

### Reproducible runner

The new `scripts/run_hedged_lanes.py` runs both audits and, when eligible, the
diagnostics. It writes no market data to the repository. Example:

```bash
python scripts/run_hedged_lanes.py \
  --carry-spot user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT-1m.feather \
  --carry-perp user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-1m-futures.feather \
  --carry-funding user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-funding.feather \
  --carry-index user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-index-1m.feather \
  --carry-venue binance-global \
  --residual-asset /path/to/asset.feather \
  --residual-reference /path/to/shortable-reference.feather \
  --residual-venue okx \
  --min-overlap-days 90
```

The residual paths are intentionally placeholders until a same-venue pair with
an explicitly shortable reference is acquired. The command reports the
failure reason instead of substituting another venue.

## Practical research plan

### Phase 1 — acquire a complete contract

For one venue and one instrument, acquire at least 90–180 days of:

- spot candles or trades;
- perpetual/future candles or trades;
- the venue's index and mark prices;
- every funding event and funding interval;
- open interest;
- fee tier, spread, and slippage observations;
- margin, liquidation-distance, or a conservative liquidation model.

For residual hedging, acquire two distinct assets on the same venue and market
type. The reference leg must be shortable. Record pair identity, venue,
instrument type, quote/settlement currency, and source manifest for every file.

### Phase 2 — validate the accounting

Use point-in-time signals and next-interval execution. Reconcile:

- both entry fills and both exit fills;
- leg notional and hedge-ratio changes;
- funding paid or received at actual timestamps;
- borrow and collateral cost;
- fees, spread, and slippage separately by leg;
- margin and venue-failure scenarios;
- pair overlap and shared-wallet concentration.

### Phase 3 — freeze before tuning

Split by time, not by favorable trades:

- training window for a small predeclared threshold grid;
- locked forward window with no retuning;
- a second venue or instrument family;
- bootstrap and block-bootstrap path stress;
- minimum trade and minimum funding-event gates.

The lane is not promoted when only basis convergence is positive but funding,
financing, or execution evidence is absent.

### Phase 4 — integrate only after standalone validation

Once a hedged lane passes its own gates, add it to the shared-wallet allocator
as a separate sleeve. Keep it separate from `RegimeRouted` so its return,
drawdown, funding exposure, and venue risk remain attributable. Promote the
combined product only if the sleeve contributes after costs and does not rely
on the old momentum export to carry the result.

## Decision

Implementation is complete for the research contract and fail-closed runner.
The data is not yet complete enough to claim either lane is profitable. The
next external step is acquiring margin/liquidation observations and measured
fill-cost history—not adding more indicator parameters. The expanded Binance
Global and OKX L2 acquisition is documented in the [free derivatives
acquisition report](free-derivatives-acquisition-2026-09-28.md).

If this makes money, tell me lol. If it loses money, tell me that too—the point
is to measure reality, not promise returns.
