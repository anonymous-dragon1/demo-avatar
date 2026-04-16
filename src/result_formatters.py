from __future__ import annotations

from typing import Any

import pandas as pd


MACHINE_KPI_COLUMNS = [
    "kpi_key",
    "label",
    "value",
    "display_value",
    "unit",
    "section",
    "sort_order",
]

MACHINE_COST_BREAKDOWN_COLUMNS = [
    "component",
    "cost",
    "share_pct",
    "sort_order",
]

MACHINE_GANTT_COLUMNS = [
    "line_id",
    "display_name",
    "bo_id",
    "product_code",
    "sequence",
    "start_min",
    "end_min",
    "start_label",
    "end_label",
    "duration_min",
    "setup_time_min",
    "changeover_from_prev_min",
    "line_preference_penalty",
    "customer_name",
    "task_label",
]

CAPACITY_CHART_COLUMNS = [
    "line_id",
    "display_name",
    "used_min",
    "capacity_min",
    "remaining_min",
    "utilization_pct",
    "slack_pct",
    "assigned_order_count",
    "setup_min",
    "changeover_min",
    "processing_min",
    "total_machine_cost",
]

DROPPED_ORDER_COLUMNS = [
    "bo_id",
    "product_code",
    "duration_min",
    "demand_qty",
    "customer_name",
    "drop_penalty_units",
    "reason",
]

MANPOWER_KPI_COLUMNS = [
    "kpi_key",
    "label",
    "value",
    "display_value",
    "unit",
    "section",
    "sort_order",
]

MANPOWER_COST_BREAKDOWN_COLUMNS = [
    "component",
    "cost",
    "share_pct",
    "cost_scope",
    "sort_order",
]

SHORTAGE_HEATMAP_COLUMNS = [
    "day",
    "shift_id",
    "shift_name",
    "line_id",
    "competency",
    "required_qty",
    "assigned_qty",
    "shortage_qty",
    "coverage_pct",
    "heatmap_value",
    "source_bo_ids_json",
    "scenario_note",
]

EMPLOYEE_SCHEDULE_COLUMNS = [
    "employee_id",
    "employee_name",
    "day",
    "shift_id",
    "shift_name",
    "line_id",
    "competency",
    "skill_score",
    "skill_penalty",
    "shift_cost",
    "source_bo_ids_json",
    "scenario_note",
]

COVERAGE_TABLE_COLUMNS = [
    "day",
    "shift_id",
    "shift_name",
    "line_id",
    "competency",
    "required_qty",
    "assigned_qty",
    "shortage_qty",
    "coverage_pct",
    "source_bo_ids_json",
    "scenario_note",
]


def _empty_df(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    return float(value)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    return int(value)


def build_machine_kpis(
    schedule_df: pd.DataFrame,
    dropped_df: pd.DataFrame,
    line_summary_df: pd.DataFrame,
    solver_summary: dict[str, Any],
) -> pd.DataFrame:
    total_capacity = _to_int(line_summary_df.get("capacity_min", pd.Series(dtype="int64")).sum())
    total_used = _to_int(line_summary_df.get("used_min", pd.Series(dtype="int64")).sum())
    utilization_pct = round((total_used / total_capacity) * 100, 2) if total_capacity else 0.0

    rows = [
        {
            "kpi_key": "total_machine_cost",
            "label": "Total Machine Cost",
            "value": _to_int(solver_summary.get("total_machine_cost")),
            "display_value": str(_to_int(solver_summary.get("total_machine_cost"))),
            "unit": "cost_units",
            "section": "business",
            "sort_order": 1,
        },
        {
            "kpi_key": "scheduled_orders",
            "label": "Scheduled Orders",
            "value": _to_int(solver_summary.get("scheduled_orders", len(schedule_df))),
            "display_value": str(_to_int(solver_summary.get("scheduled_orders", len(schedule_df)))),
            "unit": "order",
            "section": "business",
            "sort_order": 2,
        },
        {
            "kpi_key": "dropped_orders",
            "label": "Unscheduled Orders",
            "value": _to_int(solver_summary.get("dropped_orders", len(dropped_df))),
            "display_value": str(_to_int(solver_summary.get("dropped_orders", len(dropped_df)))),
            "unit": "order",
            "section": "business",
            "sort_order": 3,
        },
        {
            "kpi_key": "used_capacity_min",
            "label": "Used Capacity",
            "value": total_used,
            "display_value": str(total_used),
            "unit": "min",
            "section": "business",
            "sort_order": 4,
        },
        {
            "kpi_key": "utilization_pct",
            "label": "Utilization",
            "value": utilization_pct,
            "display_value": f"{utilization_pct:.2f}%",
            "unit": "pct",
            "section": "business",
            "sort_order": 5,
        },
        {
            "kpi_key": "solver_status",
            "label": "Solver Status",
            "value": solver_summary.get("status", "UNKNOWN"),
            "display_value": str(solver_summary.get("status", "UNKNOWN")),
            "unit": "text",
            "section": "diagnostic",
            "sort_order": 90,
        },
        {
            "kpi_key": "objective_value",
            "label": "Objective Value",
            "value": _to_float(solver_summary.get("objective_value")),
            "display_value": f"{_to_float(solver_summary.get('objective_value')):.0f}",
            "unit": "objective",
            "section": "diagnostic",
            "sort_order": 91,
        },
        {
            "kpi_key": "runtime_sec",
            "label": "Runtime",
            "value": round(_to_float(solver_summary.get("runtime_sec")), 4),
            "display_value": f"{_to_float(solver_summary.get('runtime_sec')):.4f}",
            "unit": "sec",
            "section": "diagnostic",
            "sort_order": 92,
        },
    ]
    return pd.DataFrame(rows, columns=MACHINE_KPI_COLUMNS).sort_values("sort_order").reset_index(drop=True)


def build_machine_cost_breakdown_df(
    schedule_df: pd.DataFrame,
    dropped_df: pd.DataFrame,
    line_summary_df: pd.DataFrame,
    solver_summary: dict[str, Any],
) -> pd.DataFrame:
    setup_cost = _to_int(solver_summary.get("total_setup_cost"))
    changeover_cost = _to_int(solver_summary.get("total_changeover_cost"))
    line_pref_cost = _to_int(solver_summary.get("total_line_preference_penalty"))
    total_cost = setup_cost + changeover_cost + line_pref_cost
    rows = [
        {"component": "Setup Cost", "cost": setup_cost, "sort_order": 1},
        {"component": "Changeover Cost", "cost": changeover_cost, "sort_order": 2},
        {"component": "Line Preference Penalty", "cost": line_pref_cost, "sort_order": 3},
        {"component": "Total Machine Cost", "cost": total_cost, "sort_order": 99},
    ]
    for row in rows:
        row["share_pct"] = round((row["cost"] / total_cost) * 100, 2) if total_cost else 0.0
    return pd.DataFrame(rows, columns=MACHINE_COST_BREAKDOWN_COLUMNS).sort_values("sort_order").reset_index(drop=True)


def build_machine_gantt_df(schedule_df: pd.DataFrame) -> pd.DataFrame:
    if schedule_df is None or schedule_df.empty:
        return _empty_df(MACHINE_GANTT_COLUMNS)
    out = schedule_df.copy()
    out["task_label"] = out.apply(
        lambda row: f"{row['bo_id']} | {row['product_code']} | Seq {row['sequence']}",
        axis=1,
    )
    return out[MACHINE_GANTT_COLUMNS].sort_values(["line_id", "sequence", "start_min", "bo_id"]).reset_index(drop=True)


def build_capacity_chart_df(line_summary_df: pd.DataFrame) -> pd.DataFrame:
    if line_summary_df is None or line_summary_df.empty:
        return _empty_df(CAPACITY_CHART_COLUMNS)
    out = line_summary_df.copy()
    out["slack_pct"] = out.apply(
        lambda row: round((row["remaining_min"] / row["capacity_min"]) * 100, 2) if row["capacity_min"] else 0.0,
        axis=1,
    )
    return out[CAPACITY_CHART_COLUMNS].sort_values(["line_id"]).reset_index(drop=True)


def build_dropped_orders_df(dropped_df: pd.DataFrame) -> pd.DataFrame:
    if dropped_df is None or dropped_df.empty:
        return _empty_df(DROPPED_ORDER_COLUMNS)
    out = dropped_df.copy()
    return out[DROPPED_ORDER_COLUMNS].sort_values(["bo_id"]).reset_index(drop=True)


def build_manpower_kpis(
    assignments_df: pd.DataFrame,
    shortage_df: pd.DataFrame,
    coverage_summary_df: pd.DataFrame,
    solver_summary: dict[str, Any],
) -> pd.DataFrame:
    total_required = _to_int(coverage_summary_df.get("required_qty", pd.Series(dtype="int64")).sum())
    total_assigned = _to_int(coverage_summary_df.get("assigned_qty", pd.Series(dtype="int64")).sum())
    total_shortage = _to_int(solver_summary.get("total_shortage_qty", shortage_df.get("shortage_qty", pd.Series(dtype="int64")).sum()))
    coverage_pct = round((total_assigned / total_required) * 100, 2) if total_required else 100.0

    rows = [
        {
            "kpi_key": "total_manpower_cost",
            "label": "Total Manpower Cost",
            "value": _to_int(solver_summary.get("total_manpower_cost")),
            "display_value": str(_to_int(solver_summary.get("total_manpower_cost"))),
            "unit": "cost_units",
            "section": "business",
            "sort_order": 1,
        },
        {
            "kpi_key": "activated_employee_shifts",
            "label": "Active Employee Shifts",
            "value": _to_int(solver_summary.get("activated_employee_shifts")),
            "display_value": str(_to_int(solver_summary.get("activated_employee_shifts"))),
            "unit": "shift",
            "section": "business",
            "sort_order": 2,
        },
        {
            "kpi_key": "assignments_count",
            "label": "Assignments",
            "value": _to_int(solver_summary.get("assignments_count", len(assignments_df))),
            "display_value": str(_to_int(solver_summary.get("assignments_count", len(assignments_df)))),
            "unit": "assignment",
            "section": "business",
            "sort_order": 3,
        },
        {
            "kpi_key": "total_shortage_qty",
            "label": "Total Shortage",
            "value": total_shortage,
            "display_value": str(total_shortage),
            "unit": "headcount",
            "section": "business",
            "sort_order": 4,
        },
        {
            "kpi_key": "coverage_pct",
            "label": "Coverage",
            "value": coverage_pct,
            "display_value": f"{coverage_pct:.2f}%",
            "unit": "pct",
            "section": "business",
            "sort_order": 5,
        },
        {
            "kpi_key": "solver_status",
            "label": "Solver Status",
            "value": solver_summary.get("status", "UNKNOWN"),
            "display_value": str(solver_summary.get("status", "UNKNOWN")),
            "unit": "text",
            "section": "diagnostic",
            "sort_order": 90,
        },
        {
            "kpi_key": "objective_value",
            "label": "Objective Value",
            "value": _to_float(solver_summary.get("objective_value")),
            "display_value": f"{_to_float(solver_summary.get('objective_value')):.0f}",
            "unit": "objective",
            "section": "diagnostic",
            "sort_order": 91,
        },
        {
            "kpi_key": "runtime_sec",
            "label": "Runtime",
            "value": round(_to_float(solver_summary.get("runtime_sec")), 4),
            "display_value": f"{_to_float(solver_summary.get('runtime_sec')):.4f}",
            "unit": "sec",
            "section": "diagnostic",
            "sort_order": 92,
        },
        {
            "kpi_key": "total_skill_penalty",
            "label": "Skill Penalty",
            "value": _to_int(solver_summary.get("total_skill_penalty")),
            "display_value": str(_to_int(solver_summary.get("total_skill_penalty"))),
            "unit": "penalty_units",
            "section": "diagnostic",
            "sort_order": 93,
        },
    ]
    return pd.DataFrame(rows, columns=MANPOWER_KPI_COLUMNS).sort_values("sort_order").reset_index(drop=True)


def build_manpower_cost_breakdown_df(
    assignments_df: pd.DataFrame,
    shortage_df: pd.DataFrame,
    coverage_summary_df: pd.DataFrame,
    solver_summary: dict[str, Any],
) -> pd.DataFrame:
    shift_cost = _to_int(solver_summary.get("total_shift_cost"))
    business_total = _to_int(solver_summary.get("total_manpower_cost", shift_cost))
    shortage_penalty = _to_int(solver_summary.get("total_shortage_qty"))
    skill_penalty = _to_int(solver_summary.get("total_skill_penalty"))
    technical_total = shift_cost + shortage_penalty + skill_penalty
    rows = [
        {
            "component": "Shift Cost",
            "cost": shift_cost,
            "cost_scope": "business",
            "sort_order": 1,
        },
        {
            "component": "Total Manpower Cost",
            "cost": business_total,
            "cost_scope": "business",
            "sort_order": 99,
        },
        {
            "component": "Shortage Qty",
            "cost": shortage_penalty,
            "cost_scope": "diagnostic",
            "sort_order": 201,
        },
        {
            "component": "Skill Penalty",
            "cost": skill_penalty,
            "cost_scope": "diagnostic",
            "sort_order": 202,
        },
        {
            "component": "Diagnostic Total",
            "cost": technical_total,
            "cost_scope": "diagnostic",
            "sort_order": 299,
        },
    ]
    business_denominator = business_total if business_total else shift_cost
    diagnostic_denominator = technical_total
    for row in rows:
        denominator = business_denominator if row["cost_scope"] == "business" else diagnostic_denominator
        row["share_pct"] = round((row["cost"] / denominator) * 100, 2) if denominator else 0.0
    return pd.DataFrame(rows, columns=MANPOWER_COST_BREAKDOWN_COLUMNS).sort_values(
        ["cost_scope", "sort_order"]
    ).reset_index(drop=True)


def build_shortage_heatmap_df(shortage_df: pd.DataFrame) -> pd.DataFrame:
    if shortage_df is None or shortage_df.empty:
        return _empty_df(SHORTAGE_HEATMAP_COLUMNS)
    out = shortage_df.copy()
    out["coverage_pct"] = out.apply(
        lambda row: round((row["assigned_qty"] / row["required_qty"]) * 100, 2) if row["required_qty"] else 100.0,
        axis=1,
    )
    out["heatmap_value"] = out["shortage_qty"]
    return out[SHORTAGE_HEATMAP_COLUMNS].sort_values(
        ["day", "shift_id", "line_id", "competency"]
    ).reset_index(drop=True)


def build_employee_schedule_df(assignments_df: pd.DataFrame) -> pd.DataFrame:
    if assignments_df is None or assignments_df.empty:
        return _empty_df(EMPLOYEE_SCHEDULE_COLUMNS)
    out = assignments_df.copy()
    return out[EMPLOYEE_SCHEDULE_COLUMNS].sort_values(
        ["employee_id", "day", "shift_id", "line_id", "competency"]
    ).reset_index(drop=True)


def build_coverage_table_df(coverage_summary_df: pd.DataFrame) -> pd.DataFrame:
    if coverage_summary_df is None or coverage_summary_df.empty:
        return _empty_df(COVERAGE_TABLE_COLUMNS)
    out = coverage_summary_df.copy()
    return out[COVERAGE_TABLE_COLUMNS].sort_values(
        ["day", "shift_id", "line_id", "competency"]
    ).reset_index(drop=True)
