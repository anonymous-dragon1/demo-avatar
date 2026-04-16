from __future__ import annotations

from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = DEMO_ROOT / "data"
OUTPUT_DIR = DEMO_ROOT / "outputs"

DEMO_HORIZON = "Monday-Friday"
MACHINE_TIME_UNIT = "minutes_from_week_start"
MANPOWER_TIME_UNIT = "shift_buckets"

W_DROP = 1_000_000
W_CHANGEOVER = 1_000
W_LINE_PREF = 1

W_SHORTAGE = 1_000_000
W_SKILL = 1_000
W_SHIFT_COST = 1
