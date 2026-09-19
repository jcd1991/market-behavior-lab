from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_layout_is_present() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / "examples/config.backtest.example.json",
        ROOT / "examples/config.backtest.okx.expanded.example.json",
        ROOT / "examples/config.backtest.okx.btc-eth.example.json",
        ROOT / "examples/config.backtest.okx.majors.example.json",
        ROOT / "examples/config.dry-run.example.json",
        ROOT / "examples/config.backtest.binanceus.spot.example.json",
        ROOT / "user_data/strategies/RegimeRouted.py",
        ROOT / "user_data/strategies/RegimeRoutedAsiaWindow.py",
        ROOT / "user_data/strategies/RegimeRoutedFundingFilter.py",
        ROOT / "user_data/strategies/RegimeRoutedBasisOI.py",
        ROOT / "user_data/strategies/HurstRegimeSwitch.py",
        ROOT / "user_data/strategies/hurst.py",
        ROOT / "user_data/strategies/lib/regime_detector.py",
        ROOT / "docs/references.md",
        ROOT / "scripts/export_lab_run.py",
        ROOT / "research/evaluation/bootstrap_trades.py",
        ROOT / "research/evaluation/simulate_sleeves.py",
        ROOT / "research/evaluation/walk_forward_report.py",
        ROOT / "research/evaluation/benchmark_buy_hold.py",
        ROOT / "user_data/strategies/market_context.py",
        ROOT / "research/evaluation/derivative_manifest.py",
        ROOT / "research/evaluation/derivative_features.py",
        ROOT / "research/evaluation/liquidation_events.py",
        ROOT / "research/evaluation/hurst.py",
        ROOT / "research/evaluation/ghe.py",
        ROOT / "research/evaluation/frequency_sensitivity.py",
        ROOT / "research/evaluation/orderbook_cost_snapshot.py",
        ROOT / "user_data/strategies/RelativeValueGHE.py",
        ROOT / "user_data/strategies/ghe.py",
        ROOT / "research/evaluation/advanced_strategies.py",
        ROOT / "user_data/strategies/advanced_strategy_helpers.py",
        ROOT / "user_data/strategies/RegimeRoutedVolTarget.py",
        ROOT / "user_data/strategies/JumpAwareRegimeRouted.py",
        ROOT / "user_data/strategies/CryptoFactorEnsemble.py",
        ROOT / "user_data/strategies/VolatilityManagedMomentum.py",
        ROOT / "user_data/strategies/ClusterRotation.py",
        ROOT / "user_data/strategies/KalmanResidual.py",
        ROOT / "scripts/backfill_okx_derivatives.sh",
        ROOT / "user_data/strategies/CryptoMomentumRotation.py",
        ROOT / "user_data/strategies/CryptoMomentumRotationSpot.py",
        ROOT / "user_data/strategies/ScheduledPortfolioRotation.py",
        ROOT / "user_data/strategies/StandaloneBreakoutTrend.py",
        ROOT / "user_data/strategies/StandaloneBreakoutTrendSpot.py",
        ROOT / "user_data/strategies/StandaloneBreakoutTrendSpotGuarded.py",
        ROOT / "user_data/strategies/VolatilityConditionedReversal.py",
        ROOT / "user_data/strategies/SizeLiquidityDualSignal.py",
        ROOT / "user_data/strategies/DispersionConditionedMomentum.py",
        ROOT / "user_data/strategies/MultiHorizonTrendReversal.py",
        ROOT / "user_data/strategies/BetaNeutralResidualPortfolio.py",
        ROOT / "user_data/strategies/RelativeValueStatArb.py",
        ROOT / "user_data/strategies/FundingBasisCarry.py",
        ROOT / "user_data/strategies/VolatilityCrashGuard.py",
        ROOT / "user_data/strategies/research_strategy_helpers.py",
    ]
    assert all(path.is_file() for path in expected)


def test_public_source_has_no_old_private_headers() -> None:
    source_dir = ROOT / "user_data/strategies"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_dir.glob("*.py"))
    assert "Private " + "— do not redistribute" not in source
    assert "Ported from " + "aitrader" not in source
