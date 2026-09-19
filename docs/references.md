# References and attribution

## Project code

The strategy and regime-detector modules in this repository are original
project implementations. They were developed during the earlier `aitrader`
prototype and migrated to Freqtrade. No source code, figures, or prose is
intentionally redistributed from a research paper.

## Runtime reference

- [Freqtrade](https://github.com/freqtrade/freqtrade) — external runtime,
  strategy interface, data access, backtesting, and dry-run execution.
- [FreqAI: generalizing adaptive modeling for chaotic time-series market
  forecasts](https://doi.org/10.21105/joss.04864) — Freqtrade ecosystem paper;
  this repository does not redistribute FreqAI source code.

## Research-paper bibliography

- Chang, Y., Lizardi, C., and Shah, R. (2022), “Optimizing Returns Using the
  Hurst Exponent and Q Learning on Momentum and Mean Reversion Strategies,”
  [arXiv:2205.11122](https://arxiv.org/abs/2205.11122). Informed the
  OHLCV-only `HurstRegimeSwitch` research lane; the Q-learning component was
  not copied or implemented.
- Cortese, F. P., Kolm, P. N., and Lindström, E. (2023), “What drives
  cryptocurrency returns? A sparse statistical jump model approach,”
  [Digital Finance DOI](https://doi.org/10.1007/s42521-023-00085-x). Informed
  the use of interpretable regime labels as an evaluation dimension, not a
  copied jump-model implementation.
- Dobrynskaya, V. (2023), “Cryptocurrency Momentum and Reversal,”
  [Journal of Alternative Investments DOI](https://doi.org/10.3905/jai.2023.1.189).
  Informed the separation of momentum and reversal results by window and
  regime.
- Ramos-Requena, J. P., and Bağcı, M. (2026), “Analysis Pairs Trading Strategy
  Applied to the Cryptocurrency Market,”
  [publisher record](https://doi.org/10.1007/s10614-025-11149-y). This is a
  deferred research direction for a GHE-based pair selector; the current
  repository does not claim to reproduce it.
- Lahmiri, S. and Bekiros, S. (2019), “Intraday efficiency-frequency nexus in
  the cryptocurrency markets,”
  [ResearchGate record](https://www.researchgate.net/publication/336018023_Intraday_efficiency-frequency_nexus_in_the_cryptocurrency_markets)
  and [publisher DOI](https://doi.org/10.1016/j.frl.2019.09.013). Informed
  the decision to keep sampling frequency and venue as explicit test factors.

## Data and library references

Market-data endpoints and Python libraries are implementation dependencies, not
strategy provenance. Their links and licenses should be reviewed separately
when the optional data adapters are added to this public repository.
