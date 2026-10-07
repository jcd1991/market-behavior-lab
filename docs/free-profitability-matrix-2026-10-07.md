# Free-data profitability matrix

This pass evaluates the six research lanes that can be run from the current
local cache or free public data. It is a screening report, not a profitability
claim.

Run it from the repository root after activating the same Freqtrade virtual
environment used for the rest of the project:

```bash
python \
  scripts/normalize_binance_metrics_series.py \
  --input-dir user_data/data/historical/raw/acquisition-2026-09-28/binance/metrics \
  --symbol BTCUSDT \
  --pair BTC/USDT:USDT \
  --output user_data/data/historical/normalized/binance-global/acquisition-2026-09-28/BTC_USDT_USDT-metrics-5m.feather \
  --source binance-global-public-archive-metrics-acquisition-2026-09-28

python \
  scripts/run_free_profitability_research.py
```

The metrics normalizer writes both the archive label (`date`) and the earliest
safe feature-use timestamp (`available_at`). Binance UM metrics changed from
end-labelled to start-labelled rows on 2026-06-25, so a start-labelled row is
shifted five minutes before it can be used as a signal feature. Ambiguous
single-row or irregular files remain unavailable rather than being guessed.

## Lanes and evidence

| Lane | Input | Evaluation | Promotion status |
| --- | --- | --- | --- |
| Two-leg residual hedge | Same-venue Binance Global BTC/ETH perpetual 1-minute data | Causal rolling beta/z-score grid, cost sensitivity, two walk-forward folds | Research only until frozen forward windows and measured two-leg fills survive |
| Derivatives-conditioned momentum | Same-venue Binance Global futures candles, mark/index, funding, and point-in-time metrics | 5-minute feature join, fixed-hold momentum, shared wallet, frozen tuning | Research only; derivative metrics are free archive context, not execution truth |
| Cash-and-carry | Same-venue Binance Global spot/perpetual/index/funding | Basis convergence, funding, costs, stress, margin-buffer gate | Diagnostic only while observed margin/liquidation and borrow history is absent |
| Cross-sectional portfolio | Local static six-pair spot candle panel | Point-in-time membership, momentum/reversal/liquidity, volatility sizing, caps | Static-universe screen; venue provenance needs re-verification |
| Volatility trend ensemble | Prior venue-labelled Freqtrade exports | Shared-wallet overlap/cap replay and frozen weight/cap tuning | Screening evidence only; exports were not synchronized signal/fill runs |
| Shared wallet | The trend sleeves above | One balance, max-open positions, pair overlap, concentration caps, spread/slippage stress | Required execution gate, not a live allocator |

The generated JSON report is intentionally ignored with local market data:

```text
research/reports/generated/free-profitability-matrix-2026-10-07.json
```

Do not interpret a positive train or holdout result as portable profitability.
The report must be read with the source, venue, market type, date window, trade
count, costs, and missing-data gates beside the return.

If this makes money, tell me lol. If it loses money, tell me that too—the point
is to measure reality, not promise returns.
