# Architecture

## Data flow

1. Freqtrade supplies OHLCV data and strategy callbacks.
2. `lib/regime_detector.py` adds trend, volatility, liquidity, sweep, and stress
   features to the dataframe.
3. `RegimeRouted` gates several signal sleeves by composite regime.
4. Ranking and allocation logic selects candidates and adjusts exposure.
5. Stops, exits, protections, cost checks, and optional pyramiding govern the
   trade lifecycle.
6. Freqtrade performs the backtest or dry-run execution.

## Regime detector

The detector exposes 33 columns including efficiency ratio, choppiness, ATR
phase, Bollinger bandwidth, volatility percentiles, trend direction, sweeps,
reclaims, capitulation context, and liquidity quality. The state machine uses
confirmation and cooldown controls to avoid reacting to every single candle.

## RegimeRouted

The primary strategy is a multi-sleeve `IStrategy` implementation. Its main
research families include volatility expansion, liquidity-sweep reversal,
pullback continuation, breakout resumption, Donchian/Supertrend breakout, and
selective mean reversion. Experimental overlays are controlled by explicit
parameters and are not automatically evidence of a profitable edge.

## Portfolio governance

The strategy adds cross-sectional ranking, pair health, dynamic ranking,
correlation and concentration limits, heat budgets, volatility targeting,
quality-aware sizing, cost gates, loss-streak decay, cooldowns, and structured
trade management on top of Freqtrade callbacks.

Optional external feature files are ignored when absent. They are not required
for the default backtest or dry-run configuration.
