"""Causal evaluators for the next Market Behavior Lab research lanes.

This module is intentionally independent of Freqtrade's strategy scheduler so
that the research can compare a shared wallet, an ensemble, and a portfolio
with the same cost model.  It uses next-candle opens for fills and never uses
future candles to form a signal.  Results from a static local universe are
screening evidence; they are not a point-in-time universe or execution claim.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    fee_bps_per_side: float = 10.0
    spread_bps_round_trip: float = 10.0
    slippage_bps_round_trip: float = 10.0
    safety_bps_round_trip: float = 0.0

    @property
    def round_trip_bps(self) -> float:
        return 2.0 * self.fee_bps_per_side + self.spread_bps_round_trip + self.slippage_bps_round_trip + self.safety_bps_round_trip


@dataclass(frozen=True)
class BreakoutPolicy:
    horizons: tuple[int, ...] = (12, 24, 48, 96)
    votes: int = 3
    atr_max: float = 0.20
    breakout_buffer: float = 0.002
    exit_ema: int = 24
    volume_ratio_min: float = 0.0
    min_move_bps: float = 0.0


@dataclass(frozen=True)
class MarketOverlay:
    mode: str = "none"
    ema_window: int = 96
    drawdown_window: int = 180
    half_size_drawdown: float = 0.15
    off_size_drawdown: float = 0.30


@dataclass(frozen=True)
class MomentumPolicy:
    lookback: int = 42
    rebalance_every: int = 6
    holdings: int = 2
    min_quote_volume_ratio: float = 0.50
    max_pair_weight: float = 0.50
    trend_window: int = 42
    cash_below_market_trend: bool = True


def load_candles(data_dir: Path, pairs: Iterable[str], timeframe: str = "4h") -> dict[str, pd.DataFrame]:
    """Load the exact local Freqtrade-style candle files for a static screen."""
    output: dict[str, pd.DataFrame] = {}
    for pair in pairs:
        filename = pair.replace("/", "_").replace(":", "_") + f"-{timeframe}.feather"
        path = data_dir / filename
        if not path.is_file():
            continue
        frame = pd.read_feather(path)
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(frame.columns):
            raise ValueError(f"{path} missing columns: {sorted(required - set(frame.columns))}")
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").drop_duplicates("date")
        frame["pair"] = pair
        if not frame.empty:
            output[pair] = frame.reset_index(drop=True)
    return output


def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    previous = frame["close"].shift(1)
    true_range = pd.concat(
        [frame["high"] - frame["low"], (frame["high"] - previous).abs(), (frame["low"] - previous).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=window).mean()


def _features(frame: pd.DataFrame, policy: BreakoutPolicy) -> pd.DataFrame:
    work = frame.copy()
    work["atr_pct"] = _atr(work) / work["close"].replace(0.0, np.nan)
    work["ema"] = work["close"].ewm(span=policy.exit_ema, adjust=False, min_periods=policy.exit_ema).mean()
    for horizon in policy.horizons:
        work[f"upper_{horizon}"] = work["high"].rolling(horizon, min_periods=horizon).max().shift(1)
        work[f"lower_{horizon}"] = work["low"].rolling(horizon, min_periods=horizon).min().shift(1)
    upper = pd.concat([work[f"upper_{horizon}"] for horizon in policy.horizons], axis=1)
    lower = pd.concat([work[f"lower_{horizon}"] for horizon in policy.horizons], axis=1)
    work["long_votes"] = (work["close"].to_numpy()[:, None] > upper.to_numpy() * (1.0 + policy.breakout_buffer)).sum(axis=1)
    work["short_votes"] = (work["close"].to_numpy()[:, None] < lower.to_numpy() * (1.0 - policy.breakout_buffer)).sum(axis=1)
    quote_volume = work["close"].abs() * work["volume"].clip(lower=0.0)
    work["volume_ratio"] = quote_volume / quote_volume.rolling(max(6, min(policy.horizons)), min_periods=max(6, min(policy.horizons) // 2)).median().replace(0.0, np.nan)
    work["long_move_bps"] = (work["close"] / upper.min(axis=1) - 1.0) * 10000.0
    work["short_move_bps"] = (1.0 - work["close"] / lower.max(axis=1)) * 10000.0
    return work


def _trade_frame(
    frame: pd.DataFrame,
    policy: BreakoutPolicy,
    costs: CostModel,
    *,
    side: str = "long",
    overlay_scale: pd.Series | None = None,
) -> pd.DataFrame:
    work = _features(frame, policy)
    signal = work["long_votes"].ge(policy.votes) if side == "long" else work["short_votes"].ge(policy.votes)
    signal &= work["atr_pct"].le(policy.atr_max)
    if policy.volume_ratio_min > 0:
        signal &= work["volume_ratio"].ge(policy.volume_ratio_min)
    if policy.min_move_bps > 0:
        signal &= (work["long_move_bps"] if side == "long" else work["short_move_bps"]).ge(policy.min_move_bps)
    entry_price = work["open"].shift(-1)
    exit_signal = work["close"].lt(work["ema"]) if side == "long" else work["close"].gt(work["ema"])
    rows: list[dict[str, Any]] = []
    open_index: int | None = None
    for index in range(len(work) - 1):
        if open_index is None and bool(signal.iloc[index]):
            open_index = index + 1
            continue
        if open_index is None or index <= open_index:
            continue
        if bool(exit_signal.iloc[index]) or index == len(work) - 2:
            close_index = index + 1 if index + 1 < len(work) else index
            entry = float(work.iloc[open_index]["open"])
            exit_price = float(work.iloc[close_index]["open"] if close_index < len(work) else work.iloc[-1]["close"])
            gross = exit_price / entry - 1.0 if side == "long" else entry / exit_price - 1.0
            scale = float(overlay_scale.iloc[open_index]) if overlay_scale is not None else 1.0
            rows.append(
                {
                    "pair": str(work.iloc[0]["pair"]),
                    "side": side,
                    "open_time": work.iloc[open_index]["date"],
                    "close_time": work.iloc[close_index]["date"],
                    "gross_ratio": gross,
                    "cost_ratio": costs.round_trip_bps / 10000.0,
                    "profit_ratio": scale * gross - costs.round_trip_bps / 10000.0,
                    "size_scale": scale,
                    "entry_price": entry,
                    "exit_price": exit_price,
                }
            )
            open_index = None
    return pd.DataFrame(rows)


def market_overlay_scale(btc: pd.DataFrame, overlay: MarketOverlay) -> pd.Series:
    """Return a position-size scale aligned to BTC timestamps."""
    dates = pd.DatetimeIndex(pd.to_datetime(btc["date"], utc=True).astype("datetime64[ns, UTC]")) if "date" in btc else btc.index
    if btc.empty or overlay.mode == "none":
        return pd.Series(1.0, index=dates, dtype=float)
    close = btc["close"]
    ema = close.ewm(span=overlay.ema_window, adjust=False, min_periods=overlay.ema_window).mean()
    peak = close.rolling(overlay.drawdown_window, min_periods=overlay.drawdown_window).max()
    drawdown = close / peak.replace(0.0, np.nan) - 1.0
    scale = pd.Series(1.0, index=dates, dtype=float)
    if overlay.mode in {"trend", "trend_drawdown"}:
        scale.iloc[np.flatnonzero(close.le(ema).fillna(False).to_numpy())] = 0.0
    if overlay.mode == "trend_drawdown":
        scale.iloc[np.flatnonzero(drawdown.le(-abs(overlay.off_size_drawdown)).fillna(False).to_numpy())] = 0.0
        half = drawdown.le(-abs(overlay.half_size_drawdown)).fillna(False).to_numpy() & scale.gt(0).to_numpy()
        scale.iloc[np.flatnonzero(half)] = 0.5
    return scale.ffill().fillna(0.0)


def _align_scale(scale: pd.Series, target: pd.Series) -> pd.Series:
    left_dates = pd.to_datetime(target, utc=True).astype("datetime64[ns, UTC]")
    right_dates = pd.to_datetime(scale.index, utc=True).astype("datetime64[ns, UTC]")
    left = pd.DataFrame({"date": left_dates, "target": range(len(target))}).sort_values("date")
    right = pd.DataFrame({"date": right_dates, "scale": scale.to_numpy()}).sort_values("date")
    merged = pd.merge_asof(left, right, on="date", direction="backward")
    return merged.sort_values("target")["scale"].fillna(0.0).reset_index(drop=True)


def _shared_wallet(trades: pd.DataFrame, *, starting_balance: float = 1000.0, max_open: int = 2, pair_cap: float = 0.50) -> dict[str, Any]:
    if trades.empty:
        return {"starting_balance": starting_balance, "final_balance": starting_balance, "profit_pct": 0.0, "accepted": 0, "rejected": 0, "max_drawdown_pct": 0.0}
    frame = trades.sort_values(["open_time", "close_time", "pair"]).reset_index(drop=True)
    active: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    rejected = 0
    balance = float(starting_balance)
    equity_points = [balance]
    for row in frame.to_dict("records"):
        still_open: list[dict[str, Any]] = []
        for position in active:
            if position["close_time"] <= row["open_time"]:
                balance += position["stake"] * float(position["profit_ratio"])
                equity_points.append(balance)
            else:
                still_open.append(position)
        active = still_open
        if len(active) >= max_open or any(position["pair"] == row["pair"] for position in active):
            rejected += 1
            continue
        stake = min(balance / max_open, balance * pair_cap)
        if stake <= 0:
            rejected += 1
            continue
        position = {**row, "stake": stake}
        active.append(position)
        accepted.append(position)
    for position in active:
        balance += position["stake"] * float(position["profit_ratio"])
        equity_points.append(balance)
    equity = pd.Series(equity_points, dtype=float)
    drawdown = (equity / equity.cummax() - 1.0).min() * -100.0
    return {
        "starting_balance": starting_balance,
        "final_balance": balance,
        "profit_abs": balance - starting_balance,
        "profit_pct": (balance / starting_balance - 1.0) * 100.0,
        "accepted": len(accepted),
        "rejected": rejected,
        "max_drawdown_pct": float(drawdown),
        "mean_size_scale": float(np.mean([row.get("size_scale", 1.0) for row in accepted])) if accepted else 0.0,
    }


def evaluate_breakout(candles: dict[str, pd.DataFrame], policy: BreakoutPolicy = BreakoutPolicy(), costs: CostModel = CostModel(), overlay: MarketOverlay = MarketOverlay(), *, start: str | None = None, end: str | None = None, side: str = "long") -> dict[str, Any]:
    selected: dict[str, pd.DataFrame] = {}
    for pair, frame in candles.items():
        work = frame.copy()
        if start:
            work = work[work["date"] >= pd.Timestamp(start, tz="UTC")]
        if end:
            work = work[work["date"] < pd.Timestamp(end, tz="UTC")]
        if len(work) >= max(max(policy.horizons), policy.exit_ema) + 5:
            selected[pair] = work.reset_index(drop=True)
    btc = selected.get("BTC/USDT", candles.get("BTC/USDT", pd.DataFrame()))
    scale = market_overlay_scale(btc, overlay) if not btc.empty else pd.Series(dtype=float)
    rows = []
    for pair, frame in selected.items():
        aligned = _align_scale(scale, frame["date"]) if not scale.empty else None
        rows.append(_trade_frame(frame, policy, costs, side=side, overlay_scale=aligned))
    trades = pd.concat([row for row in rows if not row.empty], ignore_index=True) if any(not row.empty for row in rows) else pd.DataFrame()
    result = _shared_wallet(trades)
    result.update({"lane": "breakout", "policy": asdict(policy), "overlay": asdict(overlay), "costs": asdict(costs), "pairs": sorted(selected), "trades_generated": int(len(trades)), "start": start, "end": end, "side": side})
    return result


def _momentum_rebalance(candles: dict[str, pd.DataFrame], policy: MomentumPolicy, costs: CostModel, *, start: str | None, end: str | None) -> dict[str, Any]:
    prepared: dict[str, pd.DataFrame] = {}
    for pair, frame in candles.items():
        work = frame.copy()
        if start:
            work = work[work["date"] >= pd.Timestamp(start, tz="UTC")]
        if end:
            work = work[work["date"] < pd.Timestamp(end, tz="UTC")]
        work = work.reset_index(drop=True)
        work["momentum"] = work["close"].pct_change(policy.lookback)
        work["trend"] = work["close"] > work["close"].rolling(policy.trend_window, min_periods=policy.trend_window).mean()
        quote = work["close"].abs() * work["volume"].clip(lower=0.0)
        work["volume_ratio"] = quote / quote.rolling(policy.lookback, min_periods=max(6, policy.lookback // 2)).median().replace(0.0, np.nan)
        prepared[pair] = work
    if not prepared:
        return {"lane": "momentum", "eligible": False, "reason": "no_candles"}
    dates = sorted(set().union(*(set(frame["date"]) for frame in prepared.values())))
    btc = prepared.get("BTC/USDT")
    btc_by_date = btc.set_index("date") if btc is not None else pd.DataFrame()
    balance = 1000.0
    previous: dict[str, float] = {}
    turnovers: list[float] = []
    curve = [balance]
    rebalances = 0
    held_bars = 0
    for step, date in enumerate(dates[:-1]):
        if step % max(1, policy.rebalance_every) == 0:
            observations = []
            for pair, frame in prepared.items():
                match = frame[frame["date"] == date]
                if match.empty:
                    continue
                row = match.iloc[-1]
                if pd.notna(row["momentum"]) and pd.notna(row["volume_ratio"]):
                    observations.append({"pair": pair, "momentum": float(row["momentum"]), "volume_ratio": float(row["volume_ratio"]), "trend": bool(row["trend"])})
            market_on = True
            if policy.cash_below_market_trend and not btc_by_date.empty and date in btc_by_date.index:
                market_on = bool(btc_by_date.loc[date, "trend"])
            ranked = [row for row in sorted(observations, key=lambda item: item["momentum"], reverse=True) if row["volume_ratio"] >= policy.min_quote_volume_ratio and row["trend"] and market_on]
            selected = ranked[:max(0, policy.holdings)]
            target = {row["pair"]: min(policy.max_pair_weight, 1.0 / max(1, len(selected))) for row in selected}
            turnover = sum(abs(target.get(pair, 0.0) - previous.get(pair, 0.0)) for pair in set(target) | set(previous))
            balance *= max(0.0, 1.0 - turnover * costs.round_trip_bps / 10000.0)
            turnovers.append(turnover)
            previous = target
            rebalances += 1
        next_date = dates[step + 1]
        for pair, weight in previous.items():
            frame = prepared[pair]
            now = frame[frame["date"] == date]
            nxt = frame[frame["date"] == next_date]
            if not now.empty and not nxt.empty:
                balance *= max(0.0, 1.0 + weight * (float(nxt.iloc[-1]["close"]) / float(now.iloc[-1]["close"]) - 1.0))
        curve.append(balance)
        held_bars += 1 if previous else 0
    equity = pd.Series(curve, dtype=float)
    dd = (equity / equity.cummax() - 1.0).min() * -100.0
    return {
        "lane": "momentum", "eligible": True, "observations": len(dates), "rebalances": rebalances,
        "final_balance": balance, "profit_abs": balance - 1000.0, "profit_pct": (balance / 1000.0 - 1.0) * 100.0,
        "max_drawdown_pct": float(dd), "mean_turnover": float(np.mean(turnovers)) if turnovers else 0.0,
        "policy": asdict(policy), "costs": asdict(costs), "static_universe": sorted(prepared), "held_rebalance_count": held_bars,
    }


def evaluate_momentum(candles: dict[str, pd.DataFrame], policy: MomentumPolicy = MomentumPolicy(), costs: CostModel = CostModel(), *, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    return _momentum_rebalance(candles, policy, costs, start=start, end=end)


def tune_breakout(candles: dict[str, pd.DataFrame], costs: CostModel, *, train_start: str, train_end: str) -> list[dict[str, Any]]:
    """Small predeclared grid; callers must evaluate the winner out of sample."""
    candidates = []
    for horizons, votes, min_move in itertools.product(((12, 24, 48, 96), (18, 36, 72, 144), (24, 48, 96, 192)), (2, 3), (0.0, 20.0, 40.0)):
        if votes > len(horizons):
            continue
        policy = BreakoutPolicy(horizons=horizons, votes=votes, min_move_bps=min_move)
        result = evaluate_breakout(candles, policy, costs, start=train_start, end=train_end)
        candidates.append(result)
    return sorted(candidates, key=lambda row: (row.get("profit_pct", -999.0), -row.get("max_drawdown_pct", 999.0)), reverse=True)


def tune_momentum(candles: dict[str, pd.DataFrame], costs: CostModel, *, train_start: str, train_end: str) -> list[dict[str, Any]]:
    candidates = []
    for lookback, rebalance, holdings, volume_floor in itertools.product((18, 42, 84), (3, 6, 12), (1, 2), (0.5, 1.0)):
        policy = MomentumPolicy(lookback=lookback, rebalance_every=rebalance, holdings=holdings, min_quote_volume_ratio=volume_floor)
        candidates.append(evaluate_momentum(candles, policy, costs, start=train_start, end=train_end))
    return sorted(candidates, key=lambda row: (row.get("profit_pct", -999.0), -row.get("max_drawdown_pct", 999.0)), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2024-06-01")
    parser.add_argument("--end", default="2026-04-14")
    args = parser.parse_args()
    pairs = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT")
    candles = load_candles(args.data_dir, pairs)
    costs = CostModel()
    frozen = evaluate_breakout(candles, costs=costs, start=args.start, end=args.end)
    guard = evaluate_breakout(candles, costs=costs, overlay=MarketOverlay(mode="trend_drawdown"), start=args.start, end=args.end)
    liquidity = evaluate_breakout(candles, costs=costs, policy=BreakoutPolicy(volume_ratio_min=0.75, min_move_bps=20.0), start=args.start, end=args.end)
    momentum = evaluate_momentum(candles, costs=costs, start=args.start, end=args.end)
    train_end = "2025-07-01"
    breakout_grid = tune_breakout(candles, costs, train_start=args.start, train_end=train_end)
    momentum_grid = tune_momentum(candles, costs, train_start=args.start, train_end=train_end)
    winner = breakout_grid[0] if breakout_grid else frozen
    tuned_oos = evaluate_breakout(candles, BreakoutPolicy(**winner["policy"]), costs, start=train_end, end=args.end)
    mom_winner = momentum_grid[0] if momentum_grid else momentum
    mom_oos = evaluate_momentum(candles, MomentumPolicy(**mom_winner["policy"]), costs, start=train_end, end=args.end)
    report = {
        "schema_version": "recommended-lanes.v1", "source": "project-local Freqtrade candle files", "venue_label": "historical venue labels are inherited from the local files; not re-verified here",
        "data_dir": str(args.data_dir), "pairs": sorted(candles), "timeframe": "4h", "costs": asdict(costs),
        "full_window": {"start": args.start, "end": args.end, "breakout_frozen": frozen, "breakout_crash_overlay": guard, "breakout_liquidity_filter": liquidity, "momentum_static_universe": momentum},
        "tuning": {"train_window": {"start": args.start, "end": train_end}, "breakout_top5": breakout_grid[:5], "momentum_top5": momentum_grid[:5], "breakout_winner_forward": tuned_oos, "momentum_winner_forward": mom_oos},
        "data_gates": {"carry": {"status": "blocked_without_same_venue_index_and_matched_spot_perp_execution"}, "orderflow": {"status": "blocked_without_historical_tick_and_L2_replay"}, "universe": {"status": "static_screen_only; point_in_time_membership_required_for_promotion"}},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
