from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_layout_is_present() -> None:
    expected = [
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / "examples/config.backtest.example.json",
        ROOT / "examples/config.dry-run.example.json",
        ROOT / "user_data/strategies/RegimeRouted.py",
        ROOT / "user_data/strategies/lib/regime_detector.py",
        ROOT / "docs/references.md",
    ]
    assert all(path.is_file() for path in expected)


def test_public_source_has_no_old_private_headers() -> None:
    source_dir = ROOT / "user_data/strategies"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_dir.glob("*.py"))
    assert "Private " + "— do not redistribute" not in source
    assert "Ported from " + "aitrader" not in source
