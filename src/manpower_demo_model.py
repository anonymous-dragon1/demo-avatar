from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from src.config import W_SHIFT_COST, W_SHORTAGE, W_SKILL


@dataclass(frozen=True)
class ManpowerWeights:
    shortage: int = W_SHORTAGE
    skill: int = W_SKILL
    shift_cost: int = W_SHIFT_COST


STATUS_LABELS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


ASSIGNMENT_COLUMNS = [
    "employee_id",
    "employee_name",
    "line_id",
    "day",
    "shift_id",
    "shift_name",
    "competency",
    "skill_score",
    "skill_penalty",
    "shift_cost",
    "source_bo_ids_json",
    "scenario_note",
]

SHORTAGE_COLUMNS = [
    "line_id",
    "day",
    "shift_id",
    "shift_name",
    "competency",
    "required_qty",
    "assigned_qty",
    "shortage_qty",
    "source_bo_ids_json",
    "scenario_note",
]

COVERAGE_COLUMNS = [
    "line_id",
    "day",
    "shift_id",
    "shift_name",
    "competency",
    "required_qty",
    "assigned_qty",
    "shortage_qty",
    "coverage_pct",
    "source_bo_ids_json",
    "scenario_note",
]

EMPLOYEE_SHIFT_COLUMNS = [
    "employee_id",
    "employee_name",
    "day",
    "shift_id",
    "shift_name",
    "line_id",
    "competency",
    "shift_cost",
]


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    return int(value)


def _employee_maps(employees_df: pd.DataFrame) -> tuple[dict[str, dict[str, int]], dict[str, set[str]], dict[str, dict[str, Any]]]:
    skill_map: dict[str, dict[str, int]] = {}
    availability_map: dict[str, set[str]] = {}
    employee_meta: dict[str, dict[str, Any]] = {}
    for rec in employees_df.to_dict("records"):
        employee_id = str(rec["employee_id"])
        skills = {str(k): _to_int(v) for k, v in (rec.get("skills_json") or {}).items()}
        availability = {str(day) for day in (rec.get("available_days_json") or [])}
        skill_map[employee_id] = skills
        availability_map[employee_id] = availability
        employee_meta[employee_id] = {
            "employee_name": str(rec["employee_name"]),
            "shift_cost": _to_int(rec["shift_cost"]),
            "team": str(rec.get("team", "")),
        }
    return skill_map, availability_map, employee_meta


def solve_manpower_demo(
    employees_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    weights: ManpowerWeights | None = None,
    time_limit_sec: int | float = 10,
    random_seed: int = 0,
) -> dict[str, Any]:
    weights = weights or ManpowerWeights()

    if demand_df is None or demand_df.empty:
        return {
            "assignments_df": _empty_df(ASSIGNMENT_COLUMNS),
            "shortage_df": _empty_df(SHORTAGE_COLUMNS),
            "coverage_summary_df": _empty_df(COVERAGE_COLUMNS),
            "employee_shift_summary_df": _empty_df(EMPLOYEE_SHIFT_COLUMNS),
            "solver_summary": {
                "status": "NOT_RUN",
                "status_code": None,
                "message": "No manpower demand rows were generated.",
                "objective_value": 0,
                "runtime_sec": 0.0,
                "total_shortage_qty": 0,
                "total_skill_penalty": 0,
                "total_shift_cost": 0,
                "total_manpower_cost": 0,
                "weights": asdict(weights),
                "time_limit_sec": float(time_limit_sec),
                "random_seed": random_seed,
            },
        }

    model = cp_model.CpModel()
    skill_map, availability_map, employee_meta = _employee_maps(employees_df)
    shift_day_map = {str(rec["shift_id"]): str(rec["day"]) for rec in shifts_df.to_dict("records")}

    demand_records = []
    for idx, rec in enumerate(demand_df.to_dict("records")):
        demand_records.append(
            {
                "demand_id": idx,
                "line_id": str(rec["line_id"]),
                "day": str(rec["day"]),
                "shift_id": str(rec["shift_id"]),
                "shift_name": str(rec["shift_name"]),
                "competency": str(rec["competency"]),
                "required_qty": _to_int(rec["required_qty"]),
                "source_bo_ids_json": str(rec.get("source_bo_ids_json", "[]")),
                "scenario_note": str(rec.get("scenario_note", "")),
            }
        )

    feasible_employees_by_demand: dict[int, list[str]] = {}
    x: dict[tuple[str, int], cp_model.IntVar] = {}
    miss: dict[int, cp_model.IntVar] = {}
    y: dict[tuple[str, str], cp_model.IntVar] = {}

    shift_ids = sorted({str(rec["shift_id"]) for rec in demand_records})
    employee_ids = list(skill_map.keys())
    for employee_id in employee_ids:
        for shift_id in shift_ids:
            y[(employee_id, shift_id)] = model.NewBoolVar(f"y[{employee_id},{shift_id}]")

    for demand in demand_records:
        demand_id = demand["demand_id"]
        competency = demand["competency"]
        day = demand["day"]
        required_qty = demand["required_qty"]
        feasible = [
            employee_id
            for employee_id in employee_ids
            if competency in skill_map.get(employee_id, {}) and day in availability_map.get(employee_id, set())
        ]
        feasible_employees_by_demand[demand_id] = feasible
        miss[demand_id] = model.NewIntVar(0, required_qty, f"miss[{demand_id}]")
        assign_terms = []
        for employee_id in feasible:
            var = model.NewBoolVar(f"x[{employee_id},{demand_id}]")
            x[(employee_id, demand_id)] = var
            assign_terms.append(var)
            model.Add(var <= y[(employee_id, demand["shift_id"])])
        if assign_terms:
            model.Add(sum(assign_terms) + miss[demand_id] >= required_qty)
            model.Add(sum(assign_terms) <= required_qty)
        else:
            model.Add(miss[demand_id] == required_qty)

    # one employee can cover at most one seat in the same shift
    for employee_id in employee_ids:
        for shift_id in shift_ids:
            shift_demand_terms = [
                x[(employee_id, demand["demand_id"])]
                for demand in demand_records
                if demand["shift_id"] == shift_id and (employee_id, demand["demand_id"]) in x
            ]
            if shift_demand_terms:
                model.Add(sum(shift_demand_terms) <= 1)
                model.Add(sum(shift_demand_terms) <= y[(employee_id, shift_id)])
            else:
                model.Add(y[(employee_id, shift_id)] == 0)

    # at most one shift per employee per day
    unique_days = sorted({str(rec["day"]) for rec in demand_records})
    for employee_id in employee_ids:
        for day in unique_days:
            day_shifts = [shift_id for shift_id in shift_ids if shift_day_map.get(shift_id) == day]
            if day_shifts:
                model.Add(sum(y[(employee_id, shift_id)] for shift_id in day_shifts) <= 1)

    shortage_term = sum(miss[demand_id] for demand_id in miss)
    skill_term = sum(
        x[(employee_id, demand_id)] * (100 - skill_map[employee_id][next(d["competency"] for d in demand_records if d["demand_id"] == demand_id)])
        for (employee_id, demand_id) in x
    )
    shift_cost_term = sum(y[(employee_id, shift_id)] * employee_meta[employee_id]["shift_cost"] for (employee_id, shift_id) in y)
    model.Minimize(
        weights.shortage * shortage_term
        + weights.skill * skill_term
        + weights.shift_cost * shift_cost_term
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_sec)
    solver.parameters.random_seed = random_seed
    solver.parameters.num_search_workers = 1
    status_code = solver.Solve(model)
    status = STATUS_LABELS.get(status_code, str(status_code))

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "assignments_df": _empty_df(ASSIGNMENT_COLUMNS),
            "shortage_df": _empty_df(SHORTAGE_COLUMNS),
            "coverage_summary_df": _empty_df(COVERAGE_COLUMNS),
            "employee_shift_summary_df": _empty_df(EMPLOYEE_SHIFT_COLUMNS),
            "solver_summary": {
                "status": status,
                "status_code": status_code,
                "message": "Manpower demo model did not find a feasible solution.",
                "objective_value": None,
                "runtime_sec": solver.WallTime(),
                "total_shortage_qty": None,
                "total_skill_penalty": None,
                "total_shift_cost": None,
                "total_manpower_cost": None,
                "weights": asdict(weights),
                "time_limit_sec": float(time_limit_sec),
                "random_seed": random_seed,
            },
        }

    demand_by_id = {rec["demand_id"]: rec for rec in demand_records}
    assignments_rows: list[dict[str, Any]] = []
    shortage_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    employee_shift_rows: list[dict[str, Any]] = []
    total_skill_penalty = 0
    total_shift_cost = 0

    for demand in demand_records:
        demand_id = demand["demand_id"]
        assigned_employees = [
            employee_id
            for employee_id in feasible_employees_by_demand[demand_id]
            if solver.Value(x[(employee_id, demand_id)])
        ]
        assigned_qty = len(assigned_employees)
        shortage_qty = solver.Value(miss[demand_id])
        coverage_pct = round((assigned_qty / demand["required_qty"]) * 100, 2) if demand["required_qty"] else 100.0

        coverage_rows.append(
            {
                "line_id": demand["line_id"],
                "day": demand["day"],
                "shift_id": demand["shift_id"],
                "shift_name": demand["shift_name"],
                "competency": demand["competency"],
                "required_qty": demand["required_qty"],
                "assigned_qty": assigned_qty,
                "shortage_qty": shortage_qty,
                "coverage_pct": coverage_pct,
                "source_bo_ids_json": demand["source_bo_ids_json"],
                "scenario_note": demand["scenario_note"],
            }
        )

        if shortage_qty > 0:
            shortage_rows.append(
                {
                    "line_id": demand["line_id"],
                    "day": demand["day"],
                    "shift_id": demand["shift_id"],
                    "shift_name": demand["shift_name"],
                    "competency": demand["competency"],
                    "required_qty": demand["required_qty"],
                    "assigned_qty": assigned_qty,
                    "shortage_qty": shortage_qty,
                    "source_bo_ids_json": demand["source_bo_ids_json"],
                    "scenario_note": demand["scenario_note"],
                }
            )

        for employee_id in assigned_employees:
            score = skill_map[employee_id][demand["competency"]]
            penalty = 100 - score
            total_skill_penalty += penalty
            assignments_rows.append(
                {
                    "employee_id": employee_id,
                    "employee_name": employee_meta[employee_id]["employee_name"],
                    "line_id": demand["line_id"],
                    "day": demand["day"],
                    "shift_id": demand["shift_id"],
                    "shift_name": demand["shift_name"],
                    "competency": demand["competency"],
                    "skill_score": score,
                    "skill_penalty": penalty,
                    "shift_cost": employee_meta[employee_id]["shift_cost"],
                    "source_bo_ids_json": demand["source_bo_ids_json"],
                    "scenario_note": demand["scenario_note"],
                }
            )
            employee_shift_rows.append(
                {
                    "employee_id": employee_id,
                    "employee_name": employee_meta[employee_id]["employee_name"],
                    "day": demand["day"],
                    "shift_id": demand["shift_id"],
                    "shift_name": demand["shift_name"],
                    "line_id": demand["line_id"],
                    "competency": demand["competency"],
                    "shift_cost": employee_meta[employee_id]["shift_cost"],
                }
            )

    used_shift_pairs = [(employee_id, shift_id) for (employee_id, shift_id), var in y.items() if solver.Value(var)]
    total_shift_cost = sum(employee_meta[employee_id]["shift_cost"] for employee_id, _shift_id in used_shift_pairs)
    total_shortage_qty = sum(solver.Value(miss[demand_id]) for demand_id in miss)

    assignments_df = pd.DataFrame(assignments_rows, columns=ASSIGNMENT_COLUMNS)
    if not assignments_df.empty:
        assignments_df = assignments_df.sort_values(["day", "shift_id", "line_id", "competency", "employee_id"]).reset_index(drop=True)

    shortage_df = pd.DataFrame(shortage_rows, columns=SHORTAGE_COLUMNS)
    if not shortage_df.empty:
        shortage_df = shortage_df.sort_values(["day", "shift_id", "line_id", "competency"]).reset_index(drop=True)

    coverage_summary_df = pd.DataFrame(coverage_rows, columns=COVERAGE_COLUMNS)
    if not coverage_summary_df.empty:
        coverage_summary_df = coverage_summary_df.sort_values(["day", "shift_id", "line_id", "competency"]).reset_index(drop=True)

    employee_shift_summary_df = pd.DataFrame(employee_shift_rows, columns=EMPLOYEE_SHIFT_COLUMNS)
    if not employee_shift_summary_df.empty:
        employee_shift_summary_df = employee_shift_summary_df.sort_values(["employee_id", "day", "shift_id"]).reset_index(drop=True)

    solver_summary = {
        "status": status,
        "status_code": status_code,
        "message": "Manpower demo model solved successfully.",
        "objective_value": solver.ObjectiveValue(),
        "runtime_sec": solver.WallTime(),
        "total_shortage_qty": total_shortage_qty,
        "total_skill_penalty": total_skill_penalty,
        "total_shift_cost": total_shift_cost,
        "total_manpower_cost": total_shift_cost,
        "assignments_count": len(assignments_df),
        "shortage_rows": len(shortage_df),
        "activated_employee_shifts": len(used_shift_pairs),
        "weights": asdict(weights),
        "time_limit_sec": float(time_limit_sec),
        "random_seed": random_seed,
    }

    return {
        "assignments_df": assignments_df,
        "shortage_df": shortage_df,
        "coverage_summary_df": coverage_summary_df,
        "employee_shift_summary_df": employee_shift_summary_df,
        "solver_summary": solver_summary,
    }
