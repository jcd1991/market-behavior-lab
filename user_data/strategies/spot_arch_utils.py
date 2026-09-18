import json
import os
from pathlib import Path

from freqtrade.optimize.hyperopt_tools import HyperoptTools
from market_context import parse_pair


def base_asset(pair: str) -> str:
    token = str(pair or "").strip().upper()
    if not token:
        return ""
    if "/" in token:
        return token.split("/", 1)[0].strip()
    return token


def quote_asset(pair: str) -> str:
    try:
        return parse_pair(pair).quote
    except ValueError:
        return ""


def asset_set_from_pairs(pairs: set[str] | list[str] | tuple[str, ...]) -> set[str]:
    return {base_asset(pair) for pair in pairs if base_asset(pair)}


def current_whitelist(strategy) -> list[str]:
    try:
        pairs = list(strategy.dp.current_whitelist() or [])
    except Exception:
        pairs = list(strategy.config.get("exchange", {}).get("pair_whitelist", []))
    return [pair for pair in pairs if pair]


def resolve_pair_by_asset(strategy, asset: str, preferred_quotes: tuple[str, ...] = ("USDT", "USD", "USDC")) -> str | None:
    asset = str(asset or "").strip().upper()
    if not asset:
        return None
    candidates = [pair for pair in current_whitelist(strategy) if base_asset(pair) == asset]
    if not candidates:
        return None

    priority_map = {quote: idx for idx, quote in enumerate(preferred_quotes)}

    def _sort_key(pair: str) -> tuple[int, str]:
        return (priority_map.get(quote_asset(pair), len(priority_map) + 1), pair)

    candidates.sort(key=_sort_key)
    return candidates[0]


def load_strategy_params(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return HyperoptTools.load_params(path)
    except ValueError:
        return {}


def apply_runtime_overrides(params: dict, env_name: str) -> dict:
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return params

    try:
        overrides = json.loads(raw)
    except json.JSONDecodeError:
        return params
    if not isinstance(overrides, dict):
        return params

    payload = dict(params.get("params", {}))
    for space in ("buy", "sell", "roi", "trailing", "max_open_trades", "stoploss"):
        space_overrides = overrides.get(space, {})
        if isinstance(space_overrides, dict):
            merged = dict(payload.get(space, {}))
            merged.update(space_overrides)
            payload[space] = merged

    for key, value in overrides.items():
        if key.startswith(("buy_", "sell_")):
            space = "buy" if key.startswith("buy_") else "sell"
            merged = dict(payload.get(space, {}))
            merged[key] = value
            payload[space] = merged

    params["params"] = payload
    return params
