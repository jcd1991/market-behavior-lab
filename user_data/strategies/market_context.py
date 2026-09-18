"""Small venue-aware helpers shared by crypto strategies and exports."""

from __future__ import annotations

class PairContext:
    __slots__ = ("raw", "canonical", "base", "quote", "settlement", "market_type")

    def __init__(self, raw: str, canonical: str, base: str, quote: str, settlement: str | None, market_type: str) -> None:
        self.raw = raw
        self.canonical = canonical
        self.base = base
        self.quote = quote
        self.settlement = settlement
        self.market_type = market_type


def market_type_from_config(config: dict) -> str:
    return "futures" if str(config.get("trading_mode", "spot")).lower() == "futures" else "spot"


def is_futures_config(config: dict) -> bool:
    return market_type_from_config(config) == "futures"


def parse_pair(raw: str, market_type: str | None = None) -> PairContext:
    value = str(raw or "").strip().upper()
    if "/" not in value:
        raise ValueError(f"invalid crypto pair: {raw!r}")
    base, rest = value.split("/", 1)
    quote, separator, settlement = rest.partition(":")
    quote = quote.strip()
    settlement = settlement.strip() or None
    inferred = "futures" if settlement else "spot"
    actual_type = market_type or inferred
    if actual_type not in {"spot", "futures"}:
        raise ValueError(f"invalid market type: {actual_type!r}")
    if actual_type == "spot" and settlement:
        raise ValueError(f"spot pair cannot contain settlement suffix: {raw!r}")
    if actual_type == "futures" and not settlement:
        settlement = quote
    canonical = f"{base}/{quote}:{settlement}" if actual_type == "futures" else f"{base}/{quote}"
    return PairContext(value, canonical, base, quote, settlement, actual_type)


def reference_pair(asset: str, config: dict, quote: str = "USDT") -> str:
    base = str(asset or "").strip().upper()
    quote = str(quote or "USDT").strip().upper()
    return f"{base}/{quote}:{quote}" if is_futures_config(config) else f"{base}/{quote}"


def derivative_candle_types(config: dict) -> tuple[str, ...]:
    return ("mark", "index", "funding_rate") if is_futures_config(config) else ()
