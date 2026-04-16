from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_SCENARIO_FILES = {
    "machine_orders.csv",
    "machine_lines.csv",
    "machine_changeovers.csv",
    "employees.csv",
    "shifts.csv",
    "line_shift_requirements.csv",
    "scenario_meta.json",
}

REQUIRED_META_KEYS = {
    "scenario_id",
    "title",
    "description",
    "expected_behavior",
    "difficulty",
}

DAY_LABELS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


def _require_columns(df: pd.DataFrame, required: list[str], table_name: str) -> list[str]:
    missing = [col for col in required if col not in df.columns]
    return [f"{table_name}: missing required columns: {', '.join(missing)}"] if missing else []


def _parse_json_value(raw: Any, table_name: str, column: str, row_idx: int, errors: list[str]) -> Any:
    if pd.isna(raw):
        errors.append(f"{table_name}: row {row_idx + 1} column '{column}' is empty.")
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        errors.append(f"{table_name}: row {row_idx + 1} column '{column}' contains invalid JSON.")
        return None


def validate_machine_orders(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = [
        "bo_id",
        "product_code",
        "duration_min",
        "eligible_lines_json",
        "setup_time_min",
        "setup_cost",
        "line_preference_penalty_json",
    ]
    errors.extend(_require_columns(df, required, "machine_orders.csv"))
    if errors:
        return errors

    if df["bo_id"].astype(str).duplicated().any():
        errors.append("machine_orders.csv: 'bo_id' must be unique.")

    numeric_nonneg = ["setup_time_min", "setup_cost"]
    for col in numeric_nonneg:
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.isna().any() or (vals < 0).any():
            errors.append(f"machine_orders.csv: column '{col}' must contain non-negative numbers.")

    duration = pd.to_numeric(df["duration_min"], errors="coerce")
    if duration.isna().any() or (duration <= 0).any():
        errors.append("machine_orders.csv: column 'duration_min' must contain positive numbers.")

    for row_idx, raw in enumerate(df["eligible_lines_json"]):
        parsed = _parse_json_value(raw, "machine_orders.csv", "eligible_lines_json", row_idx, errors)
        if parsed is None:
            continue
        if not isinstance(parsed, list) or not parsed or not all(isinstance(v, str) and v.strip() for v in parsed):
            errors.append("machine_orders.csv: 'eligible_lines_json' must be a non-empty JSON array of line ids.")

    for row_idx, raw in enumerate(df["line_preference_penalty_json"]):
        parsed = _parse_json_value(raw, "machine_orders.csv", "line_preference_penalty_json", row_idx, errors)
        if parsed is None:
            continue
        if not isinstance(parsed, dict):
            errors.append("machine_orders.csv: 'line_preference_penalty_json' must be a JSON object keyed by line id.")
            continue
        for _, val in parsed.items():
            try:
                if float(val) < 0:
                    raise ValueError
            except Exception:
                errors.append("machine_orders.csv: 'line_preference_penalty_json' values must be non-negative numbers.")
                break

    return errors


def validate_machine_lines(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = ["line_id", "capacity_min", "display_name"]
    errors.extend(_require_columns(df, required, "machine_lines.csv"))
    if errors:
        return errors

    if df["line_id"].astype(str).duplicated().any():
        errors.append("machine_lines.csv: 'line_id' must be unique.")

    cap = pd.to_numeric(df["capacity_min"], errors="coerce")
    if cap.isna().any() or (cap <= 0).any():
        errors.append("machine_lines.csv: 'capacity_min' must contain positive numbers.")

    return errors


def validate_machine_changeovers(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = ["line_id", "from_product_code", "to_product_code", "changeover_time_min", "changeover_cost"]
    errors.extend(_require_columns(df, required, "machine_changeovers.csv"))
    if errors:
        return errors

    if df.duplicated(subset=["line_id", "from_product_code", "to_product_code"]).any():
        errors.append("machine_changeovers.csv: each (line_id, from_product_code, to_product_code) row must be unique.")

    for col in ["changeover_time_min", "changeover_cost"]:
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.isna().any() or (vals < 0).any():
            errors.append(f"machine_changeovers.csv: '{col}' must contain non-negative numbers.")

    return errors


def validate_employees(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = ["employee_id", "employee_name", "skills_json", "shift_cost", "available_days_json"]
    errors.extend(_require_columns(df, required, "employees.csv"))
    if errors:
        return errors

    if df["employee_id"].astype(str).duplicated().any():
        errors.append("employees.csv: 'employee_id' must be unique.")

    shift_cost = pd.to_numeric(df["shift_cost"], errors="coerce")
    if shift_cost.isna().any() or (shift_cost < 0).any():
        errors.append("employees.csv: 'shift_cost' must contain non-negative numbers.")

    for row_idx, raw in enumerate(df["skills_json"]):
        parsed = _parse_json_value(raw, "employees.csv", "skills_json", row_idx, errors)
        if parsed is None:
            continue
        if not isinstance(parsed, dict) or not parsed:
            errors.append("employees.csv: 'skills_json' must be a non-empty JSON object.")
            continue
        for key, val in parsed.items():
            if not isinstance(key, str) or not key.strip():
                errors.append("employees.csv: 'skills_json' keys must be non-empty competency names.")
                break
            try:
                score = float(val)
                if not (0 <= score <= 100):
                    raise ValueError
            except Exception:
                errors.append("employees.csv: 'skills_json' values must be numbers between 0 and 100.")
                break

    for row_idx, raw in enumerate(df["available_days_json"]):
        parsed = _parse_json_value(raw, "employees.csv", "available_days_json", row_idx, errors)
        if parsed is None:
            continue
        if not isinstance(parsed, list) or not parsed:
            errors.append("employees.csv: 'available_days_json' must be a non-empty JSON array.")
            continue
        if any(day not in DAY_LABELS for day in parsed):
            errors.append("employees.csv: 'available_days_json' contains invalid day labels.")

    return errors


def validate_shifts(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = ["shift_id", "day", "shift_name", "start_min", "end_min"]
    errors.extend(_require_columns(df, required, "shifts.csv"))
    if errors:
        return errors

    if df["shift_id"].astype(str).duplicated().any():
        errors.append("shifts.csv: 'shift_id' must be unique.")

    if not set(df["day"].astype(str)).issubset(DAY_LABELS):
        errors.append("shifts.csv: 'day' must use labels in Mon..Sun.")

    start = pd.to_numeric(df["start_min"], errors="coerce")
    end = pd.to_numeric(df["end_min"], errors="coerce")
    if start.isna().any() or (start < 0).any():
        errors.append("shifts.csv: 'start_min' must contain non-negative numbers.")
    if end.isna().any() or (end <= 0).any():
        errors.append("shifts.csv: 'end_min' must contain positive numbers.")
    if not start.isna().all() and not end.isna().all() and (end <= start).any():
        errors.append("shifts.csv: each row must satisfy end_min > start_min.")

    return errors


def validate_line_shift_requirements(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    required = ["line_id", "shift_name", "competency", "required_qty"]
    errors.extend(_require_columns(df, required, "line_shift_requirements.csv"))
    if errors:
        return errors

    qty = pd.to_numeric(df["required_qty"], errors="coerce")
    if qty.isna().any() or (qty < 0).any():
        errors.append("line_shift_requirements.csv: 'required_qty' must contain non-negative numbers.")

    return errors


def _load_csv(path: Path, table_name: str, errors: list[str]) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path)
    except Exception as exc:
        errors.append(f"{table_name}: failed to read CSV: {exc}")
        return None


def validate_scenario_folder(path: str | Path) -> list[str]:
    scenario_dir = Path(path)
    errors: list[str] = []

    if not scenario_dir.exists() or not scenario_dir.is_dir():
        return [f"Scenario path does not exist or is not a directory: {scenario_dir}"]

    existing = {p.name for p in scenario_dir.iterdir() if p.is_file()}
    missing = sorted(REQUIRED_SCENARIO_FILES - existing)
    if missing:
        errors.append(f"Scenario '{scenario_dir.name}' is missing required files: {', '.join(missing)}")
        return errors

    try:
        meta = json.loads((scenario_dir / "scenario_meta.json").read_text())
    except Exception as exc:
        errors.append(f"scenario_meta.json: failed to parse JSON: {exc}")
        return errors

    missing_keys = sorted(REQUIRED_META_KEYS - set(meta.keys()))
    if missing_keys:
        errors.append(f"scenario_meta.json: missing required keys: {', '.join(missing_keys)}")

    machine_orders = _load_csv(scenario_dir / "machine_orders.csv", "machine_orders.csv", errors)
    machine_lines = _load_csv(scenario_dir / "machine_lines.csv", "machine_lines.csv", errors)
    machine_changeovers = _load_csv(scenario_dir / "machine_changeovers.csv", "machine_changeovers.csv", errors)
    employees = _load_csv(scenario_dir / "employees.csv", "employees.csv", errors)
    shifts = _load_csv(scenario_dir / "shifts.csv", "shifts.csv", errors)
    requirements = _load_csv(scenario_dir / "line_shift_requirements.csv", "line_shift_requirements.csv", errors)

    if errors:
        return errors

    errors.extend(validate_machine_orders(machine_orders))
    errors.extend(validate_machine_lines(machine_lines))
    errors.extend(validate_machine_changeovers(machine_changeovers))
    errors.extend(validate_employees(employees))
    errors.extend(validate_shifts(shifts))
    errors.extend(validate_line_shift_requirements(requirements))

    if errors:
        return errors

    line_ids = set(machine_lines["line_id"].astype(str))
    shift_names = set(shifts["shift_name"].astype(str))
    competencies: set[str] = set()

    for raw in employees["skills_json"]:
        parsed = json.loads(str(raw)) if not isinstance(raw, dict) else raw
        competencies.update(str(key) for key in parsed.keys())

    for row_idx, raw in enumerate(machine_orders["eligible_lines_json"]):
        parsed = json.loads(str(raw)) if not isinstance(raw, list) else raw
        unknown = sorted({str(x) for x in parsed} - line_ids)
        if unknown:
            errors.append(
                f"machine_orders.csv: row {row_idx + 1} references unknown eligible lines: {', '.join(unknown)}"
            )

    for row_idx, raw in enumerate(machine_orders["line_preference_penalty_json"]):
        parsed = json.loads(str(raw)) if not isinstance(raw, dict) else raw
        unknown = sorted({str(x) for x in parsed.keys()} - line_ids)
        if unknown:
            errors.append(
                f"machine_orders.csv: row {row_idx + 1} references unknown line preference keys: {', '.join(unknown)}"
            )

    if not set(machine_changeovers["line_id"].astype(str)).issubset(line_ids):
        errors.append("machine_changeovers.csv: contains line_id values not present in machine_lines.csv.")

    if not set(requirements["line_id"].astype(str)).issubset(line_ids):
        errors.append("line_shift_requirements.csv: contains line_id values not present in machine_lines.csv.")

    if not set(requirements["shift_name"].astype(str)).issubset(shift_names):
        errors.append("line_shift_requirements.csv: contains shift_name values not present in shifts.csv.")

    if not set(requirements["competency"].astype(str)).issubset(competencies):
        errors.append("line_shift_requirements.csv: contains competency values not present in any employee skills_json.")

    return errors
