from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import DATA_DIR

JSON_COLUMNS_BY_FILE: dict[str, list[str]] = {
    "machine_orders.csv": ["eligible_lines_json", "line_preference_penalty_json"],
    "employees.csv": ["skills_json", "available_days_json"],
}

INT_COLUMNS_BY_FILE: dict[str, list[str]] = {
    "machine_orders.csv": ["duration_min", "priority", "setup_time_min", "setup_cost", "demand_qty"],
    "machine_lines.csv": ["capacity_min"],
    "machine_changeovers.csv": ["changeover_time_min", "changeover_cost"],
    "employees.csv": ["shift_cost"],
    "shifts.csv": ["start_min", "end_min"],
    "line_shift_requirements.csv": ["required_qty"],
}

BOOL_COLUMNS_BY_FILE: dict[str, list[str]] = {
    "employees.csv": ["can_work_long_shift"],
}

CSV_FILE_ORDER = [
    "machine_orders.csv",
    "machine_lines.csv",
    "machine_changeovers.csv",
    "employees.csv",
    "shifts.csv",
    "line_shift_requirements.csv",
]


def _load_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _parse_json_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    out = df.copy()
    for col in JSON_COLUMNS_BY_FILE.get(filename, []):
        if col in out.columns:
            out[col] = out[col].apply(lambda v: json.loads(v) if isinstance(v, str) else v)
    return out


def _normalize_int_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    out = df.copy()
    for col in INT_COLUMNS_BY_FILE.get(filename, []):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out


def _normalize_bool_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    out = df.copy()
    for col in BOOL_COLUMNS_BY_FILE.get(filename, []):
        if col in out.columns:
            out[col] = out[col].astype("boolean")
    return out


def _normalize_text_columns(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    out = df.copy()
    skip = set(JSON_COLUMNS_BY_FILE.get(filename, [])) | set(INT_COLUMNS_BY_FILE.get(filename, [])) | set(BOOL_COLUMNS_BY_FILE.get(filename, []))
    for col in out.columns:
        if col in skip:
            continue
        if pd.api.types.is_object_dtype(out[col]) or pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].astype("string")
    return out


def normalize_table(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    out = df.copy()
    out = _parse_json_columns(out, filename)
    out = _normalize_int_columns(out, filename)
    out = _normalize_bool_columns(out, filename)
    out = _normalize_text_columns(out, filename)
    return out


def list_scenarios(base_dir: Path | None = None) -> list[dict[str, Any]]:
    root = base_dir or DATA_DIR
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.iterdir()):
        if path.is_dir():
            meta_path = path / "scenario_meta.json"
            meta = _load_json_file(meta_path) if meta_path.exists() else {}
            out.append(
                {
                    "name": path.name,
                    "path": path,
                    "title": meta.get("title", path.name),
                    "description": meta.get("description", ""),
                    "difficulty": meta.get("difficulty", ""),
                    "meta": meta,
                }
            )
    return out


def load_scenario(scenario_dir: str | Path) -> dict[str, Any]:
    path = Path(scenario_dir)
    tables: dict[str, pd.DataFrame] = {}
    raw_tables: dict[str, pd.DataFrame] = {}
    for filename in CSV_FILE_ORDER:
        table = pd.read_csv(path / filename)
        raw_tables[filename] = table.copy()
        tables[filename] = normalize_table(table, filename)

    meta = _load_json_file(path / "scenario_meta.json")
    return {
        "name": path.name,
        "path": path,
        "meta": meta,
        "tables": tables,
        "raw_tables": raw_tables,
        "machine_orders": tables["machine_orders.csv"],
        "machine_lines": tables["machine_lines.csv"],
        "machine_changeovers": tables["machine_changeovers.csv"],
        "employees": tables["employees.csv"],
        "shifts": tables["shifts.csv"],
        "line_shift_requirements": tables["line_shift_requirements.csv"],
    }


def save_edited_table(df: pd.DataFrame, path: str | Path) -> None:
    target = Path(path)
    filename = target.name
    out = df.copy()
    for col in JSON_COLUMNS_BY_FILE.get(filename, []):
        if col in out.columns:
            out[col] = out[col].apply(lambda v: json.dumps(v) if isinstance(v, (list, dict)) else v)
    for col in BOOL_COLUMNS_BY_FILE.get(filename, []):
        if col in out.columns:
            out[col] = out[col].astype(object)
    out.to_csv(target, index=False)
