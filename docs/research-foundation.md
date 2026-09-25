# Research foundation and next validation lanes

This document defines the project’s execution-aware research boundary. The
repository remains a Freqtrade strategy/research layer; it is not an exchange
adapter or a live trading service.

## Priority 1: evidence before tuning

The first priority is a common `microstructure.v1` contract for venue-labeled
one-minute trades and L2 order-book snapshots. The normalizer in
`research/evaluation/microstructure.py` preserves:

- UTC timestamps, venue, canonical pair, and spot/futures market type;
- trade price, amount, side, and notional;
- order-book depth, best bid/ask, midpoint, and observed spread;
- source labels and explicit missing-data behavior.

Use `scripts/normalize_microstructure.py` to convert a permitted venue export
to uncompressed Parquet. Do not mix those files into Freqtrade OHLCV candles.
Current public snapshots are calibration observations, not historical fills.

`VenueCostModel` holds maker/taker fee tiers and safety assumptions.
`execution_foundation.py` adds a deterministic shared-wallet replay and a
dry-run fill reconciliation report. If an order book is required and missing,
the simulator rejects the trade; it does not silently assume zero slippage.

Point-in-time universe membership is required for cross-sectional research.
Membership rows are effective from their UTC timestamp until the next change,
so a later listing cannot enter an earlier ranking.

## Priority 2: same-venue cash and carry

`research/evaluation/cash_carry.py` is an offline two-leg evaluator:

1. Long the spot asset.
2. Short the same asset’s perpetual/futures contract on the same venue.
3. Account for funding received by the short, basis convergence, round-trip
   costs, borrow, collateral carry, and optional margin-buffer observations.
4. Report an adverse-basis and venue-failure stress result.

It fails closed for venue mismatch, missing index, missing funding, and missing
overlap. A carry result is not valid when spot comes from Binance.US and the
perpetual comes from OKX, or when an index is replaced by CoinGecko.

The local cache currently does not provide a complete same-venue spot,
perpetual, funding, and index history for a long, comparable window. The
correct result is therefore often `eligible: false`, not an invented return.

## Priority 3: cross-sectional portfolio

`research/evaluation/cross_sectional_portfolio.py` is the first portfolio-level
lane rather than a collection of independent pair strategies. It combines:

- momentum and short-horizon reversal ranks;
- rolling quote-liquidity rank;
- inverse-volatility weights;
- rolling BTC beta control;
- point-in-time universe membership;
- long/short selection, spot-only mode, rebalance turnover, and concentration
  caps;
- venue-specific fee, spread, and slippage assumptions.

The evaluator is intentionally separate from `RegimeRouted`: a portfolio
allocator must prove that it improves a frozen, cost-aware result before it is
allowed to become a strategy enhancement.

## Priority 4: frozen volatility-managed ensemble

`research/evaluation/volatility_ensemble.py` evaluates `VolatilityManagedTrendCash`,
standalone breakout, and multi-timeframe confirmation as independent sleeves.
It accepts closed trade exports in timestamp order, applies one wallet,
overlap handling, capacity limits, and costs. Parameters must be frozen before
an ensemble run; a positive historical sleeve cannot be selected after seeing
the combined result.

The intended test lanes are Binance.US spot, Coinbase spot, and OKX or another
permitted venue using each venue’s native data and fee schedule. The ensemble
does not make any venue portable by averaging returns.

## Priority 5: market making and order flow

`research/evaluation/orderflow_market_making.py` is a readiness-gated scaffold.
It accepts only timestamped trades plus normalized L2 books and includes a
small passive-quote replay for spread, inventory, and adverse-selection
sensitivity. It explicitly does not model queue priority, latency, partial
fills, cancellations, or exchange outages yet.

OHLCV-only backtests are not evidence for market making. The lane remains
deferred until a permitted venue provides synchronized trade/order-book events
with sufficient history.

## Reproduction gates

Run the focused foundation tests:

```bash
python -m pytest -q tests/test_research_foundation.py
```

Normalize a permitted export:

```bash
python scripts/normalize_microstructure.py \
  --kind trades \
  --input /path/to/venue-trades.parquet \
  --output /tmp/btc-usdt-trades.parquet \
  --venue coinbase \
  --pair BTC/USD \
  --market-type spot \
  --source coinbase-public-trades
```

The project’s normal Freqtrade install and backtest commands remain in the
main [README](../README.md). Freqtrade candle data is still the truth for a
candle backtest; microstructure data calibrates execution and enables a
separate event-driven study.

## Promotion rule

No lane is promoted because it is positive in one historical window. A
candidate must clear:

- exact venue and market-type provenance;
- point-in-time universe controls;
- frozen parameters on a later window;
- measured or conservative costs;
- shared-wallet and concentration checks;
- minimum trade-count and drawdown gates;
- dry-run expected-versus-realized fill reconciliation;
- a venue-specific operational and regulatory review.

If this makes money, tell me lol. If it loses money, tell me that too—the
point is to measure reality, not promise returns.
