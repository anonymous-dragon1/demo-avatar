from __future__ import annotations

import json
from typing import Any

import pandas as pd


DEMAND_COLUMNS = [
    "line_id",
    "day",
    "shift_id",
    "shift_name",
    "competency",
    "required_qty",
    "source_bo_ids_json",
    "source_bo_count",
    "scenario_note",
]


DAY_ORDER = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def _empty_demand_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DEMAND_COLUMNS)


def _overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and end_a > start_b


def _build_shift_segment_df(shifts_df: pd.DataFrame) -> pd.DataFrame:
    if shifts_df is None or shifts_df.empty:
        return pd.DataFrame()
    shift_df = shifts_df.copy().sort_values(["start_min", "shift_id"]).reset_index(drop=True)
    shift_df["duration_min"] = shift_df["end_min"].astype(int) - shift_df["start_min"].astype(int)
    shift_df["compressed_start_min"] = shift_df["duration_min"].cumsum().shift(fill_value=0).astype(int)
    shift_df["compressed_end_min"] = shift_df["compressed_start_min"] + shift_df["duration_min"]
    return shift_df[
        [
            "day",
            "shift_id",
            "shift_name",
            "start_min",
            "end_min",
            "duration_min",
            "compressed_start_min",
            "compressed_end_min",
        ]
    ]


def _compressed_minute_to_calendar_minute(
    compressed_minute: int,
    shift_segments_df: pd.DataFrame,
    *,
    is_end: bool = False,
) -> int:
    if shift_segments_df.empty:
        return int(compressed_minute)
    minute_value = int(compressed_minute)
    for _, row in shift_segments_df.iterrows():
        compressed_start = int(row["compressed_start_min"])
        compressed_end = int(row["compressed_end_min"])
        actual_start = int(row["start_min"])
        actual_end = int(row["end_min"])
        if is_end:
            if minute_value == compressed_end:
                return actual_end
            if compressed_start < minute_value < compressed_end:
                return actual_start + (minute_value - compressed_start)
        else:
            if compressed_start <= minute_value < compressed_end:
                return actual_start + (minute_value - compressed_start)
    last_row = shift_segments_df.iloc[-1]
    overflow = minute_value - int(last_row["compressed_end_min"])
    return int(last_row["end_min"]) + max(0, overflow)


def build_line_shift_demand(
    schedule_df: pd.DataFrame,
    shifts_df: pd.DataFrame,
    line_shift_requirements_df: pd.DataFrame,
) -> pd.DataFrame:
    if schedule_df is None or schedule_df.empty:
        return _empty_demand_df()

    shift_segments_df = _build_shift_segment_df(shifts_df)
    active_sources: dict[tuple[str, str, str], set[str]] = {}
    for sched in schedule_df.to_dict("records"):
        line_id = str(sched["line_id"])
        bo_id = str(sched["bo_id"])
        start_min = _compressed_minute_to_calendar_minute(
            int(sched["start_min"]),
            shift_segments_df,
            is_end=False,
        )
        end_min = _compressed_minute_to_calendar_minute(
            int(sched["end_min"]),
            shift_segments_df,
            is_end=True,
        )
        for shift in shifts_df.to_dict("records"):
            shift_start = int(shift["start_min"])
            shift_end = int(shift["end_min"])
            if _overlaps(start_min, end_min, shift_start, shift_end):
                key = (line_id, str(shift["shift_id"]), str(shift["shift_name"]))
                active_sources.setdefault(key, set()).add(bo_id)

    if not active_sources:
        return _empty_demand_df()

    shift_meta = {
        (str(rec["shift_id"]), str(rec["shift_name"])): {"day": str(rec["day"])}
        for rec in shifts_df.to_dict("records")
    }

    rows: list[dict[str, Any]] = []
    for req in line_shift_requirements_df.to_dict("records"):
        line_id = str(req["line_id"])
        shift_name = str(req["shift_name"])
        matching_shift_ids = [
            shift_id
            for (shift_id, req_shift_name), _meta in shift_meta.items()
            if req_shift_name == shift_name
        ]
        for shift_id in matching_shift_ids:
            key = (line_id, shift_id, shift_name)
            source_bo_ids = sorted(active_sources.get(key, set()))
            if not source_bo_ids:
                continue
            rows.append(
                {
                    "line_id": line_id,
                    "day": shift_meta[(shift_id, shift_name)]["day"],
                    "shift_id": shift_id,
                    "shift_name": shift_name,
                    "competency": str(req["competency"]),
                    "required_qty": int(req["required_qty"]),
                    "source_bo_ids_json": json.dumps(source_bo_ids),
                    "source_bo_count": len(source_bo_ids),
                    "scenario_note": str(req["scenario_note"]) if "scenario_note" in req else "",
                }
            )

    if not rows:
        return _empty_demand_df()

    out = pd.DataFrame(rows, columns=DEMAND_COLUMNS)
    out = (
        out.groupby(["line_id", "day", "shift_id", "shift_name", "competency"], as_index=False)
        .agg(
            required_qty=("required_qty", "sum"),
            source_bo_ids_json=(
                "source_bo_ids_json",
                lambda vals: json.dumps(sorted({bo for raw in vals for bo in json.loads(raw)})),
            ),
            scenario_note=("scenario_note", lambda vals: " | ".join(sorted({v for v in vals if v}))),
        )
    )
    out["source_bo_count"] = out["source_bo_ids_json"].apply(lambda raw: len(json.loads(raw)))
    out["_day_order"] = out["day"].map(lambda day: DAY_ORDER.get(day, 999))
    out = out.sort_values(["_day_order", "shift_id", "line_id", "competency"]).reset_index(drop=True)
    return out[DEMAND_COLUMNS]
