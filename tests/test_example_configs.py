import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_example_configs_are_safe() -> None:
    for path in (ROOT / "examples").glob("config.*.json"):
        config = json.loads(path.read_text(encoding="utf-8"))
        assert config["dry_run"] is True
        assert config["api_server"]["enabled"] is False
        assert config["telegram"]["enabled"] is False
        assert not config["exchange"]["key"]
        assert not config["exchange"]["secret"]
        assert not config["exchange"]["password"]
