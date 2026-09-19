# Market Behavior Lab

An experimental application for studying how adaptive strategies respond to
changing market conditions.

Market Behavior Lab is a portfolio research project built to run on the
[Freqtrade](https://github.com/freqtrade/freqtrade) runtime. It explores market
regimes, routed signal families, portfolio-aware sizing, and disciplined
backtest validation. Freqtrade is installed separately; this repository contains
the project-specific research layer.

> **Status: archived research project.** This is a portfolio artifact, not a
> trading recommendation or a promise of future returns.

> If this makes money, tell me lol. If it loses money, tell me that too—the
> point is to measure reality, not promise returns.

## Why this project exists

Many trading experiments look convincing in one backtest and fail when the
market, venue, or execution assumptions change. This project investigates that
failure directly rather than presenting one optimized indicator as a finished
product.

The project combines:

- reusable market-regime detection;
- multiple signal sleeves routed by market state;
- cross-sectional ranking and portfolio-aware allocation;
- volatility-aware sizing, exposure limits, and cost gates;
- custom exits, stops, protections, and continuation pyramiding;
- walk-forward, lookahead, recursive, and path-risk checks;
- explicit treatment of failed or default-off experiments.

## Architecture

```text
OHLCV and optional reference data
                |
                v
        lib/regime_detector.py
   trend, volatility, liquidity,
       sweep and stress context
                |
                v
          RegimeRouted
       routed signal sleeves
                |
                v
      ranking -> sizing -> risk
                |
                v
         Freqtrade callbacks
                |
                v
      backtest or credential-free
             dry-run
```

### What is specific to this project?

| Market Behavior Lab | Upstream Freqtrade |
| --- | --- |
| `RegimeRouted` and supporting strategies | Trading engine and `IStrategy` API |
| Regime detector and 33 derived features | Exchange/data abstractions |
| Signal routing, ranking, sizing, and risk governance | Backtesting, dry-run, and CLI |
| Research acceptance and Monte Carlo helpers | Persistence and reporting primitives |
| Project evaluation notes and failed experiments | General documentation and runtime support |

The old internal project name was **aitrader**. The strategy code was migrated
to the Freqtrade runtime; `aitrader` is retained only as historical project
lineage.

## Strategy catalogue

| Strategy | Timeframe | Side | Role |
| --- | --- | --- | --- |
| `RegimeRouted` | 1h | Long/short | Primary regime-routed futures research strategy |
| `RegimeRoutedSpot` | 1h | Long-only | Coinbase Advanced spot validation lane |
| `SlowResidualRotation` | 4h | Long-only | Slower residual and momentum rotation |
| `QuietBreakoutSwing` | 4h | Long-only | Lower-frequency breakout research |
| `CrossSectionalRotation` | 1h | Long/short | Cross-sectional ranking and rotation |
| `PortfolioAllocatorSpot` | 4h | Long-only | Spot portfolio allocation experiment |
| `RelativeValueBucket` | 1h | Long/short | Relative-value bucket research |
| `RelativeValueGHE` | 1h | Long/short | Fixed residual leader map with causal generalized-Hurst filter |
| `RegimeRoutedVolTarget` | 1h | Long/short | Regime router with volatility-targeted sizing |
| `JumpAwareRegimeRouted` | 1h | Long/short | Regime router with negative-jump stress veto |
| `CryptoFactorEnsemble` | 1h | Long/short | Transparent momentum, reversal, liquidity, and volatility factors |
| `VolatilityManagedMomentum` | 4h | Long-only | Slow momentum/residual sleeve with volatility-managed sizing |
| `ClusterRotation` | 1h | Long/short | Cross-sectional rotation with correlation concentration control |
| `KalmanResidual` | 1h | Long/short | Relative-value lane with a causal adaptive hedge ratio |
| `RegimeRoutedFundingFilter` | 1h | Long/short | Requires overlapping historical funding; fail-closed validation lane |
| `RegimeRoutedBasisOI` | 1h | Long/short | Requires both basis and open interest; no cross-venue filling |
| `HurstRegimeSwitch` | 1h | Long/short | Experimental Hurst-conditioned momentum/mean-reversion lane |
| `CryptoMomentumRotation` / `CryptoMomentumRotationSpot` | 1h | Long/short / long-only | Independent cross-sectional momentum lane |
| `ScheduledPortfolioRotation` | 4h | Long-only | Lower-turnover scheduled portfolio rotation |
| `StandaloneBreakoutTrend` / `StandaloneBreakoutTrendSpot` | 4h | Long/short / long-only | Donchian/ATR trend-following lane |
| `StandaloneBreakoutTrendSpotGuarded` | 4h | Long-only | Spot breakout with a broad BTC trend guard |
| `RelativeValueStatArb` | 1h | Long/short | Fixed-leader residual statistical arbitrage |
| `FundingBasisCarry` | 1h | Long/short | Fail-closed exact-venue carry validation lane |
| `VolatilityCrashGuard` | 1h | Long-only | Trend participation with volatility/crash gating |
| `VolatilityConditionedReversal` | 15m | Long/short | Short-horizon reversal gated by elevated volatility |
| `SizeLiquidityDualSignal` | 1h | Long/short | Dollar-volume liquidity proxy with momentum/reversal split |
| `DispersionConditionedMomentum` | 4h | Long/short | Cross-sectional momentum activated by universe dispersion |
| `MultiHorizonTrendReversal` | 1h | Long/short | Fixed multi-horizon trend and short-horizon reversal blend |
| `BetaNeutralResidualPortfolio` | 1h | Long/short | Residual lane with a signal-level BTC beta cap |
| `CrossSectionalReversal8W` | 4h | Long/short | High-volatility 8-week cross-sectional reversal |
| `AdaptiveTrendPortfolio` | 1h decision / 6h schedule | Long/short | Rolling-Sharpe trend selection with ATR trailing exits |
| `SymmetricTrendVeto` | 1h | Long/short | Trend lane with separate long/short trailing-return vetoes |
| `CostAwareMomentumGate` | 1h | Long/short | Momentum entries gated above modeled execution costs |
| `VolumeProfileOHLCVProxy` | 5m | Long/short | Previous-day volume-profile and candle-volume proxy |
| `MultiTimeframeConfirmation` | 5m + 15m | Long/short | Lower-timeframe signal requiring higher-timeframe agreement |
| `BaselineRSIBollinger` / `BaselineRSIBollingerSpot` | 1h | Long/short / long-only | Unchanged RSI/Bollinger mean-reversion baseline |
| `BaselineEMAADX` / `BaselineEMAADXSpot` | 1h | Long/short / long-only | Unchanged EMA/ADX trend-following baseline |

The official upstream `SampleStrategy` and community `FSampleStrategy` were
also evaluated as external Freqtrade baselines; they are not copied into this
repository. See the [baseline validation matrix](docs/crypto-strategy-research.md#baseline-validation-matrix)
for the exact datasets, diagnostics, and limitations.

`CrossSectionalRotation_KR.py` and `spot_arch_utils.py` are supporting modules
required by the spot allocator. They are not separate claims of venue
portability.

## Research outcome

The project found that the strongest behavior was venue-specific and did not
transfer cleanly to the intended deployment path. OKX was the only venue in the
research record showing strong economics; Kraken derivatives did not reproduce
that behavior, and available Hyperliquid history was insufficient for the same
research loop.

The best late-stage spot salvage recorded in the archive was:

| Scenario | Profit | Sharpe | Profit factor | Max drawdown |
| --- | ---: | ---: | ---: | ---: |
| `RegimeRoutedSpotTrim`, `A4_deny8_toploss` | `+148.654 USDT` (`+14.87%`) | `0.437` | `3.373` | `1.40%` |

This is a historical backtest result from the research archive. It is not an
independently reproduced guarantee, live performance, or investment claim.

The final spot rewrites were instructive failures:

| Strategy | Result | Trades | Sharpe | Profit factor | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| `CrossSectionalRotationSpot` | `-34.72%` | 146 | -3.984 | 0.149 | 34.72% |
| `RelativeValueBucketSpot` | `-0.05%` | 4 | -0.087 | 0.040 | 0.05% |
| `PortfolioAllocatorSpot` | `-66.21%` | 191 | -9.284 | 0.061 | 66.54% |

See [`docs/evaluation.md`](docs/evaluation.md) for the full interpretation,
windows, and limitations.

For the separate Coinbase Advanced spot lane, see
[`docs/coinbase-spot-validation.md`](docs/coinbase-spot-validation.md). It is
an exchange-specific validation experiment, not a profitability promise.

## Install upstream Freqtrade

This project does not replace or vendor Freqtrade. Install a supported upstream
checkout in its own virtual environment:

```bash
export FREQTRADE_ROOT=/path/to/freqtrade
export LAB_ROOT=/path/to/market-behavior-lab

git clone --branch stable --depth 1 \
  https://github.com/freqtrade/freqtrade.git "$FREQTRADE_ROOT"
cd "$FREQTRADE_ROOT"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -e .

freqtrade --version
```

## Install and run Market Behavior Lab

Clone the public project:

```bash
git clone https://github.com/jcd1991/market-behavior-lab.git "$LAB_ROOT"
cd "$LAB_ROOT"

# Optional: install the repository's lightweight research-test dependencies.
python -m pip install -e "$LAB_ROOT[dev]"
```

Discover the strategies:

```bash
"$FREQTRADE_ROOT/.venv/bin/freqtrade" list-strategies \
  --userdir "$LAB_ROOT/user_data"
```

Download representative 1-hour futures data:

```bash
"$FREQTRADE_ROOT/.venv/bin/freqtrade" download-data \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.example.json" \
  --datadir "$LAB_ROOT/user_data/data" \
  --exchange okx \
  --pairs BTC/USDT:USDT ETH/USDT:USDT \
  --timeframes 1h \
  --timerange 20240601-20251201
```

Run a backtest:

```bash
"$FREQTRADE_ROOT/.venv/bin/freqtrade" backtesting \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.example.json" \
  --datadir "$LAB_ROOT/user_data/data" \
  --strategy RegimeRouted \
  --timerange 20240601-20251201 \
  --export trades
```

For the documented OKX universe-sensitivity study, use the explicit
credential-free configs under `examples/`:

```bash
freqtrade backtesting --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.okx.btc-eth.example.json" \
  --datadir "$LAB_ROOT/user_data/data" --strategy RegimeRouted \
  --timerange 20240613-20251202 --export trades

freqtrade backtesting --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.okx.expanded.example.json" \
  --datadir "$LAB_ROOT/user_data/data" --strategy RegimeRouted \
  --timerange 20240613-20251202 --export trades
```

These are historical research lanes only. The configs contain no credentials
and do not constitute a U.S. leveraged-trading recommendation.

Before using derivative-feature lanes, audit exact venue/date overlap:

```bash
python research/evaluation/derivative_manifest.py \
  --data-dir "$LAB_ROOT/user_data/data/futures" \
  --ohlcv-file "$LAB_ROOT/user_data/data/futures/BTC_USDT_USDT-1h-futures.feather"
```

`scripts/backfill_okx_derivatives.sh` downloads futures, mark, index, and
funding candles into a separate directory without deleting existing data.
`RegimeRoutedFundingFilter` blocks missing funding; `RegimeRoutedBasisOI`
requires both basis and open interest. Liquidation events need a separate,
venue-labeled historical event source and are never inferred from candle wicks.

For the spot validation lane, use `examples/config.backtest.binanceus.spot.example.json`
with `PortfolioAllocatorSpot` and canonical spot pairs such as `BTC/USDT`.
Futures-only strategies and fields such as funding, mark price, and index price
are not silently substituted into this spot path.

Run a credential-free dry-run:

```bash
"$FREQTRADE_ROOT/.venv/bin/freqtrade" trade \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.dry-run.example.json" \
  --strategy RegimeRouted
```

The public configurations keep `dry_run` enabled, disable Telegram/API access,
contain no credentials, and use a small simulated wallet. Live trading is not
part of the public quickstart.

For current execution-cost calibration only, capture a public order-book
snapshot. This is not historical spread/slippage data and must not be merged
into backtest candles:

```bash
"$FREQTRADE_ROOT/.venv/bin/python" \
  "$LAB_ROOT/research/evaluation/orderbook_cost_snapshot.py" \
  --exchange binanceus --pair BTC/USDT --pair ETH/USDT --notional 20
```

## Research checks

The repository includes small, dependency-light checks for the reusable research
helpers:

```bash
cd "$LAB_ROOT"
"$FREQTRADE_ROOT/.venv/bin/python" -m pytest -q
```

The acceptance scripts can also be run directly:

```bash
"$FREQTRADE_ROOT/.venv/bin/python" \
  tests/acceptance/robustness_acceptance_tests.py
"$FREQTRADE_ROOT/.venv/bin/python" \
  tests/acceptance/pyr_acceptance_tests.py
"$FREQTRADE_ROOT/.venv/bin/python" \
  tests/acceptance/qsize_acceptance_tests.py
```

## External research and data references

The custom implementation is original project code informed by public research.
Paper-specific references are listed only when the exact bibliographic record is
known; see [`docs/references.md`](docs/references.md). Runtime and data-provider
links are kept separate from strategy provenance.

## Disclaimer

This software is experimental and provided for research and educational use.
Backtests are sensitive to data quality, fees, slippage, pair selection, venue
behavior, and implementation details. Past simulated results do not predict
future results. Do not use this project with money you cannot afford to lose.

## License

Original Market Behavior Lab code is released under the MIT License. Freqtrade
is an external dependency with its own license and project terms. See
[`LICENSE`](LICENSE) and [`docs/freqtrade-runtime.md`](docs/freqtrade-runtime.md).
