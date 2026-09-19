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
        ROOT / "user_data/strategies/RelativeValueGHE.py",
        ROOT / "user_data/strategies/ghe.py",
        ROOT / "scripts/backfill_okx_derivatives.sh",
    ]
    assert all(path.is_file() for path in expected)


def test_public_source_has_no_old_private_headers() -> None:
    source_dir = ROOT / "user_data/strategies"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_dir.glob("*.py"))
    assert "Private " + "— do not redistribute" not in source
    assert "Ported from " + "aitrader" not in source
