# Public data re-evaluation — 2026-09-25

This report records the seven-part re-evaluation gate run against the local
Market Behavior Lab research checkout. It is a screening report, not a live
performance claim.

## Protocol

- Freqtrade: `2026.2-dev-d07ba71e3`.
- Frozen strategy parameters; no retuning was performed for this pass.
- Freqtrade fee stress: 0.10% per side.
- Starting balance: 1,000 USDT.
- Maximum open trades: 2.
- Primary window: 2024-06-13 through 2025-12-02, with each strategy's warm-up
  period reducing the first tradable timestamp.
- Additional round-trip costs of 10, 20, 40, and 80 bps were applied after
  the Freqtrade export. These are modeled sensitivities, not historical fills.
- Walk-forward windows were fixed before looking at results:
  `2024-06-13–2024-12-31`, `2025-01-01–2025-09-30`, and
  `2025-10-01–2025-12-02`.
- Bootstrap results use 2,000 independent trade resamples. They are not a
  substitute for a path- or order-book-level Monte Carlo simulation.

## Full-window results

| Venue / lane | Trades | Net result | Max drawdown | Result at +40 bps extra round trip | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| OKX perpetual — `StandaloneBreakoutTrend` | 124 | +1.97% | 0.86% | +1.15% | Best OKX screen; long leg +2.07%, short leg -0.10% |
| OKX perpetual — `VolatilityManagedTrendCash` | 95 | +0.18% | 0.32% | -0.06% | Too little edge after modest extra cost |
| OKX perpetual — `CrossSectionalRotation` | 392 | -4.21% | 4.24% | -7.09% | Negative on both long (-2.30%) and short (-1.91%) legs |
| Binance.US-labeled spot — `StandaloneBreakoutTrendSpot` | 104 | +5.95% | 1.17% | +5.13% | Positive aggregate screen, but not stable in the late window |
| Binance.US-labeled spot — `VolatilityManagedTrendCashSpot` | 59 | +0.48% | 0.36% | +0.36% | Near-flat and low sample size |
| Binance.US-labeled spot — `PortfolioAllocatorSpot` | 310 | -5.52% | 5.52% | -7.98% | The shared portfolio implementation is currently a negative control |

The Binance.US label refers to the project's existing Freqtrade candle files;
the newly downloaded public Binance archive is global Binance and is not used
to claim Binance.US execution history.

The strongest positive full-window screen, `StandaloneBreakoutTrendSpot`, is
not a buy-and-hold replacement. In the same window, fee-adjusted buy-and-hold
was approximately +28.82% for BTC, -19.93% for ETH, -16.02% for SOL, and
+315.42% for XRP in the project’s spot files. That comparison shows how much
the result depends on the selected pair and regime; it does not establish a
tradable benchmark portfolio.

## Walk-forward stability

| Lane | Early window | Middle window | Late window | Reading |
| --- | ---: | ---: | ---: | --- |
| OKX `StandaloneBreakoutTrend` | +1.30% / 40 trades | +0.42% / 65 | +0.28% / 19 | Positive, but small and cost-sensitive |
| OKX `VolatilityManagedTrendCash` | +0.20% / 30 | +0.17% / 52 | -0.12% / 13 | Near-flat and fails late |
| Binance.US `StandaloneBreakoutTrendSpot` | +4.77% / 42 | +1.43% / 52 | -0.32% / 10 | Fails the locked late window |
| Binance.US `VolatilityManagedTrendCashSpot` | +0.43% / 17 | +0.13% / 37 | -0.26% / 8 | Fails the locked late window |

The late Binance.US breakout window had only ten trades and only a 7.05%
profitable-bootstrap rate. That is negative evidence, even though the full
window is positive.

## Data-contract and source results

The new normalizers produced local, ignored artifacts without mixing venues:

- Binance global official August 2026 BTCUSDT 1-minute archive: 44,640 UTC
  candles; checksum verified as
  `acab442e02745177063031d402929703ae983715010064b40cf811c4beb843d4`.
- OKX historical-market-data module 2: 2,880 UTC BTC-USDT-SWAP 1-minute
  candles over the two downloaded days. The OKX module 4 query confirmed
  roughly 703.89 MB of 400-level L2 files for those two days, but those files
  were not downloaded or used for strategy evaluation.
- OKX public derivative pages: 100 funding observations covering
  2026-08-23 through 2026-09-25, plus short current mark, index, and
  open-interest pages. This is not a complete historical carry panel.
- Kraken REST: a bounded page of 1,000 XBT/USD trades covering only about 36
  minutes from 2025-01-01. The complete quarterly archive was not pulled
  because the advertised file was about 1.3 GB on a nearly full development
  disk.
- BitMEX: one public 2015 day supplied 73 trade rows and 1,040 quote rows.
- Tardis: one permitted first-of-month Deribit BTC perpetual sample supplied
  131,910 trades. It is a sample, not a full venue history.
- Coin Metrics Community: the coverage catalog returned, but the requested
  historical market-orderbook series returned `403`; no substitute was used.

Current public order-book snapshots were available for cost calibration, but
they are not backdated onto old trades. A historical execution-cost claim
still requires timestamp-matched books or trades at each signal and fill.

## What was completed and what remains blocked

1. **Normalized contract:** completed for Binance/OKX OHLCV and OKX funding,
   mark, index, and open-interest responses. Each artifact has UTC timestamps,
   a schema version, source metadata, and `execution_truth: false`.
2. **Frozen parameters:** completed. No post-result tuning was used.
3. **Candidate reruns:** completed for the available breakout, volatility,
   cross-sectional, and allocator lanes. `MomentumRegimeBasket15mLb30` was not
   rerun because its implementation is absent from this public checkout; its
   earlier documented numbers were not treated as new evidence.
4. **Costs:** fee stress and modeled round-trip cost sensitivity completed;
   venue-current snapshots completed. Historical spread/slippage and funding
   attribution remain incomplete.
5. **Benchmarks:** completed against exact local candle files and the
   documented buy-and-hold calculation.
6. **Third-venue portability:** partially completed. Kraken and Tardis data
   access was verified, but neither source currently supplies the complete
   compatible OHLCV windows needed for a fair frozen strategy comparison.
7. **Order-flow/market making:** correctly deferred. The available OKX L2
   query establishes that large historical files exist, but a complete,
   downloaded, normalized, replayable L2 history is not yet available.

## Decision

No lane clears a portable-profit gate. The most defensible next candidate is
the standalone breakout on a longer, genuinely forward Binance.US window,
but it must remain frozen and must use matched venue costs. The next data
priority is not another indicator: acquire enough same-venue minute trades,
quotes/L2, funding, index, mark, open interest, fee tiers, and point-in-time
universe membership to reconcile expected and realized fills. Carry and
market-making research should wait for that data.
