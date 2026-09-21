"""Approximate a shared-wallet allocator from independent Freqtrade exports.

The input strategies were backtested independently, so this cannot recreate
their original signal competition. It does, however, enforce a single wallet,
strategy sleeve budgets, a maximum number of open positions, pair overlap
handling, concentration caps, and an additional round-trip cost stress.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class InputLane:
    name: str
    path: Path
    weight: float
    priority: int = 0


def load_trades(path: Path, lane: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".json") and "config" not in n]
        if not names:
            raise ValueError(f"no result JSON in {path}")
        payload = json.loads(archive.read(names[0]))
    strategies = payload.get("strategy", {})
    rows = []
    for result in strategies.values():
        for trade in result.get("trades", []):
            open_date = pd.to_datetime(trade.get("open_date"), utc=True, errors="coerce")
            close_date = pd.to_datetime(trade.get("close_date"), utc=True, errors="coerce")
            if pd.isna(open_date) or pd.isna(close_date):
                continue
            ratio = trade.get("profit_ratio")
            if ratio is None:
                ratio = trade.get("profit_pct", 0.0) / 100.0
            rows.append({
                "lane": lane,
                "open_date": open_date,
                "close_date": close_date,
                "pair": trade.get("pair", ""),
                "profit_ratio": float(ratio or 0.0),
            })
    return pd.DataFrame(rows)


def simulate(
    lanes: list[InputLane],
    starting_balance: float = 1000.0,
    max_open: int = 3,
    pair_cap: float = 0.40,
    extra_round_trip_cost: float = 0.0,
) -> dict:
    if not lanes or sum(lane.weight for lane in lanes) <= 0:
        raise ValueError("at least one lane with positive weight is required")
    total_weight = sum(lane.weight for lane in lanes)
    frames = [load_trades(lane.path, lane.name) for lane in lanes]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if frame.empty:
        return {"starting_balance": starting_balance, "final_balance": starting_balance, "profit_pct": 0.0, "accepted": 0, "rejected": 0}

    lane_weights = {lane.name: lane.weight / total_weight for lane in lanes}
    priorities = {lane.name: lane.priority for lane in lanes}
    events = []
    for _, trade in frame.iterrows():
        events.append((trade["open_date"], 1, trade))
        events.append((trade["close_date"], 0, trade))
    events.sort(key=lambda item: (item[0], item[1], priorities.get(item[2]["lane"], 0)))

    balance = float(starting_balance)
    open_positions: dict[int, dict] = {}
    rejected: dict[str, int] = {}
    accepted = []
    frame = frame.reset_index(drop=True)
    frame["trade_id"] = range(len(frame))
    # Rebuild events after adding stable ids.
    events = []
    for _, trade in frame.iterrows():
        events.append((trade["open_date"], 1, trade))
        events.append((trade["close_date"], 0, trade))
    events.sort(key=lambda item: (item[0], item[1], priorities.get(item[2]["lane"], 0)))

    for _, event_type, trade in events:
        trade_id = int(trade["trade_id"])
        if event_type == 0:
            position = open_positions.pop(trade_id, None)
            if position is not None:
                ratio = float(trade["profit_ratio"]) - float(extra_round_trip_cost)
                balance += position["stake"] * ratio
                accepted.append({**position, "profit_abs": position["stake"] * ratio})
            continue
        if len(open_positions) >= max_open:
            rejected["max_open"] = rejected.get("max_open", 0) + 1
            continue
        if any(pos["pair"] == trade["pair"] for pos in open_positions.values()):
            rejected["pair_overlap"] = rejected.get("pair_overlap", 0) + 1
            continue
        sleeve_budget = balance * lane_weights[trade["lane"]]
        current_lane = sum(pos["stake"] for pos in open_positions.values() if pos["lane"] == trade["lane"])
        if current_lane >= sleeve_budget:
            rejected["lane_budget"] = rejected.get("lane_budget", 0) + 1
            continue
        # Spread each lane's capital budget across the configured capacity so
        # one early signal cannot consume the entire sleeve.
        per_position_budget = sleeve_budget / max_open
        stake = min(per_position_budget, sleeve_budget - current_lane, balance * pair_cap)
        if stake <= 0:
            rejected["pair_cap"] = rejected.get("pair_cap", 0) + 1
            continue
        open_positions[trade_id] = {"trade_id": trade_id, "lane": trade["lane"], "pair": trade["pair"], "stake": stake, "open_date": trade["open_date"]}

    # The Freqtrade report force-closes positions at the end of the window.
    for trade_id, position in list(open_positions.items()):
        trade = frame.iloc[trade_id]
        ratio = float(trade["profit_ratio"]) - float(extra_round_trip_cost)
        balance += position["stake"] * ratio
        accepted.append({**position, "profit_abs": position["stake"] * ratio, "force_closed": True})

    equity = pd.Series([starting_balance] + [starting_balance + sum(item["profit_abs"] for item in accepted[:i]) for i in range(1, len(accepted) + 1)])
    drawdown = equity / equity.cummax() - 1.0
    return {
        "starting_balance": starting_balance,
        "final_balance": balance,
        "profit_abs": balance - starting_balance,
        "profit_pct": (balance / starting_balance - 1.0) * 100.0,
        "max_drawdown_pct": abs(float(drawdown.min())) * 100.0,
        "accepted": len(accepted),
        "rejected": sum(rejected.values()),
        "rejections": rejected,
        "open_at_end_force_closed": sum(1 for item in accepted if item.get("force_closed")),
        "pair_cap": pair_cap,
        "max_open": max_open,
        "extra_round_trip_cost": extra_round_trip_cost,
        "lanes": [{"name": lane.name, "weight": lane.weight} for lane in lanes],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", action="append", required=True, help="name:weight:path-to-freqtrade-zip")
    parser.add_argument("--starting-balance", type=float, default=1000.0)
    parser.add_argument("--max-open", type=int, default=3)
    parser.add_argument("--pair-cap", type=float, default=0.40)
    parser.add_argument("--extra-round-trip-cost", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    lanes = []
    for value in args.lane:
        name, weight, path = value.split(":", 2)
        lanes.append(InputLane(name, Path(path), float(weight), len(lanes)))
    result = simulate(lanes, args.starting_balance, args.max_open, args.pair_cap, args.extra_round_trip_cost)
    rendered = json.dumps(result, indent=2, default=str, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
