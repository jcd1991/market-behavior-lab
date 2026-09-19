import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "evaluation"))

from walk_forward_report import summarize_runs  # noqa: E402


def test_summarize_runs_reports_labeled_export(tmp_path: Path) -> None:
    import json
    import zipfile

    payload = {"strategy": {"Demo": {"trades": [{"profit_abs": 2.0}, {"profit_abs": -1.0}]}}}
    archive = tmp_path / "run.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("result.json", json.dumps(payload))

    result = summarize_runs([("window-a", archive)], strategy="Demo", iterations=100, seed=7)
    assert result[0]["label"] == "window-a"
    assert result[0]["n_trades"] == 2
    assert result[0]["observed"]["profit_abs"] == 1.0
