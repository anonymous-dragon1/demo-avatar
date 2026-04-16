from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import DATA_DIR

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
FULL_WEEK_AVAILABILITY = json.dumps(DAYS)


def _common_lines() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"line_id": "LINE_A", "capacity_min": 4800, "display_name": "Line A"},
            {"line_id": "LINE_B", "capacity_min": 4800, "display_name": "Line B"},
        ]
    )


def _common_shifts() -> pd.DataFrame:
    rows = []
    for day_idx, day in enumerate(DAYS):
        base = day_idx * 1440
        rows.extend(
            [
                {
                    "shift_id": f"{day}_S1",
                    "day": day,
                    "shift_name": f"{day} Shift 1",
                    "start_min": base + 360,
                    "end_min": base + 840,
                },
                {
                    "shift_id": f"{day}_S2",
                    "day": day,
                    "shift_name": f"{day} Shift 2",
                    "start_min": base + 840,
                    "end_min": base + 1320,
                },
            ]
        )
    return pd.DataFrame(rows)


def _common_changeovers() -> pd.DataFrame:
    rows = []
    products = ["P1", "P2", "P3"]
    for line in ["LINE_A", "LINE_B"]:
        for p1 in products:
            for p2 in products:
                if p1 == p2:
                    t, c = 0, 0
                elif {p1, p2} == {"P1", "P2"}:
                    t, c = 30, 10
                elif {p1, p2} == {"P2", "P3"}:
                    t, c = 45, 20
                else:
                    t, c = 60, 30
                rows.append(
                    {
                        "line_id": line,
                        "from_product_code": p1,
                        "to_product_code": p2,
                        "changeover_time_min": t,
                        "changeover_cost": c,
                    }
                )
    return pd.DataFrame(rows)


def _common_line_shift_requirements() -> pd.DataFrame:
    rows = []
    for day in DAYS:
        for shift_no in [1, 2]:
            shift_name = f"{day} Shift {shift_no}"
            rows.extend(
                [
                    {
                        "line_id": "LINE_A",
                        "shift_name": shift_name,
                        "competency": "PACKING",
                        "required_qty": 1,
                        "scenario_note": "Base requirement for Line A. If the line is active in this shift, one PACKING worker is required.",
                    },
                    {
                        "line_id": "LINE_B",
                        "shift_name": shift_name,
                        "competency": "MIXING",
                        "required_qty": 1,
                        "scenario_note": "Base requirement for Line B. If the line is active in this shift, one MIXING worker is required.",
                    },
                ]
            )
    return pd.DataFrame(rows)


def _employees_balanced() -> pd.DataFrame:
    rows = [
        {"employee_id": "E01", "employee_name": "Alice", "skills_json": json.dumps({"PACKING": 95}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "A"},
        {"employee_id": "E02", "employee_name": "Budi", "skills_json": json.dumps({"PACKING": 90}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "A"},
        {"employee_id": "E03", "employee_name": "Cici", "skills_json": json.dumps({"PACKING": 84, "MIXING": 78}), "shift_cost": 11, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "B"},
        {"employee_id": "E04", "employee_name": "Deni", "skills_json": json.dumps({"MIXING": 95}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "B"},
        {"employee_id": "E05", "employee_name": "Eka", "skills_json": json.dumps({"MIXING": 90}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "B"},
        {"employee_id": "E06", "employee_name": "Farah", "skills_json": json.dumps({"PACKING": 80, "MIXING": 92}), "shift_cost": 12, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "C"},
        {"employee_id": "E07", "employee_name": "Gita", "skills_json": json.dumps({"PACKING": 87}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "C"},
        {"employee_id": "E08", "employee_name": "Hadi", "skills_json": json.dumps({"MIXING": 85}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "D"},
    ]
    return pd.DataFrame(rows)


def _employees_shortage() -> pd.DataFrame:
    rows = [
        {"employee_id": "E01", "employee_name": "Alice", "skills_json": json.dumps({"PACKING": 95}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "A"},
        {"employee_id": "E02", "employee_name": "Budi", "skills_json": json.dumps({"PACKING": 88}), "shift_cost": 10, "available_days_json": json.dumps(["Mon", "Tue", "Wed"]), "can_work_long_shift": False, "team": "A"},
        {"employee_id": "E03", "employee_name": "Deni", "skills_json": json.dumps({"MIXING": 94}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "B"},
        {"employee_id": "E04", "employee_name": "Eka", "skills_json": json.dumps({"MIXING": 86}), "shift_cost": 10, "available_days_json": json.dumps(["Mon", "Tue", "Wed"]), "can_work_long_shift": False, "team": "B"},
        {"employee_id": "E05", "employee_name": "Fajar", "skills_json": json.dumps({"MIXING": 82}), "shift_cost": 10, "available_days_json": FULL_WEEK_AVAILABILITY, "can_work_long_shift": False, "team": "C"},
    ]
    return pd.DataFrame(rows)


def build_balanced_scenario() -> dict[str, object]:
    orders = pd.DataFrame(
        [
            {"bo_id": "BO01", "product_code": "P1", "duration_min": 780, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 1, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 140, "customer_name": "Cust A"},
            {"bo_id": "BO02", "product_code": "P2", "duration_min": 720, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 2, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0, "LINE_B": 6}), "demand_qty": 125, "customer_name": "Cust B"},
            {"bo_id": "BO03", "product_code": "P3", "duration_min": 660, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 3, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 120, "customer_name": "Cust C"},
            {"bo_id": "BO04", "product_code": "P1", "duration_min": 600, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 4, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 2, "LINE_B": 0}), "demand_qty": 110, "customer_name": "Cust D"},
            {"bo_id": "BO05", "product_code": "P2", "duration_min": 540, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 5, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 95, "customer_name": "Cust E"},
            {"bo_id": "BO06", "product_code": "P3", "duration_min": 480, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 6, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 5, "LINE_B": 0}), "demand_qty": 90, "customer_name": "Cust F"},
            {"bo_id": "BO07", "product_code": "P1", "duration_min": 420, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 7, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 80, "customer_name": "Cust G"},
            {"bo_id": "BO08", "product_code": "P2", "duration_min": 360, "eligible_lines_json": json.dumps(["LINE_B", "LINE_A"]), "priority": 8, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 7, "LINE_B": 0}), "demand_qty": 75, "customer_name": "Cust H"},
        ]
    )
    return {
        "machine_orders.csv": orders,
        "machine_lines.csv": _common_lines(),
        "machine_changeovers.csv": _common_changeovers(),
        "employees.csv": _employees_balanced(),
        "shifts.csv": _common_shifts(),
        "line_shift_requirements.csv": _common_line_shift_requirements(),
        "scenario_meta.json": {
            "scenario_id": "scenario_balanced",
            "title": "Balanced Feasible Scenario",
            "description": "Eight BOs are spread across both production lines and multiple shifts while the employee pool is large enough to cover all active line-shift requirements.",
            "expected_behavior": "Machine scheduling should fit all BOs, generate demand across several shifts, and manpower should cover all active line-shift demand without shortage.",
            "difficulty": "easy",
        },
    }


def build_machine_bottleneck_scenario() -> dict[str, object]:
    orders = pd.DataFrame(
        [
            {"bo_id": "BO01", "product_code": "P1", "duration_min": 1020, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 1, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 165, "customer_name": "Cust A"},
            {"bo_id": "BO02", "product_code": "P2", "duration_min": 960, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 2, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0, "LINE_B": 4}), "demand_qty": 150, "customer_name": "Cust B"},
            {"bo_id": "BO03", "product_code": "P3", "duration_min": 900, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 3, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 145, "customer_name": "Cust C"},
            {"bo_id": "BO04", "product_code": "P1", "duration_min": 840, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 4, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 135, "customer_name": "Cust D"},
            {"bo_id": "BO05", "product_code": "P2", "duration_min": 780, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 5, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 125, "customer_name": "Cust E"},
            {"bo_id": "BO06", "product_code": "P3", "duration_min": 720, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 6, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 7, "LINE_B": 0}), "demand_qty": 120, "customer_name": "Cust F"},
            {"bo_id": "BO07", "product_code": "P1", "duration_min": 660, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 7, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 0, "LINE_B": 8}), "demand_qty": 105, "customer_name": "Cust G"},
            {"bo_id": "BO08", "product_code": "P2", "duration_min": 600, "eligible_lines_json": json.dumps(["LINE_B", "LINE_A"]), "priority": 8, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 9, "LINE_B": 0}), "demand_qty": 95, "customer_name": "Cust H"},
            {"bo_id": "BO09", "product_code": "P3", "duration_min": 660, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 9, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 6, "LINE_B": 0}), "demand_qty": 90, "customer_name": "Cust I"},
            {"bo_id": "BO10", "product_code": "P1", "duration_min": 1200, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 10, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 170, "customer_name": "Cust J"},
            {"bo_id": "BO11", "product_code": "P2", "duration_min": 1200, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 11, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 165, "customer_name": "Cust K"},
            {"bo_id": "BO12", "product_code": "P3", "duration_min": 900, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 12, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 5, "LINE_B": 0}), "demand_qty": 130, "customer_name": "Cust L"},
        ]
    )
    return {
        "machine_orders.csv": orders,
        "machine_lines.csv": _common_lines(),
        "machine_changeovers.csv": _common_changeovers(),
        "employees.csv": _employees_balanced(),
        "shifts.csv": _common_shifts(),
        "line_shift_requirements.csv": _common_line_shift_requirements(),
        "scenario_meta.json": {
            "scenario_id": "scenario_machine_bottleneck",
            "title": "Machine Bottleneck Scenario",
            "description": "The order set materially exceeds total available line capacity, so multiple orders should remain unscheduled even though manpower remains sufficient for the work that does get scheduled.",
            "expected_behavior": "Machine scheduling should leave several orders unscheduled while manpower still covers the scheduled shifts without shortage.",
            "difficulty": "medium",
        },
    }


def build_manpower_shortage_scenario() -> dict[str, object]:
    orders = pd.DataFrame(
        [
            {"bo_id": "BO01", "product_code": "P1", "duration_min": 780, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 1, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 140, "customer_name": "Cust A"},
            {"bo_id": "BO02", "product_code": "P2", "duration_min": 720, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 2, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 0, "LINE_B": 6}), "demand_qty": 125, "customer_name": "Cust B"},
            {"bo_id": "BO03", "product_code": "P3", "duration_min": 660, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 3, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 120, "customer_name": "Cust C"},
            {"bo_id": "BO04", "product_code": "P1", "duration_min": 600, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 4, "setup_time_min": 25, "setup_cost": 6, "line_preference_penalty_json": json.dumps({"LINE_A": 2, "LINE_B": 0}), "demand_qty": 110, "customer_name": "Cust D"},
            {"bo_id": "BO05", "product_code": "P2", "duration_min": 540, "eligible_lines_json": json.dumps(["LINE_B"]), "priority": 5, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_B": 0}), "demand_qty": 95, "customer_name": "Cust E"},
            {"bo_id": "BO06", "product_code": "P3", "duration_min": 480, "eligible_lines_json": json.dumps(["LINE_A", "LINE_B"]), "priority": 6, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 5, "LINE_B": 0}), "demand_qty": 90, "customer_name": "Cust F"},
            {"bo_id": "BO07", "product_code": "P1", "duration_min": 420, "eligible_lines_json": json.dumps(["LINE_A"]), "priority": 7, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 0}), "demand_qty": 80, "customer_name": "Cust G"},
            {"bo_id": "BO08", "product_code": "P2", "duration_min": 360, "eligible_lines_json": json.dumps(["LINE_B", "LINE_A"]), "priority": 8, "setup_time_min": 20, "setup_cost": 5, "line_preference_penalty_json": json.dumps({"LINE_A": 7, "LINE_B": 0}), "demand_qty": 75, "customer_name": "Cust H"},
        ]
    )
    req = _common_line_shift_requirements().copy()
    req.loc[req["line_id"] == "LINE_A", "required_qty"] = 1
    req.loc[req["line_id"] == "LINE_B", "required_qty"] = 2
    req["scenario_note"] = "Demand is intentionally higher than available headcount in selected active line-shift-competency buckets, creating a moderate manpower shortage for demonstration."
    return {
        "machine_orders.csv": orders,
        "machine_lines.csv": _common_lines(),
        "machine_changeovers.csv": _common_changeovers(),
        "employees.csv": _employees_shortage(),
        "shifts.csv": _common_shifts(),
        "line_shift_requirements.csv": req,
        "scenario_meta.json": {
            "scenario_id": "scenario_manpower_shortage",
            "title": "Manpower Shortage Scenario",
            "description": "Machine capacity is sufficient, but the employee pool and availability are intentionally a bit too small to cover all required staffing across the active shifts.",
            "expected_behavior": "Machine scheduling should be feasible while manpower assignment should show a moderate shortage across several active line-shift demand buckets.",
            "difficulty": "medium",
        },
    }


def write_scenario(folder_path: str | Path, data_dict: dict[str, object]) -> None:
    folder = Path(folder_path)
    folder.mkdir(parents=True, exist_ok=True)
    for name, payload in data_dict.items():
        target = folder / name
        if name.endswith('.csv'):
            assert isinstance(payload, pd.DataFrame)
            payload.to_csv(target, index=False)
        elif name.endswith('.json'):
            target.write_text(json.dumps(payload, indent=2))
        else:
            raise ValueError(f'Unsupported scenario artifact: {name}')


def reset_all_scenarios(base_dir: str | Path | None = None) -> None:
    root = Path(base_dir) if base_dir is not None else DATA_DIR
    root.mkdir(parents=True, exist_ok=True)

    scenarios = {
        'scenario_balanced': build_balanced_scenario(),
        'scenario_machine_bottleneck': build_machine_bottleneck_scenario(),
        'scenario_manpower_shortage': build_manpower_shortage_scenario(),
    }
    for name, payload in scenarios.items():
        write_scenario(root / name, payload)
