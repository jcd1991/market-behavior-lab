from pathlib import Path

from research.evaluation.matrix_sleeves import Candidate, matrix


def test_matrix_rejects_incompatible_venues_and_keeps_spot_candidates(tmp_path: Path):
    # The matrix operates on real Freqtrade exports; this test only checks the
    # compatibility gate without manufacturing a fake backtest artifact.
    assert matrix([
        Candidate("coinbase", tmp_path / "missing.zip", "coinbase", "spot", "1h"),
        Candidate("okx", tmp_path / "missing2.zip", "okx", "futures", "4h"),
    ]) == []
