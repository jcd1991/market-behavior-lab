import json
import zipfile
from pathlib import Path

from research.evaluation.synchronized_allocator import InputLane, simulate


def make_export(path: Path, trades: list[dict]) -> None:
    payload = {"strategy": {"Demo": {"trades": trades}}}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("result.json", json.dumps(payload))


def test_allocator_rejects_same_pair_overlap_and_applies_cost(tmp_path: Path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    trade = {"open_date": "2026-01-01 00:00:00", "close_date": "2026-01-02 00:00:00", "pair": "BTC/USD", "profit_ratio": 0.10}
    make_export(first, [trade])
    make_export(second, [trade])
    result = simulate([
        InputLane("first", first, 1.0),
        InputLane("second", second, 1.0),
    ], extra_round_trip_cost=0.02)
    assert result["accepted"] == 1
    assert result["rejections"] == {"pair_overlap": 1}
    assert result["profit_pct"] == 1.333333333333342
