import json
from pathlib import Path

import pandas as pd

from scripts.export_lab_run import export_run


def test_export_run_writes_contract_and_redacts_local_paths(tmp_path: Path) -> None:
    export = tmp_path / "result.json"
    export.write_text(json.dumps({"strategy": {"Demo": {"trades": [{"pair": "BTC/USDT", "profit_abs": 1.5, "profit_ratio": 0.01, "is_short": False}]}}}))
    export.with_name("result_config.json").write_text(json.dumps({
        "strategy": "Demo", "trading_mode": "spot", "timeframe": "1h", "dry_run_wallet": 1000,
        "stake_currency": "USDT", "exchange": {"name": "binanceus", "pair_whitelist": ["BTC/USDT"]},
        "config_files": ["/Applications/MAMP/htdocs/private-config.json"],
    }))
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"date": pd.to_datetime(["2024-01-01T00:00:00Z"]), "open": [1], "high": [2], "low": [0.5], "close": [1.5], "volume": [10]}).to_feather(data / "BTC_USDT-1h.feather")

    output = export_run(export, data, tmp_path / "run", None)
    assert {p.name for p in output.iterdir()} == {"run.json", "candles.parquet", "regimes.json", "signals.json", "trades.json", "metrics.json"}
    run = json.loads((output / "run.json").read_text())
    assert run["market_type"] == "spot"
    assert run["config"]["config_files"] == ["private-config.json"]
    assert "/Applications" not in (output / "run.json").read_text()
