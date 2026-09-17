# Freqtrade runtime contract

Market Behavior Lab is not a Freqtrade fork. The public repository supplies
strategies and research helpers that are loaded through Freqtrade's normal
`--userdir` interface.

## Supported layout

```text
market-behavior-lab/user_data/strategies/*.py
```

The upstream Freqtrade executable should receive the absolute path to that
directory through `--userdir`.

## Tested workflow

Use a supported Python version and a pinned or stable upstream Freqtrade
checkout. Install Freqtrade in its own virtual environment, then run the CLI
from the Market Behavior Lab directory with the example configs.

The default public path is backtesting followed by credential-free dry-run.
Live trading requires a private configuration and is intentionally outside the
scope of this repository.
