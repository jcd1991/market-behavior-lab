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

- Bui, D. and Nguyen, T. (2026), “Systematic Trend-Following with Adaptive
  Portfolio Construction: Enhancing Risk-Adjusted Alpha in Cryptocurrency
  Markets,” [arXiv:2602.11708](https://arxiv.org/abs/2602.11708). Informed the
  `AdaptiveTrendPortfolio` screen: intermediate-frequency momentum, rolling
  risk-adjusted selection, and volatility-scaled trailing exits. The paper's
  market-cap history and execution model were not available locally and were
  not silently substituted.
- Kiefer, P. and Nowotny, M. (2026), “Reversal in Cryptocurrency Returns,”
  [SSRN record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6703978).
  Informed the `CrossSectionalReversal8W` screen. Its reported Binance USDT
  universe, high-volatility conditioning, and survivorship-aware design are
  requirements for a later larger-universe replication.
- Bysik, A. and Ślepaczuk, R. (2026), “Machine Learning-Based Bitcoin Trading
  Under Transaction Costs: Evidence From Walk-Forward Forecasting,”
  [SSRN record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6795938).
  Informed `CostAwareMomentumGate` and the requirement that forecast magnitude
  exceed modeled fees, spread, slippage, and a safety margin before trading.
- Perera, N. (2026), “Volume Profile Mean Reversion Strategy with Tape Speed
  Confirmation for Cryptocurrency Futures Markets,”
  [SSRN record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6932998).
  Informed `VolumeProfileOHLCVProxy`. The repository implementation is only a
  candle-volume proxy and does not claim to reproduce trade-level tape speed.
- Goswami, R. (2026), “Multi-Timeframe Signal Confirmation in Algorithmic
  Cryptocurrency Trading: A Backtest Study on ETH/USDT,”
  [SSRN record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6683818).
  Informed `MultiTimeframeConfirmation`; the small reported sample makes this
  a control experiment rather than evidence of an edge.
- Dashyan, A. (2026), “A Symmetric Trend Veto is Two Different Objects: 5.7
  Years of Barrier Outcomes on Twenty Cryptocurrency Perpetuals,”
  [SSRN record](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7418978).
  Informed `SymmetricTrendVeto`, with long and short veto thresholds tested as
  separate controls.

## Data and library references

Market-data endpoints and Python libraries are implementation dependencies, not
strategy provenance. Their links and licenses should be reviewed separately
when the optional data adapters are added to this public repository.

## Evaluated external strategy sources

- [darkvolg/Trading](https://github.com/darkvolg/Trading) — GPL-3.0. Its
  TrendRider strategy was evaluated as an external Bybit-perpetual candidate;
  its source was not copied into this MIT repository.
- [freqtrade/freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies)
  and [Strategy005.py](https://github.com/freqtrade/freqtrade-strategies/blob/main/user_data/strategies/Strategy005.py)
  — GPL-3.0. Strategy005 was run from a temporary external checkout and is
  not redistributed here.
- [zodboy/freqtrade-simple-mean-reversion](https://github.com/zodboy/freqtrade-simple-mean-reversion)
  — MIT. Its general mean-reversion idea was used as a clean-license control;
  the public strategy in this repository is an independent implementation.
- [Analysis Pairs Trading Strategy Applied to the Cryptocurrency Market](https://doi.org/10.1007/s10614-025-11149-y)
  — Ramos-Requena and Bağcı (2026). This supports the research motivation for
  residual/pairs analysis; no paper text or code is redistributed.
