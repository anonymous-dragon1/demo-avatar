from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from src.config import W_CHANGEOVER, W_DROP, W_LINE_PREF


@dataclass(frozen=True)
class MachineWeights:
    drop: int = W_DROP
    changeover: int = W_CHANGEOVER
    line_preference: int = W_LINE_PREF


STATUS_LABELS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _to_int(value: Any, default: int = 0) -> int:
    if pd.isna(value):
        return default
    return int(value)


def _to_text(value: Any, default: str = "") -> str:
    if pd.isna(value):
        return default
    return str(value)


def _format_minute_label(minute: int) -> str:
    day_index = max(minute, 0) // 1440
    day = DAY_NAMES[min(day_index, len(DAY_NAMES) - 1)]
    minute_of_day = max(minute, 0) % 1440
    hour = minute_of_day // 60
    minute_part = minute_of_day % 60
    return f"{day} {hour:02d}:{minute_part:02d}"


def _build_changeover_lookup(
    changeovers_df: pd.DataFrame,
) -> tuple[dict[tuple[str, str, str], int], dict[tuple[str, str, str], int]]:
    time_lookup: dict[tuple[str, str, str], int] = {}
    cost_lookup: dict[tuple[str, str, str], int] = {}
    for rec in changeovers_df.to_dict("records"):
        key = (
            _to_text(rec.get("line_id")),
            _to_text(rec.get("from_product_code")),
            _to_text(rec.get("to_product_code")),
        )
        time_lookup[key] = _to_int(rec.get("changeover_time_min"))
        cost_lookup[key] = _to_int(rec.get("changeover_cost"))
    return time_lookup, cost_lookup


def _get_changeover_value(
    lookup: dict[tuple[str, str, str], int],
    line_id: str,
    from_product: str,
    to_product: str,
) -> int:
    if from_product == to_product:
        return 0
    return lookup.get((line_id, from_product, to_product), 0)


def _normalize_orders(
    orders_df: pd.DataFrame,
    lines_df: pd.DataFrame,
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, int], dict[str, str]]:
    line_ids = [str(v) for v in lines_df["line_id"].tolist()]
    capacities = {
        str(rec["line_id"]): _to_int(rec["capacity_min"])
        for rec in lines_df.to_dict("records")
    }
    display_names = {
        str(rec["line_id"]): _to_text(rec.get("display_name"), default=str(rec["line_id"]))
        for rec in lines_df.to_dict("records")
    }
    orders: dict[str, dict[str, Any]] = {}
    for rec in orders_df.to_dict("records"):
        bo_id = _to_text(rec.get("bo_id"))
        eligible_lines = [str(v) for v in rec.get("eligible_lines_json", []) if str(v) in capacities]
        pref_penalty_raw = rec.get("line_preference_penalty_json", {}) or {}
        pref_penalty = {str(k): _to_int(v) for k, v in pref_penalty_raw.items()}
        orders[bo_id] = {
            "bo_id": bo_id,
            "product_code": _to_text(rec.get("product_code")),
            "duration_min": _to_int(rec.get("duration_min")),
            "setup_time_min": _to_int(rec.get("setup_time_min")),
            "setup_cost": _to_int(rec.get("setup_cost")),
            "eligible_lines": eligible_lines,
            "line_preference_penalty": pref_penalty,
            "demand_qty": _to_int(rec.get("demand_qty")),
            "customer_name": _to_text(rec.get("customer_name")),
        }
    return line_ids, orders, capacities, display_names


def solve_machine_demo(
    orders_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    changeovers_df: pd.DataFrame,
    weights: MachineWeights | None = None,
    time_limit_sec: int | float = 10,
    random_seed: int = 0,
) -> dict[str, Any]:
    weights = weights or MachineWeights()
    model = cp_model.CpModel()

    line_ids, orders, capacities, display_names = _normalize_orders(orders_df, lines_df)
    order_ids = list(orders.keys())
    changeover_time_lookup, changeover_cost_lookup = _build_changeover_lookup(changeovers_df)
    max_changeover_time = max(changeover_time_lookup.values(), default=0)

    x: dict[tuple[str, str], cp_model.IntVar] = {}
    start: dict[tuple[str, str], cp_model.IntVar] = {}
    end: dict[tuple[str, str], cp_model.IntVar] = {}
    first: dict[tuple[str, str], cp_model.IntVar] = {}
    last: dict[tuple[str, str], cp_model.IntVar] = {}
    drop: dict[str, cp_model.IntVar] = {}
    succ: dict[tuple[str, str, str], cp_model.IntVar] = {}
    intervals_by_line: dict[str, list[cp_model.IntervalVar]] = {line_id: [] for line_id in line_ids}
    line_orders_map: dict[str, list[str]] = {line_id: [] for line_id in line_ids}
    feasible_pairs: list[tuple[str, str]] = []

    for bo_id, order in orders.items():
        drop[bo_id] = model.NewBoolVar(f"drop[{bo_id}]")
        for line_id in order["eligible_lines"]:
            capacity = capacities[line_id]
            if order["duration_min"] + order["setup_time_min"] > capacity:
                continue
            pair = (bo_id, line_id)
            feasible_pairs.append(pair)
            line_orders_map[line_id].append(bo_id)
            x[pair] = model.NewBoolVar(f"x[{bo_id},{line_id}]")
            start[pair] = model.NewIntVar(0, capacity, f"start[{bo_id},{line_id}]")
            end[pair] = model.NewIntVar(0, capacity, f"end[{bo_id},{line_id}]")
            first[pair] = model.NewBoolVar(f"first[{bo_id},{line_id}]")
            last[pair] = model.NewBoolVar(f"last[{bo_id},{line_id}]")
            model.Add(end[pair] == start[pair] + order["duration_min"]).OnlyEnforceIf(x[pair])
            model.Add(start[pair] == 0).OnlyEnforceIf(x[pair].Not())
            model.Add(end[pair] == 0).OnlyEnforceIf(x[pair].Not())
            model.Add(start[pair] >= order["setup_time_min"] * first[pair])
            intervals_by_line[line_id].append(
                model.NewOptionalIntervalVar(
                    start[pair],
                    order["duration_min"],
                    end[pair],
                    x[pair],
                    f"interval[{bo_id},{line_id}]",
                )
            )

    for bo_id in order_ids:
        assign_terms = [x[(bo_id, line_id)] for line_id in line_ids if (bo_id, line_id) in x]
        model.Add(sum(assign_terms) + drop[bo_id] == 1)

    line_used: dict[str, cp_model.IntVar] = {}
    for line_id in line_ids:
        line_orders = line_orders_map[line_id]
        line_used[line_id] = model.NewBoolVar(f"line_used[{line_id}]")
        if intervals_by_line[line_id]:
            model.AddNoOverlap(intervals_by_line[line_id])
        if not line_orders:
            model.Add(line_used[line_id] == 0)
            continue

        assigned_count = sum(x[(bo_id, line_id)] for bo_id in line_orders)
        model.Add(assigned_count >= line_used[line_id])
        model.Add(assigned_count <= len(line_orders) * line_used[line_id])
        model.Add(sum(first[(bo_id, line_id)] for bo_id in line_orders) == line_used[line_id])
        model.Add(sum(last[(bo_id, line_id)] for bo_id in line_orders) == line_used[line_id])

        for i in line_orders:
            for j in line_orders:
                if i == j:
                    continue
                succ[(i, j, line_id)] = model.NewBoolVar(f"succ[{i},{j},{line_id}]")

        for bo_id in line_orders:
            pred_vars = [succ[(other_id, bo_id, line_id)] for other_id in line_orders if other_id != bo_id]
            succ_vars = [succ[(bo_id, other_id, line_id)] for other_id in line_orders if other_id != bo_id]
            model.Add(sum(pred_vars) + first[(bo_id, line_id)] == x[(bo_id, line_id)])
            model.Add(sum(succ_vars) + last[(bo_id, line_id)] == x[(bo_id, line_id)])

        model.Add(
            sum(succ[(i, j, line_id)] for i in line_orders for j in line_orders if i != j)
            == assigned_count - line_used[line_id]
        )

        big_m = capacities[line_id] + max(
            (orders[bo_id]["duration_min"] for bo_id in line_orders),
            default=0,
        ) + max_changeover_time
        for i in line_orders:
            for j in line_orders:
                if i == j:
                    continue
                arc = succ[(i, j, line_id)]
                model.Add(arc <= x[(i, line_id)])
                model.Add(arc <= x[(j, line_id)])
                changeover_time = _get_changeover_value(
                    changeover_time_lookup,
                    line_id,
                    orders[i]["product_code"],
                    orders[j]["product_code"],
                )
                model.Add(
                    start[(j, line_id)]
                    >= end[(i, line_id)] + changeover_time - big_m * (1 - arc)
                )

    drop_penalty_terms: list[cp_model.LinearExpr] = []
    setup_cost_terms: list[cp_model.LinearExpr] = []
    changeover_cost_terms: list[cp_model.LinearExpr] = []
    line_pref_terms: list[cp_model.LinearExpr] = []

    for bo_id in order_ids:
        drop_penalty_terms.append(drop[bo_id])

    for bo_id, line_id in feasible_pairs:
        order = orders[bo_id]
        setup_cost_terms.append(first[(bo_id, line_id)] * order["setup_cost"])
        line_pref_terms.append(
            x[(bo_id, line_id)] * order["line_preference_penalty"].get(line_id, 0)
        )

    for (i, j, line_id), arc in succ.items():
        co_cost = _get_changeover_value(
            changeover_cost_lookup,
            line_id,
            orders[i]["product_code"],
            orders[j]["product_code"],
        )
        changeover_cost_terms.append(arc * co_cost)

    model.Minimize(
        weights.drop * sum(drop_penalty_terms)
        + weights.changeover * (sum(setup_cost_terms) + sum(changeover_cost_terms))
        + weights.line_preference * sum(line_pref_terms)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_sec)
    solver.parameters.random_seed = random_seed
    solver.parameters.num_search_workers = 1
    status_code = solver.Solve(model)
    status = STATUS_LABELS.get(status_code, str(status_code))

    empty_schedule_cols = [
        "bo_id",
        "line_id",
        "display_name",
        "sequence",
        "product_code",
        "start_min",
        "end_min",
        "start_label",
        "end_label",
        "duration_min",
        "setup_time_min",
        "setup_cost",
        "changeover_from_prev_min",
        "changeover_from_prev_cost",
        "line_preference_penalty",
        "demand_qty",
        "customer_name",
        "is_first_on_line",
    ]
    empty_drop_cols = [
        "bo_id",
        "product_code",
        "duration_min",
        "demand_qty",
        "customer_name",
        "drop_penalty_units",
        "reason",
    ]
    empty_line_summary_cols = [
        "line_id",
        "display_name",
        "assigned_order_count",
        "processing_min",
        "setup_min",
        "changeover_min",
        "used_min",
        "capacity_min",
        "remaining_min",
        "utilization_pct",
        "setup_cost",
        "changeover_cost",
        "line_preference_penalty",
        "total_machine_cost",
    ]

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "schedule_df": pd.DataFrame(columns=empty_schedule_cols),
            "dropped_df": pd.DataFrame(columns=empty_drop_cols),
            "line_summary_df": pd.DataFrame(columns=empty_line_summary_cols),
            "solver_summary": {
                "status": status,
                "status_code": status_code,
                "message": "Machine demo model did not find a feasible solution.",
                "objective_value": None,
                "runtime_sec": solver.WallTime(),
                "num_orders": len(order_ids),
                "scheduled_orders": 0,
                "dropped_orders": len(order_ids),
                "drop_penalty_units": 0,
                "total_processing_min": 0,
                "total_setup_min": 0,
                "total_changeover_min": 0,
                "total_setup_cost": 0,
                "total_changeover_cost": 0,
                "total_line_preference_penalty": 0,
                "total_machine_cost": 0,
                "weights": asdict(weights),
                "time_limit_sec": float(time_limit_sec),
                "random_seed": random_seed,
                "assigned_line_by_order": {},
            },
        }

    assigned_line_by_order: dict[str, str] = {}
    first_by_line: dict[str, str] = {}
    succ_by_line: dict[str, dict[str, str]] = {line_id: {} for line_id in line_ids}

    for bo_id, line_id in feasible_pairs:
        if solver.Value(x[(bo_id, line_id)]):
            assigned_line_by_order[bo_id] = line_id
        if solver.Value(first[(bo_id, line_id)]):
            first_by_line[line_id] = bo_id

    for (i, j, line_id), arc in succ.items():
        if solver.Value(arc):
            succ_by_line[line_id][i] = j

    schedule_rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []
    line_summary_rows: list[dict[str, Any]] = []
    total_setup_cost = 0
    total_changeover_cost = 0
    total_line_pref_penalty = 0
    total_setup_min = 0
    total_changeover_min = 0
    total_processing_min = 0
    total_drop_penalty_units = 0

    for bo_id in order_ids:
        if solver.Value(drop[bo_id]):
            order = orders[bo_id]
            total_drop_penalty_units += 1
            dropped_rows.append(
                {
                    "bo_id": bo_id,
                    "product_code": order["product_code"],
                    "duration_min": order["duration_min"],
                    "demand_qty": order["demand_qty"],
                    "customer_name": order["customer_name"],
                    "drop_penalty_units": 1,
                    "reason": "Left unscheduled due to available time or sequencing tradeoff.",
                }
            )

    for line_id in line_ids:
        line_sequence: list[str] = []
        if line_id in first_by_line:
            seen: set[str] = set()
            current = first_by_line[line_id]
            while current and current not in seen:
                seen.add(current)
                line_sequence.append(current)
                current = succ_by_line[line_id].get(current, "")

        processing_min = 0
        setup_min = 0
        changeover_min = 0
        setup_cost = 0
        changeover_cost = 0
        line_pref_penalty = 0
        previous_bo = None

        for sequence, bo_id in enumerate(line_sequence, start=1):
            order = orders[bo_id]
            pair = (bo_id, line_id)
            start_min = solver.Value(start[pair])
            end_min = solver.Value(end[pair])
            is_first = bool(solver.Value(first[pair]))
            prev_changeover_min = 0
            prev_changeover_cost = 0
            if previous_bo is not None:
                prev_changeover_min = _get_changeover_value(
                    changeover_time_lookup,
                    line_id,
                    orders[previous_bo]["product_code"],
                    order["product_code"],
                )
                prev_changeover_cost = _get_changeover_value(
                    changeover_cost_lookup,
                    line_id,
                    orders[previous_bo]["product_code"],
                    order["product_code"],
                )
            if is_first:
                setup_min += order["setup_time_min"]
                setup_cost += order["setup_cost"]
            processing_min += order["duration_min"]
            changeover_min += prev_changeover_min
            changeover_cost += prev_changeover_cost
            line_pref = order["line_preference_penalty"].get(line_id, 0)
            line_pref_penalty += line_pref

            schedule_rows.append(
                {
                    "bo_id": bo_id,
                    "line_id": line_id,
                    "display_name": display_names.get(line_id, line_id),
                    "sequence": sequence,
                    "product_code": order["product_code"],
                    "start_min": start_min,
                    "end_min": end_min,
                    "start_label": _format_minute_label(start_min),
                    "end_label": _format_minute_label(end_min),
                    "duration_min": order["duration_min"],
                    "setup_time_min": order["setup_time_min"] if is_first else 0,
                    "setup_cost": order["setup_cost"] if is_first else 0,
                    "changeover_from_prev_min": prev_changeover_min,
                    "changeover_from_prev_cost": prev_changeover_cost,
                    "line_preference_penalty": line_pref,
                    "demand_qty": order["demand_qty"],
                    "customer_name": order["customer_name"],
                    "is_first_on_line": is_first,
                }
            )
            previous_bo = bo_id

        used_min = processing_min + setup_min + changeover_min
        capacity_min = capacities[line_id]
        remaining_min = capacity_min - used_min
        line_total_cost = setup_cost + changeover_cost + line_pref_penalty
        line_summary_rows.append(
            {
                "line_id": line_id,
                "display_name": display_names.get(line_id, line_id),
                "assigned_order_count": len(line_sequence),
                "processing_min": processing_min,
                "setup_min": setup_min,
                "changeover_min": changeover_min,
                "used_min": used_min,
                "capacity_min": capacity_min,
                "remaining_min": remaining_min,
                "utilization_pct": round((used_min / capacity_min) * 100, 2) if capacity_min else 0.0,
                "setup_cost": setup_cost,
                "changeover_cost": changeover_cost,
                "line_preference_penalty": line_pref_penalty,
                "total_machine_cost": line_total_cost,
            }
        )
        total_processing_min += processing_min
        total_setup_min += setup_min
        total_changeover_min += changeover_min
        total_setup_cost += setup_cost
        total_changeover_cost += changeover_cost
        total_line_pref_penalty += line_pref_penalty

    schedule_df = pd.DataFrame(schedule_rows, columns=empty_schedule_cols)
    if not schedule_df.empty:
        schedule_df = schedule_df.sort_values(["line_id", "sequence", "bo_id"]).reset_index(drop=True)

    dropped_df = pd.DataFrame(dropped_rows, columns=empty_drop_cols)
    if not dropped_df.empty:
        dropped_df = dropped_df.sort_values(["bo_id"]).reset_index(drop=True)

    line_summary_df = pd.DataFrame(line_summary_rows, columns=empty_line_summary_cols)
    if not line_summary_df.empty:
        line_summary_df = line_summary_df.sort_values(["line_id"]).reset_index(drop=True)

    solver_summary = {
        "status": status,
        "status_code": status_code,
        "message": "Machine demo model solved successfully.",
        "objective_value": solver.ObjectiveValue(),
        "runtime_sec": solver.WallTime(),
        "num_orders": len(order_ids),
        "scheduled_orders": len(schedule_df),
        "dropped_orders": len(dropped_df),
        "drop_penalty_units": total_drop_penalty_units,
        "total_processing_min": total_processing_min,
        "total_setup_min": total_setup_min,
        "total_changeover_min": total_changeover_min,
        "total_setup_cost": total_setup_cost,
        "total_changeover_cost": total_changeover_cost,
        "total_line_preference_penalty": total_line_pref_penalty,
        "total_machine_cost": total_setup_cost + total_changeover_cost + total_line_pref_penalty,
        "weights": asdict(weights),
        "time_limit_sec": float(time_limit_sec),
        "random_seed": random_seed,
        "assigned_line_by_order": assigned_line_by_order,
    }

    return {
        "schedule_df": schedule_df,
        "dropped_df": dropped_df,
        "line_summary_df": line_summary_df,
        "solver_summary": solver_summary,
    }
