# Downstream inventory

Market Behavior Lab is the extracted research layer from a larger Freqtrade
checkout. This document records the boundary between project-specific work and
the upstream runtime.

## Project-specific code

| Area | Public content | Purpose |
| --- | --- | --- |
| Strategies | `user_data/strategies/` | Regime detection, signal sleeves, ranking, sizing, and trade management |
| Research | `research/evaluation/` | Trade-order Monte Carlo and reusable evaluation helpers |
| Acceptance | `tests/acceptance/` | Lightweight tests for robustness, pyramiding, and position sizing |
| Documentation | `README.md`, `docs/` | Architecture, evaluation, history, references, and runtime instructions |
| Configuration | `examples/` | Safe backtest and credential-free dry-run examples |

## Curated strategy set

- `RegimeRouted.py`: primary multi-sleeve, regime-routed futures strategy.
- `lib/regime_detector.py`: reusable 33-column market-state detector.
- `SlowResidualRotation.py`: slower residual/momentum rotation research.
- `QuietBreakoutSwing.py`: lower-frequency breakout research.
- `CrossSectionalRotation.py`: cross-sectional ranking and rotation research.
- `PortfolioAllocatorSpot.py`: spot allocation experiment.
- `RelativeValueBucket.py`: relative-value bucket research.
- `CrossSectionalRotation_KR.py` and `spot_arch_utils.py`: support modules for
  the spot allocator.

## Deliberately excluded Freqtrade fork changes

The source checkout also contained direct changes to Freqtrade exchange and
configuration code, including Kraken Futures behavior, BloFin registration,
order lookup fallback, and configuration wizard changes. Those changes are not
part of this standalone repository. They remain separate fork work and are not
required by the public strategy workflow.

## Historical project name

The old `aitrader` references in the source headers described the project’s
former internal name. They were not third-party attribution. The public code
uses Market Behavior Lab and documents the rename in
[`project-history.md`](project-history.md).

## Excluded local material

The public repository must not contain:

- live or credential-bearing configuration;
- SQLite databases, logs, backups, or raw market-data caches;
- generated backtest archives or temporary research outputs;
- platform-specific Python wheels;
- workstation-specific absolute paths;
- private operational runbooks or deployment instructions.

The allowlisted extraction and final validation scan are intentional safeguards
against accidentally publishing the much larger local working tree.
