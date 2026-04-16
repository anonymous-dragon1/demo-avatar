from __future__ import annotations

import json
import base64
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import altair as alt
import pandas as pd
import streamlit as st

from src.bridge import build_line_shift_demand
from src.dummy_data import reset_all_scenarios
from src.io import list_scenarios, load_scenario, normalize_table
from src.machine_demo_model import solve_machine_demo
from src.manpower_demo_model import solve_manpower_demo
from src.result_formatters import (
    build_capacity_chart_df,
    build_coverage_table_df,
    build_dropped_orders_df,
    build_employee_schedule_df,
    build_machine_cost_breakdown_df,
    build_machine_gantt_df,
    build_machine_kpis,
    build_manpower_cost_breakdown_df,
    build_manpower_kpis,
    build_shortage_heatmap_df,
)
from src.validators import (
    validate_employees,
    validate_line_shift_requirements,
    validate_machine_changeovers,
    validate_machine_lines,
    validate_machine_orders,
    validate_scenario_folder,
    validate_shifts,
)


APP_DIR = Path(__file__).resolve().parent
IMAGE_ASSET_DIR = APP_DIR / "image_asset"
COMPANY_LOGO_PATH = IMAGE_ASSET_DIR / "WhatsApp Image 2026-04-15 at 11.20.45 AM (1).jpeg"
PROJECT_LOGO_PATH = IMAGE_ASSET_DIR / "KN+BSB_Logo-FullColor.png"

st.set_page_config(
    page_title="Advanced Scheduling System Demo",
    page_icon=str(PROJECT_LOGO_PATH) if PROJECT_LOGO_PATH.exists() else None,
    layout="wide",
)


TABLE_CONFIGS = [
    {"filename": "machine_orders.csv", "scenario_key": "machine_orders", "label": "Production Orders"},
    {"filename": "machine_lines.csv", "scenario_key": "machine_lines", "label": "Production Lines"},
    {"filename": "machine_changeovers.csv", "scenario_key": "machine_changeovers", "label": "Product Switches"},
    {"filename": "employees.csv", "scenario_key": "employees", "label": "Employees"},
    {"filename": "shifts.csv", "scenario_key": "shifts", "label": "Shifts"},
    {"filename": "line_shift_requirements.csv", "scenario_key": "line_shift_requirements", "label": "Staffing Requirements"},
]

TABLE_VALIDATORS = {
    "machine_orders.csv": validate_machine_orders,
    "machine_lines.csv": validate_machine_lines,
    "machine_changeovers.csv": validate_machine_changeovers,
    "employees.csv": validate_employees,
    "shifts.csv": validate_shifts,
    "line_shift_requirements.csv": validate_line_shift_requirements,
}

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

FRIENDLY_COLUMNS = {
    "bo_id": "Order ID",
    "source_bo_list": "Source Orders",
    "source_bo_count": "Source Order Count",
    "source_bo_ids_json": "Source Order IDs",
    "product_code": "Product",
    "duration_min": "Duration (min)",
    "setup_time_min": "Setup Time (min)",
    "setup_cost": "Setup Cost",
    "line_id": "Line ID",
    "display_name": "Line",
    "capacity_min": "Available Time (min)",
    "employee_id": "Employee ID",
    "employee_name": "Employee",
    "shift_id": "Shift ID",
    "shift_name": "Shift",
    "required_qty": "Required Workers",
    "assigned_qty": "Assigned Workers",
    "shortage_qty": "Unfilled Need",
    "coverage_pct": "Fill Rate %",
    "competency": "Skill",
    "day": "Day",
    "changeover_time_min": "Switch Time (min)",
    "changeover_cost": "Switch Cost",
    "changeover_from_prev_min": "Previous Switch Time (min)",
    "used_min": "Used Time (min)",
    "remaining_min": "Remaining Time (min)",
    "assigned_order_count": "Assigned Orders",
}


@st.cache_data(show_spinner=False)
def _list_scenarios() -> list[dict[str, Any]]:
    return list_scenarios()


@st.cache_data(show_spinner=False)
def _load_scenario(path_str: str) -> dict[str, Any]:
    return load_scenario(Path(path_str))


@st.cache_data(show_spinner=False)
def _validate_scenario(path_str: str) -> list[str]:
    return validate_scenario_folder(Path(path_str))


def _format_clock_minutes(minutes: Any) -> str:
    try:
        total_minutes = int(round(float(minutes))) % 1440
    except Exception:
        return ""
    hours = total_minutes // 60
    mins = total_minutes % 60
    return f"{hours:02d}:{mins:02d}"


@st.cache_data(show_spinner=False)
def _run_machine(path_str: str) -> dict[str, Any]:
    scenario = _load_scenario(path_str)
    result = solve_machine_demo(
        scenario["machine_orders"],
        scenario["machine_lines"],
        scenario["machine_changeovers"],
    )
    result["kpis_df"] = build_machine_kpis(
        result["schedule_df"],
        result["dropped_df"],
        result["line_summary_df"],
        result["solver_summary"],
    )
    result["cost_breakdown_df"] = build_machine_cost_breakdown_df(
        result["schedule_df"],
        result["dropped_df"],
        result["line_summary_df"],
        result["solver_summary"],
    )
    result["gantt_df"] = build_machine_gantt_df(result["schedule_df"])
    result["capacity_chart_df"] = build_capacity_chart_df(result["line_summary_df"])
    result["dropped_orders_df"] = build_dropped_orders_df(result["dropped_df"])
    return result


@st.cache_data(show_spinner=False)
def _build_demand(path_str: str) -> pd.DataFrame:
    scenario = _load_scenario(path_str)
    machine_result = _run_machine(path_str)
    return build_line_shift_demand(
        machine_result["schedule_df"],
        scenario["shifts"],
        scenario["line_shift_requirements"],
    )


@st.cache_data(show_spinner=False)
def _run_manpower(path_str: str) -> dict[str, Any]:
    scenario = _load_scenario(path_str)
    demand_df = _build_demand(path_str)
    manpower_result = solve_manpower_demo(
        scenario["employees"],
        scenario["shifts"],
        demand_df,
    )
    manpower_result["demand_df"] = demand_df
    manpower_result["kpis_df"] = build_manpower_kpis(
        manpower_result["assignments_df"],
        manpower_result["shortage_df"],
        manpower_result["coverage_summary_df"],
        manpower_result["solver_summary"],
    )
    manpower_result["cost_breakdown_df"] = build_manpower_cost_breakdown_df(
        manpower_result["assignments_df"],
        manpower_result["shortage_df"],
        manpower_result["coverage_summary_df"],
        manpower_result["solver_summary"],
    )
    manpower_result["shortage_heatmap_df"] = build_shortage_heatmap_df(manpower_result["shortage_df"])
    manpower_result["employee_schedule_df"] = build_employee_schedule_df(manpower_result["assignments_df"])
    manpower_result["coverage_table_df"] = build_coverage_table_df(manpower_result["coverage_summary_df"])
    return manpower_result


def _render_kpi_cards(kpis_df: pd.DataFrame, section: str, columns: int = 4) -> None:
    section_df = kpis_df[kpis_df["section"] == section].sort_values("sort_order")
    if section_df.empty:
        st.caption("No metrics available yet.")
        return
    cols = st.columns(columns)
    for idx, (_, row) in enumerate(section_df.iterrows()):
        cols[idx % columns].metric(str(row["label"]), str(row["display_value"]))


def _get_kpi_display_value(kpis_df: pd.DataFrame, kpi_key: str, fallback: str) -> str:
    match = kpis_df[kpis_df["kpi_key"] == kpi_key]
    if match.empty:
        return fallback
    return str(match.iloc[0]["display_value"])


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _friendly_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "priority" in out.columns:
        out = out.drop(columns=["priority"])
    out.columns = [FRIENDLY_COLUMNS.get(col, col.replace("_", " ").title()) for col in out.columns]
    return out


def _show_table(df: pd.DataFrame) -> None:
    st.dataframe(_friendly_dataframe(df), use_container_width=True, hide_index=True)


def _minutes_to_day_label(total_minutes: float | int | None) -> str:
    if total_minutes is None or pd.isna(total_minutes):
        return ""
    minute_value = int(total_minutes)
    day_index = max(0, minute_value // 1440)
    day_name = DAY_ORDER[min(day_index, len(DAY_ORDER) - 1)]
    minute_of_day = minute_value % 1440
    hour = minute_of_day // 60
    minute = minute_of_day % 60
    return f"{day_name} {hour:02d}:{minute:02d}"


def _normalize_line_list(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        try:
            raw_value = json.loads(raw_value)
        except Exception:
            return []
    if isinstance(raw_value, (list, tuple, set)):
        return [str(item) for item in raw_value if item is not None and str(item).strip()]
    return []


def _natural_shift_sort_key(shift_name: Any) -> tuple[int, int, str]:
    text = str(shift_name).strip()
    parts = text.split()
    day_rank = len(DAY_ORDER)
    shift_rank = 999
    if parts:
        first = parts[0][:3].title()
        if first in DAY_ORDER:
            day_rank = DAY_ORDER.index(first)
    for token in parts:
        if token.isdigit():
            shift_rank = int(token)
            break
    else:
        import re

        match = re.search(r"(\d+)", text)
        if match:
            shift_rank = int(match.group(1))
    return (day_rank, shift_rank, text.lower())


def _image_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "svg": "image/svg+xml",
    }
    mime_type = mime_map.get(suffix, "application/octet-stream")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _inject_app_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --primary: #174EA6;
            --primary-2: #1E3A8A;
            --surface: #FFFFFF;
            --surface-soft: #F8FAFC;
            --surface-muted: #EEF2F7;
            --text: #0F172A;
            --text-soft: #475569;
            --border: #D9E2EC;
            --success: #DDF5E6;
            --success-text: #166534;
            --warning: #FEF3C7;
            --warning-text: #92400E;
            --danger: #FDE2E1;
            --danger-text: #991B1B;
            --shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
            --radius: 18px;
        }
        .stApp {
            background:
                radial-gradient(circle at top right, rgba(23, 78, 166, 0.06), transparent 26%),
                linear-gradient(180deg, #F6F9FC 0%, #F9FBFD 100%);
        }
        .main .block-container {
            max-width: 1720px;
            padding-top: 1rem;
            padding-bottom: 2rem;
            padding-left: 1.2rem;
            padding-right: 1.2rem;
        }
        h1, h2, h3, h4 { color: var(--text); }
        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1rem 1.05rem;
            box-shadow: var(--shadow);
        }
        [data-testid="stMetricLabel"] {
            color: var(--text-soft);
            font-weight: 600;
        }
        [data-testid="stMetricValue"] {
            color: var(--text);
        }
        .hero-card, .ui-card {
            background: rgba(255,255,255,0.92);
            border: 1px solid var(--border);
            border-radius: 22px;
            box-shadow: var(--shadow);
            padding: 1.2rem 1.35rem;
        }
        .hero-card {
            background:
                linear-gradient(135deg, rgba(23, 78, 166, 0.06), rgba(255,255,255,0.95)),
                var(--surface);
            padding: 1.45rem 1.55rem;
            margin-bottom: 0.9rem;
        }
        .hero-layout {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1.25rem;
            width: 100%;
            flex-wrap: wrap;
        }
        .hero-left {
            display: flex;
            align-items: center;
            gap: 1rem;
            min-width: 320px;
            flex: 1 1 520px;
        }
        .hero-identity-logo {
            flex: 0 0 auto;
            max-height: 72px;
            width: auto;
            object-fit: contain;
        }
        .hero-copy {
            min-width: 0;
        }
        .hero-title {
            font-size: 1.85rem;
            font-weight: 800;
            color: var(--text);
            line-height: 1.15;
            margin-bottom: 0.35rem;
        }
        .hero-subtitle {
            color: var(--text-soft);
            font-size: 1rem;
            line-height: 1.55;
            max-width: 740px;
            margin-bottom: 0;
        }
        .hero-right {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 1rem;
            flex: 0 1 460px;
            flex-wrap: wrap;
        }
        .hero-logo {
            display: block;
            width: auto;
            height: auto;
            object-fit: contain;
            max-width: 100%;
        }
        .hero-logo-company {
            max-height: 78px;
        }
        .hero-logo-project {
            max-height: 72px;
        }
        .badge-row, .stepper-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.9rem;
        }
        .hero-badge, .step-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.4rem 0.72rem;
            border-radius: 999px;
            border: 1px solid var(--border);
            background: rgba(255,255,255,0.75);
            color: var(--text-soft);
            font-size: 0.82rem;
            font-weight: 700;
        }
        .step-badge-active {
            background: var(--primary);
            border-color: var(--primary);
            color: white;
        }
        .section-head {
            margin: 0.2rem 0 0.8rem 0;
        }
        .section-eyebrow {
            color: var(--primary);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.18rem;
        }
        .section-title {
            color: var(--text);
            font-size: 1.3rem;
            font-weight: 780;
            margin-bottom: 0.16rem;
        }
        .section-subtitle {
            color: var(--text-soft);
            font-size: 0.95rem;
            line-height: 1.5;
        }
        .metric-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 18px;
            box-shadow: var(--shadow);
            padding: 1rem 1.05rem;
            min-height: 110px;
        }
        .metric-top {
            display:flex;
            align-items:center;
            justify-content:space-between;
            margin-bottom:0.6rem;
        }
        .metric-label {
            color: var(--text-soft);
            font-size: 0.83rem;
            font-weight: 700;
        }
        .metric-icon {
            font-size: 1rem;
            opacity: 0.9;
        }
        .metric-value {
            color: var(--text);
            font-size: 1.65rem;
            font-weight: 800;
            line-height: 1.05;
        }
        .metric-note {
            color: var(--text-soft);
            font-size: 0.78rem;
            margin-top: 0.28rem;
        }
        .callout {
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 0.95rem 1rem;
            margin: 0.35rem 0 0.8rem 0;
            font-size: 0.94rem;
            line-height: 1.5;
        }
        .callout strong { display:block; margin-bottom: 0.18rem; }
        .callout-info { background: #EFF6FF; color: #1E3A8A; border-color: #BFDBFE; }
        .callout-success { background: var(--success); color: var(--success-text); border-color: #B7E4C7; }
        .callout-warning { background: var(--warning); color: var(--warning-text); border-color: #FCD34D; }
        .callout-danger { background: var(--danger); color: var(--danger-text); border-color: #FECACA; }
        .status-pill {
            display:inline-flex;
            align-items:center;
            padding:0.32rem 0.7rem;
            border-radius:999px;
            font-size:0.8rem;
            font-weight:700;
            border:1px solid var(--border);
            margin-right:0.4rem;
            margin-bottom:0.35rem;
        }
        .status-ready { background:#EFF6FF; color:#1E3A8A; border-color:#BFDBFE; }
        .status-good { background:var(--success); color:var(--success-text); border-color:#B7E4C7; }
        .status-wait { background:var(--warning); color:var(--warning-text); border-color:#FDE68A; }
        .status-stop { background:var(--danger); color:var(--danger-text); border-color:#FECACA; }
        .stButton > button, .stDownloadButton > button {
            border-radius: 12px;
            border: 1px solid #C7D2E0;
            background: white;
            color: var(--text);
            font-weight: 700;
            padding: 0.7rem 1rem;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.05);
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(180deg, var(--primary), var(--primary-2));
            color: white;
            border-color: var(--primary);
        }
        div[data-testid="stTabs"] button[role="tab"] {
            border-radius: 12px 12px 0 0;
            padding: 0.7rem 0.95rem;
            font-weight: 700;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            color: var(--primary);
        }
        div[role="radiogroup"] {
            gap: 0.6rem;
        }
        div[role="radiogroup"] label {
            background: rgba(255,255,255,0.85);
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 0.5rem 0.85rem;
            box-shadow: var(--shadow);
        }
        div[role="radiogroup"] label:has(input:checked) {
            background: var(--primary);
            border-color: var(--primary);
        }
        div[role="radiogroup"] label:has(input:checked) div {
            color: white !important;
            font-weight: 800;
        }
        .compact-note {
            color: var(--text-soft);
            font-size: 0.86rem;
        }
        .detail-card {
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96));
            border: 1px solid var(--border);
            border-radius: 20px;
            box-shadow: var(--shadow);
            padding: 1rem 1.05rem;
        }
        .detail-title {
            color: var(--text);
            font-size: 1.02rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
        }
        .detail-subtitle {
            color: var(--text-soft);
            font-size: 0.85rem;
            margin-bottom: 0.85rem;
        }
        .detail-kv-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem 0.9rem;
        }
        .detail-kv {
            padding: 0.7rem 0.75rem;
            border-radius: 14px;
            background: rgba(239, 246, 255, 0.58);
            border: 1px solid #DBEAFE;
        }
        .detail-kv-label {
            color: var(--text-soft);
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.15rem;
        }
        .detail-kv-value {
            color: var(--text);
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.25;
        }
        .detail-section {
            margin-top: 0.95rem;
            padding-top: 0.85rem;
            border-top: 1px solid var(--border);
        }
        .detail-section-title {
            color: var(--text);
            font-size: 0.9rem;
            font-weight: 800;
            margin-bottom: 0.55rem;
        }
        @media (max-width: 900px) {
            .hero-card {
                padding: 1.15rem 1.1rem;
            }
            .hero-layout {
                gap: 0.95rem;
            }
            .hero-left {
                min-width: 100%;
                flex-basis: 100%;
            }
            .hero-right {
                justify-content: flex-start;
                flex-basis: 100%;
            }
            .hero-identity-logo {
                max-height: 52px;
            }
            .hero-logo-company {
                max-height: 68px;
            }
            .hero-logo-project {
                max-height: 64px;
            }
            .hero-title {
                font-size: 1.55rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_hero() -> None:
    company_logo = _image_data_uri(COMPANY_LOGO_PATH)
    project_logo = _image_data_uri(PROJECT_LOGO_PATH)
    hero_left_logo_html = (
        f'<img class="hero-identity-logo" src="{company_logo or project_logo}" alt="Brand logo" />'
        if (company_logo or project_logo)
        else ""
    )
    company_logo_html = (
        f'<img class="hero-logo hero-logo-company" src="{company_logo}" alt="Company logo" />'
        if company_logo
        else ""
    )
    project_logo_html = (
        f'<img class="hero-logo hero-logo-project" src="{project_logo}" alt="Project logo" />'
        if project_logo
        else ""
    )
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="hero-layout">
                <div class="hero-left">
                    {hero_left_logo_html}
                    <div class="hero-copy">
                        <div class="hero-title">Advanced Scheduling System Demo</div>
                        <div class="hero-subtitle">
                            Demonstration of production planning and workforce planning for multi-variant manufacturing.
                            Review input data, run optimization scenarios, and present cost and staffing outcomes with clear business context.
                        </div>
                    </div>
                </div>
                <div class="hero-right">
                    {company_logo_html}
                    {project_logo_html}
                </div>
            </div>
            <div class="badge-row">
                <span class="hero-badge">Multi-variant manufacturing</span>
                <span class="hero-badge">Production planning</span>
                <span class="hero-badge">Workforce planning</span>
                <span class="hero-badge">Cost visibility</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_header(title: str, subtitle: str = "", eyebrow: str | None = None) -> None:
    eyebrow_html = f'<div class="section-eyebrow">{eyebrow}</div>' if eyebrow else ""
    subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="section-head">
            {eyebrow_html}
            <div class="section-title">{title}</div>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_callout(title: str, body: str, tone: str = "info") -> None:
    st.markdown(
        f'<div class="callout callout-{tone}"><strong>{title}</strong>{body}</div>',
        unsafe_allow_html=True,
    )


def _render_metric_cards(cards: list[dict[str, str]], columns: int = 4) -> None:
    cols = st.columns(columns)
    for idx, card in enumerate(cards):
        with cols[idx % columns]:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-top">
                        <div class="metric-label">{card.get("label", "")}</div>
                        <div class="metric-icon">{card.get("icon", "")}</div>
                    </div>
                    <div class="metric-value">{card.get("value", "")}</div>
                    <div class="metric-note">{card.get("note", "")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_status_pills(items: list[tuple[str, str]]) -> None:
    html = "".join(
        f'<span class="status-pill status-{tone}">{label}</span>'
        for label, tone in items
    )
    st.markdown(html, unsafe_allow_html=True)


def _build_export_bundle(
    scenario_name: str,
    machine_result: dict[str, Any] | None,
    demand_df: pd.DataFrame | None,
    manpower_result: dict[str, Any] | None,
) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zip_file:
        manifest = {
            "scenario": scenario_name,
            "machine_result_available": bool(machine_result),
            "derived_demand_available": demand_df is not None and not demand_df.empty,
            "manpower_result_available": bool(manpower_result),
        }
        zip_file.writestr("manifest.json", json.dumps(manifest, indent=2))
        if machine_result is not None:
            zip_file.writestr("machine_schedule.csv", machine_result["schedule_df"].to_csv(index=False))
            zip_file.writestr("machine_dropped_orders.csv", machine_result["dropped_orders_df"].to_csv(index=False))
            zip_file.writestr("machine_capacity.csv", machine_result["capacity_chart_df"].to_csv(index=False))
        if demand_df is not None and not demand_df.empty:
            zip_file.writestr("derived_demand.csv", demand_df.to_csv(index=False))
        if manpower_result is not None:
            zip_file.writestr("manpower_assignments.csv", manpower_result["assignments_df"].to_csv(index=False))
            zip_file.writestr("manpower_shortages.csv", manpower_result["shortage_heatmap_df"].to_csv(index=False))
            zip_file.writestr("manpower_coverage.csv", manpower_result["coverage_table_df"].to_csv(index=False))
    return buffer.getvalue()


def _reset_demo_state() -> None:
    reset_all_scenarios()
    _list_scenarios.clear()
    _load_scenario.clear()
    _validate_scenario.clear()
    _run_machine.clear()
    _build_demand.clear()
    _run_manpower.clear()
    st.session_state["machine_run_path"] = None
    st.session_state["manpower_run_path"] = None
    st.session_state["reset_notice"] = "Example data sets were restored and previous run results were cleared."


def _clear_workspace_run_results() -> None:
    st.session_state["workspace_machine_result"] = None
    st.session_state["workspace_manpower_result"] = None
    st.session_state["workspace_demand_df"] = None


def _load_workspace_from_scenario(selected_record: dict[str, Any] | None) -> dict[str, Any] | None:
    if selected_record is None:
        return None
    scenario = _load_scenario(str(selected_record["path"]))
    st.session_state["workspace_scenario_name"] = scenario["name"]
    st.session_state["workspace_meta"] = dict(scenario["meta"])
    raw_tables = {
        cfg["filename"]: scenario["raw_tables"][cfg["filename"]].copy()
        for cfg in TABLE_CONFIGS
    }
    machine_orders_raw = raw_tables.get("machine_orders.csv")
    if machine_orders_raw is not None and "priority" in machine_orders_raw.columns:
        raw_tables["machine_orders.csv"] = machine_orders_raw.drop(columns=["priority"])
    st.session_state["workspace_raw_tables"] = raw_tables
    _clear_workspace_run_results()
    return scenario


def _get_workspace_signature(selected_name: str | None) -> str:
    return f"workspace::{selected_name or 'none'}"


def _ensure_workspace(selected_record: dict[str, Any] | None, selected_name: str | None) -> dict[str, Any] | None:
    signature = _get_workspace_signature(selected_name)
    if st.session_state.get("workspace_signature") != signature:
        st.session_state["workspace_signature"] = signature
        return _load_workspace_from_scenario(selected_record)
    if selected_record is None:
        return None
    return _build_runtime_scenario(
        st.session_state.get("workspace_scenario_name", selected_name or "scenario"),
        st.session_state.get("workspace_meta", {}),
        st.session_state.get("workspace_raw_tables", {}),
    )


def _build_runtime_scenario(
    scenario_name: str,
    meta: dict[str, Any],
    raw_tables: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    if not raw_tables:
        return None
    normalized_tables: dict[str, pd.DataFrame] = {}
    raw_table_copies: dict[str, pd.DataFrame] = {}
    for cfg in TABLE_CONFIGS:
        filename = cfg["filename"]
        if filename not in raw_tables:
            return None
        raw_df = raw_tables[filename].copy()
        raw_table_copies[filename] = raw_df
        normalized_tables[filename] = normalize_table(raw_df, filename)

    return {
        "name": scenario_name,
        "path": Path(scenario_name),
        "meta": meta,
        "tables": normalized_tables,
        "raw_tables": raw_table_copies,
        "machine_orders": normalized_tables["machine_orders.csv"],
        "machine_lines": normalized_tables["machine_lines.csv"],
        "machine_changeovers": normalized_tables["machine_changeovers.csv"],
        "employees": normalized_tables["employees.csv"],
        "shifts": normalized_tables["shifts.csv"],
        "line_shift_requirements": normalized_tables["line_shift_requirements.csv"],
    }


def _validate_runtime_scenario(raw_tables: dict[str, pd.DataFrame]) -> list[str]:
    errors: list[str] = []
    for cfg in TABLE_CONFIGS:
        filename = cfg["filename"]
        validator = TABLE_VALIDATORS[filename]
        raw_df = raw_tables.get(filename)
        if raw_df is None:
            errors.append(f"{filename}: table is missing from the workspace.")
            continue
        errors.extend(validator(raw_df.copy()))
    return errors


def _run_machine_for_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    result = solve_machine_demo(
        scenario["machine_orders"],
        scenario["machine_lines"],
        scenario["machine_changeovers"],
    )
    result["kpis_df"] = build_machine_kpis(
        result["schedule_df"],
        result["dropped_df"],
        result["line_summary_df"],
        result["solver_summary"],
    )
    result["cost_breakdown_df"] = build_machine_cost_breakdown_df(
        result["schedule_df"],
        result["dropped_df"],
        result["line_summary_df"],
        result["solver_summary"],
    )
    result["gantt_df"] = build_machine_gantt_df(result["schedule_df"])
    result["capacity_chart_df"] = build_capacity_chart_df(result["line_summary_df"])
    result["dropped_orders_df"] = build_dropped_orders_df(result["dropped_df"])
    return result

def _build_demand_for_scenario(scenario: dict[str, Any], machine_result: dict[str, Any]) -> pd.DataFrame:
    return build_line_shift_demand(
        machine_result["schedule_df"],
        scenario["shifts"],
        scenario["line_shift_requirements"],
    )


def _run_manpower_for_scenario(scenario: dict[str, Any], demand_df: pd.DataFrame) -> dict[str, Any]:
    manpower_result = solve_manpower_demo(
        scenario["employees"],
        scenario["shifts"],
        demand_df,
    )
    manpower_result["demand_df"] = demand_df
    manpower_result["kpis_df"] = build_manpower_kpis(
        manpower_result["assignments_df"],
        manpower_result["shortage_df"],
        manpower_result["coverage_summary_df"],
        manpower_result["solver_summary"],
    )
    manpower_result["cost_breakdown_df"] = build_manpower_cost_breakdown_df(
        manpower_result["assignments_df"],
        manpower_result["shortage_df"],
        manpower_result["coverage_summary_df"],
        manpower_result["solver_summary"],
    )
    manpower_result["shortage_heatmap_df"] = build_shortage_heatmap_df(manpower_result["shortage_df"])
    manpower_result["employee_schedule_df"] = build_employee_schedule_df(manpower_result["assignments_df"])
    manpower_result["coverage_table_df"] = build_coverage_table_df(manpower_result["coverage_summary_df"])
    return manpower_result


def _render_machine_orders_input_chart(machine_orders_df: pd.DataFrame) -> None:
    if machine_orders_df.empty:
        st.info("No production orders are available.")
        return
    view_df = machine_orders_df.copy()
    if "duration_min" in view_df.columns:
        view_df["duration_min"] = pd.to_numeric(view_df["duration_min"], errors="coerce")
    view_df = view_df.sort_values(["duration_min", "bo_id"], ascending=[False, True]).reset_index(drop=True)
    view_df["duration_label"] = view_df["duration_min"].fillna(0).astype(int).astype(str) + " min"
    line_counts: list[int] = []
    for _, row in view_df.iterrows():
        eligible_lines = _normalize_line_list(row.get("eligible_lines_json", []))
        line_counts.append(len(eligible_lines))
    view_df["allowed_line_count"] = line_counts

    st.markdown("**Processing Time by Order**")

    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Total Orders", int(len(view_df)))
    kpi_cols[1].metric("Total Processing Time", f"{int(view_df['duration_min'].sum())} min")
    kpi_cols[2].metric("Average Duration", f"{int(view_df['duration_min'].mean())} min")
    kpi_cols[3].metric("Single-Line Orders", int((view_df["allowed_line_count"] == 1).sum()))

    product_palette = ["#0072B2", "#E69F00", "#009E73"]
    max_duration = float(view_df["duration_min"].max()) if not view_df["duration_min"].isna().all() else 0.0
    x_axis_max = max_duration + max(8.0, max_duration * 0.04)
    chart = (
        alt.Chart(view_df)
        .mark_bar(size=28)
        .encode(
            x=alt.X(
                "duration_min:Q",
                title="Processing Time (minutes)",
                scale=alt.Scale(domain=[0, x_axis_max]),
            ),
            y=alt.Y("bo_id:N", title="Order", sort="-x"),
            color=alt.Color(
                "product_code:N",
                title="Product",
                scale=alt.Scale(domain=["P1", "P2", "P3"], range=product_palette),
            ),
            tooltip=[
                alt.Tooltip("bo_id:N", title="Order"),
                alt.Tooltip("product_code:N", title="Product"),
                alt.Tooltip("duration_min:Q", title="Processing Time (minutes)"),
                alt.Tooltip("allowed_line_count:Q", title="Allowed Lines"),
            ],
        )
        .properties(height=max(220, 60 + 32 * len(view_df)))
    )
    chart_labels = (
        alt.Chart(view_df)
        .mark_text(align="left", baseline="middle", dx=6, color="#374151")
        .encode(
            x=alt.X("duration_min:Q"),
            y=alt.Y("bo_id:N", sort="-x"),
            text="duration_label:N",
        )
    )
    st.altair_chart((chart + chart_labels).configure_axis(labelColor="#374151", titleColor="#374151"), use_container_width=True)

    all_lines: set[str] = set()
    for _, row in view_df.iterrows():
        eligible_lines = _normalize_line_list(row.get("eligible_lines_json", []))
        all_lines.update(eligible_lines)
    matrix_rows: list[dict[str, Any]] = []
    for _, row in view_df.iterrows():
        eligible_lines = _normalize_line_list(row.get("eligible_lines_json", []))
        line_penalties = row.get("line_preference_penalty_json", {})
        if isinstance(line_penalties, str):
            try:
                line_penalties = json.loads(line_penalties)
            except Exception:
                line_penalties = {}
        parsed_penalties: dict[str, float] = {}
        if isinstance(line_penalties, dict):
            parsed_penalties = {str(key): float(value) for key, value in line_penalties.items()}
        for allowed_line in eligible_lines:
            parsed_penalties.setdefault(str(allowed_line), 0.0)
        unique_penalties = sorted(set(parsed_penalties.values()))
        penalty_rank_map = {penalty: idx + 1 for idx, penalty in enumerate(unique_penalties)}
        min_penalty = min(parsed_penalties.values()) if parsed_penalties else None
        for line_id in all_lines:
            is_allowed = line_id in eligible_lines
            penalty_value = parsed_penalties.get(line_id)
            is_preferred = bool(is_allowed and min_penalty is not None and penalty_value == min_penalty)
            line_rank = penalty_rank_map.get(penalty_value) if is_allowed and penalty_value is not None else None
            matrix_rows.append(
                {
                    "bo_id": row["bo_id"],
                    "line_id": line_id,
                    "is_allowed": is_allowed,
                    "is_preferred": is_preferred,
                    "line_rank": line_rank,
                    "cell_label": str(int(line_rank)) if line_rank is not None else "N/A",
                    "status": (
                        "Best Allowed Line"
                        if is_preferred
                        else "Allowed Line"
                        if is_allowed
                        else "Not Allowed"
                    ),
                }
            )
    if matrix_rows:
        matrix_df = pd.DataFrame(matrix_rows)
        line_order = sorted(matrix_df["line_id"].drop_duplicates())
        st.markdown("**Allowed Line Matrix**")
        st.caption(
            "Input data view. Rank 1 = best allowed line based on line settings. Highlighted cells show the best allowed line(s); N/A means the line is not allowed."
        )
        st.markdown(
            "<div style='display:flex;gap:20px;align-items:center;color:#374151;font-size:0.92rem;'>"
            "<span style='display:flex;align-items:center;gap:8px;'><span style='display:inline-block;width:14px;height:14px;background:#FDE68A;border:1px solid #D1D5DB;'></span>Best allowed line</span>"
            "<span style='display:flex;align-items:center;gap:8px;'><span style='display:inline-block;width:14px;height:14px;background:#CBD5E1;border:1px solid #D1D5DB;'></span>Allowed line</span>"
            "<span style='display:flex;align-items:center;gap:8px;'><span style='display:inline-block;width:14px;height:14px;background:#F7F8FA;border:1px solid #D1D5DB;'></span>Not allowed</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        option_base = alt.Chart(matrix_df).encode(
            x=alt.X("line_id:N", title="Production Line", sort=line_order),
            y=alt.Y("bo_id:N", title="Order", sort=list(view_df["bo_id"])),
            tooltip=[
                alt.Tooltip("bo_id:N", title="Order"),
                alt.Tooltip("line_id:N", title="Production Line"),
                alt.Tooltip("line_rank:Q", title="Line Rank"),
                alt.Tooltip("status:N", title="Status"),
            ],
        )
        option_chart = (
            option_base.mark_rect(stroke="#D1D5DB", strokeWidth=1)
            .encode(
                color=alt.Color(
                    "status:N",
                    title="Line Status",
                    scale=alt.Scale(
                        domain=["Best Allowed Line", "Allowed Line", "Not Allowed"],
                        range=["#FDE68A", "#CBD5E1", "#F7F8FA"],
                    ),
                    legend=None,
                )
            )
            .properties(height=max(220, 60 + 28 * matrix_df["bo_id"].nunique()))
        )
        option_text = option_base.mark_text(fontSize=12, fontWeight="bold").encode(
            text=alt.Text("cell_label:N"),
            color=alt.condition(
                alt.datum.status == "Not Allowed",
                alt.value("#9CA3AF"),
                alt.value("#374151"),
            ),
        )
        st.altair_chart(
            (option_chart + option_text).configure_axis(labelColor="#374151", titleColor="#374151").configure_view(stroke="#D1D5DB"),
            use_container_width=True,
        )


def _render_machine_lines_input_chart(machine_lines_df: pd.DataFrame) -> None:
    if machine_lines_df.empty:
        st.info("No production line availability data is available.")
        return
    view_df = machine_lines_df.copy()
    view_df["capacity_min"] = pd.to_numeric(view_df["capacity_min"], errors="coerce").fillna(0)
    view_df["weekly_hours"] = view_df["capacity_min"] / 60.0
    view_df["capacity_label"] = view_df.apply(
        lambda row: (
            f"{int(row['capacity_min'])} min ({int(row['weekly_hours'])} hrs)"
            if float(row["weekly_hours"]).is_integer()
            else f"{int(row['capacity_min'])} min ({row['weekly_hours']:.1f} hrs)"
        ),
        axis=1,
    )
    view_df = view_df.sort_values(["capacity_min", "display_name"], ascending=[False, True]).reset_index(drop=True)

    st.markdown("**Available Time by Production Line**")
    st.caption(
        "Input data view. This shows weekly available time for each line on the same Monday-Friday planning calendar used by shifts and staffing."
    )

    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Total Lines", int(len(view_df)))
    kpi_cols[1].metric("Total Weekly Time", f"{int(view_df['capacity_min'].sum())} min")
    kpi_cols[2].metric("Average per Line", f"{int(view_df['capacity_min'].mean())} min")
    kpi_cols[3].metric("Available All 5 Days", int(len(view_df)))

    max_capacity = float(view_df["capacity_min"].max()) if not view_df["capacity_min"].isna().all() else 0.0
    x_axis_max = max_capacity + max(10.0, max_capacity * 0.05)
    weekly_chart = (
        alt.Chart(view_df)
        .mark_bar(size=28, color="#4E79A7")
        .encode(
            x=alt.X(
                "capacity_min:Q",
                title="Weekly Available Time (minutes)",
                scale=alt.Scale(domain=[0, x_axis_max]),
            ),
            y=alt.Y("display_name:N", title="Production Line", sort="-x"),
            tooltip=[
                alt.Tooltip("display_name:N", title="Production Line"),
                alt.Tooltip("line_id:N", title="Line ID"),
                alt.Tooltip("capacity_min:Q", title="Weekly Available Time (min)"),
                alt.Tooltip("weekly_hours:Q", title="Weekly Available Time (hours)", format=".1f"),
            ],
        )
        .properties(height=max(180, 70 + 34 * len(view_df)))
    )
    weekly_labels = (
        alt.Chart(view_df)
        .mark_text(align="left", baseline="middle", dx=6, color="#374151")
        .encode(
            x=alt.X("capacity_min:Q"),
            y=alt.Y("display_name:N", sort="-x"),
            text="capacity_label:N",
        )
    )
    st.altair_chart(
        (weekly_chart + weekly_labels).configure_axis(labelColor="#374151", titleColor="#374151"),
        use_container_width=True,
    )

    daily_rows: list[dict[str, Any]] = []
    for _, row in view_df.iterrows():
        daily_capacity = float(row["capacity_min"]) / 5.0
        for day_name in DAY_ORDER[:5]:
            daily_rows.append(
                {
                    "display_name": row["display_name"],
                    "line_id": row["line_id"],
                    "day": day_name,
                    "daily_capacity_min": daily_capacity,
                    "daily_capacity_label": f"{int(daily_capacity)} min",
                }
            )
    daily_df = pd.DataFrame(daily_rows)
    st.markdown(
        "**Estimated Daily Split** "
        "<span style='display:inline-block;padding:2px 8px;border:1px solid #CBD5E1;border-radius:999px;"
        "background:#F8FAFC;color:#64748B;font-size:0.78rem;font-weight:600;vertical-align:middle;'>Demo only</span>",
        unsafe_allow_html=True,
    )
    st.caption("Weekly time is evenly split across the same Monday-Friday planning calendar used by shifts.")
    daily_matrix = (
        alt.Chart(daily_df)
        .mark_rect(stroke="#CBD5E1", strokeWidth=1.2, color="#F8FAFC")
        .encode(
            x=alt.X("day:N", title="Day", sort=DAY_ORDER[:5]),
            y=alt.Y("display_name:N", title="Production Line", sort=list(view_df["display_name"])),
            tooltip=[
                alt.Tooltip("display_name:N", title="Production Line"),
                alt.Tooltip("day:N", title="Day"),
                alt.Tooltip("daily_capacity_min:Q", title="Estimated Daily Time (min)"),
            ],
        )
        .properties(height=max(180, 70 + 30 * len(view_df)))
    )
    daily_matrix_text = (
        alt.Chart(daily_df)
        .mark_text(color="#374151", fontSize=12)
        .encode(
            x=alt.X("day:N", sort=DAY_ORDER[:5]),
            y=alt.Y("display_name:N", sort=list(view_df["display_name"])),
            text="daily_capacity_label:N",
        )
    )
    st.altair_chart(
        (daily_matrix + daily_matrix_text)
        .configure_axis(labelColor="#374151", titleColor="#374151")
        .configure_view(stroke="#CBD5E1"),
        use_container_width=True,
    )


def _render_shifts_input_chart(shifts_df: pd.DataFrame) -> None:
    if shifts_df.empty:
        st.info("No shifts available.")
        return
    view_df = shifts_df.copy()
    view_df["start_min"] = pd.to_numeric(view_df.get("start_min"), errors="coerce").fillna(0)
    view_df["end_min"] = pd.to_numeric(view_df.get("end_min"), errors="coerce").fillna(0)
    view_df["duration_min"] = (view_df["end_min"] - view_df["start_min"]).clip(lower=0)
    view_df["start_clock_min"] = view_df["start_min"].mod(1440)
    view_df["end_clock_min"] = view_df["end_min"].mod(1440)
    view_df["end_clock_display_min"] = view_df.apply(
        lambda row: 1440 if row["duration_min"] > 0 and row["end_clock_min"] <= row["start_clock_min"] else row["end_clock_min"],
        axis=1,
    )
    view_df["mid_clock_min"] = (view_df["start_clock_min"] + view_df["end_clock_display_min"]) / 2
    view_df["start_label"] = view_df["start_min"].apply(_format_clock_minutes)
    view_df["end_label"] = view_df.apply(
        lambda row: "24:00" if row["duration_min"] > 0 and row["end_clock_min"] <= row["start_clock_min"] else _format_clock_minutes(row["end_min"]),
        axis=1,
    )
    view_df["time_window_label"] = view_df.apply(
        lambda row: f"{row['shift_name']} | {row['start_label']} - {row['end_label']}",
        axis=1,
    )
    day_order = [day for day in DAY_ORDER if day in view_df["day"].astype(str).unique().tolist()]
    if not day_order:
        day_order = sorted(view_df["day"].astype(str).unique().tolist())
    shift_order = list(view_df["shift_name"].drop_duplicates())
    st.markdown("**Defined Shift Windows by Day**")
    st.caption(
        "Input data view. These are the planned shift windows for the week, shown by day and time of day. "
        "They are not production results or staffing assignments."
    )
    shift_cols = st.columns(4)
    shift_cols[0].metric("Total Shifts", int(len(view_df)))
    shift_cols[1].metric("Active Days", int(view_df["day"].nunique()))
    shift_cols[2].metric("Total Defined Hours", f"{int(round(view_df['duration_min'].sum() / 60))} hrs")
    avg_shifts_per_day = len(view_df) / max(view_df["day"].nunique(), 1)
    shift_cols[3].metric("Average Shifts / Day", f"{avg_shifts_per_day:.1f}")

    bars = (
        alt.Chart(view_df)
        .mark_bar(size=34, cornerRadiusEnd=3)
        .encode(
            x=alt.X(
                "start_clock_min:Q",
                title="Time of Day",
                scale=alt.Scale(domain=[0, 1440]),
                axis=alt.Axis(
                    values=[0, 240, 480, 720, 960, 1200, 1440],
                    labelExpr="datum.value === 0 ? '00:00' : datum.value === 240 ? '04:00' : datum.value === 480 ? '08:00' : datum.value === 720 ? '12:00' : datum.value === 960 ? '16:00' : datum.value === 1200 ? '20:00' : '24:00'",
                    labelColor="#374151",
                    titleColor="#374151",
                ),
            ),
            x2="end_clock_display_min:Q",
            y=alt.Y("day:N", title=None, sort=day_order, axis=alt.Axis(labelColor="#374151", titleColor="#374151")),
            yOffset=alt.YOffset("shift_name:N", sort=shift_order),
            color=alt.value("#93C5FD"),
            stroke=alt.value("#2563EB"),
            tooltip=[
                alt.Tooltip("shift_id:N", title="Shift ID"),
                alt.Tooltip("shift_name:N", title="Shift"),
                alt.Tooltip("day:N", title="Day"),
                alt.Tooltip("start_label:N", title="Start"),
                alt.Tooltip("end_label:N", title="End"),
                alt.Tooltip("duration_min:Q", title="Duration (min)"),
            ],
        )
        .properties(height=max(220, 44 * len(day_order)))
    )
    labels = (
        alt.Chart(view_df)
        .mark_text(fontSize=11, fontWeight="bold", color="#1E3A8A", baseline="middle")
        .encode(
            x=alt.X("mid_clock_min:Q"),
            y=alt.Y("day:N", sort=day_order),
            yOffset=alt.YOffset("shift_name:N", sort=shift_order),
            text="time_window_label:N",
        )
    )
    chart = (bars + labels).configure_view(stroke="#CBD5E1")
    st.altair_chart(chart, use_container_width=True)


def _render_requirements_input_chart(requirements_df: pd.DataFrame) -> None:
    if requirements_df.empty:
        st.info("No staffing requirement data is available.")
        return
    view_df = requirements_df.copy()
    view_df["required_qty"] = pd.to_numeric(view_df["required_qty"], errors="coerce").fillna(0).astype(int)
    view_df["line_id"] = view_df["line_id"].astype(str)
    view_df["shift_name"] = view_df["shift_name"].astype(str)
    view_df["competency"] = view_df["competency"].astype(str)
    view_df["shift_sort"] = view_df["shift_name"].map(_natural_shift_sort_key)

    aggregated_df = (
        view_df.groupby(["line_id", "shift_name", "competency"], as_index=False)
        .agg(required_qty=("required_qty", "sum"))
        .copy()
    )

    line_order = sorted(aggregated_df["line_id"].dropna().astype(str).unique().tolist())
    shift_order = (
        aggregated_df[["shift_name"]]
        .drop_duplicates()
        .assign(_sort_key=lambda df: df["shift_name"].map(_natural_shift_sort_key))
        .sort_values("_sort_key")["shift_name"]
        .tolist()
    )
    skill_totals = (
        aggregated_df.groupby("competency", as_index=False)
        .agg(total_required=("required_qty", "sum"), max_required=("required_qty", "max"), staffing_rows=("required_qty", "size"))
        .sort_values(["total_required", "competency"], ascending=[False, True])
        .reset_index(drop=True)
    )
    skill_order = skill_totals["competency"].tolist()
    line_count = len(line_order)
    shift_count = len(shift_order)
    skill_count = len(skill_order)
    highest_required = int(aggregated_df["required_qty"].max()) if not aggregated_df.empty else 0
    busiest_shift_row = (
        aggregated_df.groupby("shift_name", as_index=False)
        .agg(total_required=("required_qty", "sum"))
        .sort_values(["total_required", "shift_name"], ascending=[False, True])
        .head(1)
    )
    busiest_shift = str(busiest_shift_row.iloc[0]["shift_name"]) if not busiest_shift_row.empty else "N/A"
    busiest_shift_total = int(busiest_shift_row.iloc[0]["total_required"]) if not busiest_shift_row.empty else 0
    total_staffing_rows = int(len(aggregated_df))

    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Staffing Rows", f"{total_staffing_rows:,}")
    kpi_cols[1].metric("Highest Headcount", f"{highest_required:,}")
    kpi_cols[2].metric("Busiest Shift", f"{busiest_shift} ({busiest_shift_total:,})")
    kpi_cols[3].metric("Required Skills", f"{skill_count:,}")

    st.caption(
        "Input / master data view. Missing combinations are shown as 0 so it is clear where no staffing requirement exists."
    )

    if aggregated_df.empty:
        st.info("No staffing requirement data is available.")
        return

    for competency in skill_order:
        skill_df = aggregated_df[aggregated_df["competency"] == competency].copy()
        grid = pd.MultiIndex.from_product(
            [line_order, shift_order],
            names=["line_id", "shift_name"],
        ).to_frame(index=False)
        grid = grid.merge(skill_df[["line_id", "shift_name", "required_qty"]], on=["line_id", "shift_name"], how="left")
        grid["required_qty"] = grid["required_qty"].fillna(0).astype(int)

        st.markdown(f"**{competency}**")
        skill_summary_cols = st.columns(3)
        skill_summary_cols[0].metric("Rows", f"{int(len(skill_df)):,}")
        skill_summary_cols[1].metric("Peak", f"{int(skill_df['required_qty'].max()) if not skill_df.empty else 0:,}")
        skill_summary_cols[2].metric("Affected Lines", f"{int(skill_df['line_id'].nunique()) if not skill_df.empty else 0:,}")
        matrix_df = (
            grid.pivot(index="line_id", columns="shift_name", values="required_qty")
            .reindex(index=line_order, columns=shift_order)
            .fillna(0)
            .astype(int)
        )
        max_for_skill = int(matrix_df.to_numpy().max()) if not matrix_df.empty else 0

        def _cell_style(value: Any) -> str:
            try:
                qty = int(value)
            except Exception:
                qty = 0
            if qty <= 0 or max_for_skill <= 0:
                return "background-color: #F8FAFC; color: #475569; font-weight: 600;"
            ratio = qty / max_for_skill
            if ratio >= 0.8:
                return "background-color: #1D4ED8; color: #FFFFFF; font-weight: 700;"
            if ratio >= 0.55:
                return "background-color: #60A5FA; color: #0F172A; font-weight: 700;"
            if ratio >= 0.3:
                return "background-color: #BFDBFE; color: #0F172A; font-weight: 700;"
            return "background-color: #DBEAFE; color: #0F172A; font-weight: 700;"

        styler = matrix_df.style.format("{:.0f}")
        if hasattr(styler, "map"):
            styler = styler.map(_cell_style)
        else:
            styler = styler.applymap(_cell_style)

        styled_matrix = styler.set_properties(**{"text-align": "center"}).set_table_styles(
            [
                {"selector": "th", "props": [("background-color", "#EFF6FF"), ("color", "#0F172A"), ("font-weight", "700")]},
                {"selector": "td", "props": [("min-width", "78px"), ("border", "1px solid #CBD5E1")]},
            ]
        )
        st.dataframe(styled_matrix, use_container_width=True)
        st.markdown(
            '<div class="compact-note" style="margin-top:-0.25rem; margin-bottom:0.8rem;">'
            "Cells shown as 0 indicate no staffing requirement for that line and shift."
            "</div>",
            unsafe_allow_html=True,
        )


def _render_employees_input_chart(employees_df: pd.DataFrame) -> None:
    if employees_df.empty or "skills_json" not in employees_df.columns:
        st.info("No employee skill data is available.")
        return
    skill_rows: list[dict[str, Any]] = []
    employee_names: list[str] = []
    all_skills: set[str] = set()
    for _, row in employees_df.iterrows():
        employee_name = row.get("employee_name", row.get("employee_id", ""))
        employee_names.append(employee_name)
        skills = row.get("skills_json", {})
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except Exception:
                skills = {}
        if isinstance(skills, dict):
            for competency, score in skills.items():
                all_skills.add(str(competency))
                skill_rows.append(
                    {
                        "employee_name": employee_name,
                        "competency": competency,
                        "score": float(score),
                        "status": "Qualified",
                    }
                )
    if not skill_rows:
        st.info("Employee skills could not be visualized from the current table.")
        return
    for employee_name in employee_names:
        employee_skill_names = {str(row["competency"]) for row in skill_rows if row["employee_name"] == employee_name}
        for competency in all_skills:
            if competency not in employee_skill_names:
                skill_rows.append(
                    {
                        "employee_name": employee_name,
                        "competency": competency,
                        "score": None,
                        "status": "Not Qualified",
                    }
                )
    chart_df = pd.DataFrame(skill_rows)
    qualified_df = chart_df[chart_df["status"] == "Qualified"].copy()
    if not qualified_df.empty:
        employee_order_df = (
            qualified_df.groupby("employee_name")
            .agg(
                qualified_skill_count=("competency", "nunique"),
                max_skill_score=("score", "max"),
            )
            .reset_index()
            .sort_values(["qualified_skill_count", "max_skill_score", "employee_name"], ascending=[False, False, True])
        )
        all_employee_names = employee_order_df["employee_name"].tolist()
    else:
        all_employee_names = sorted(set(employee_names))
    strongest_by_skill = qualified_df.groupby("competency")["score"].max().to_dict()
    multi_skill_count = qualified_df.groupby("employee_name")["competency"].nunique()

    st.markdown("**Employee Skill Matrix**")
    st.caption(
        "Input data view. Each cell shows whether an employee is qualified for a skill and, when qualified, the relative skill score. N/A means not qualified or no rating for that skill."
    )
    skill_cols = st.columns(4)
    skill_cols[0].metric("Employees", int(len(set(employee_names))))
    skill_cols[1].metric("Skills", int(len(all_skills)))
    skill_cols[2].metric("Employees Qualified in 2+ Skills", int((multi_skill_count >= 2).sum()))
    skill_cols[3].metric("Highest Skill Score", int(qualified_df["score"].max()) if not qualified_df.empty else 0)

    skill_chart = (
        alt.Chart(qualified_df)
        .mark_rect(stroke="#D1D5DB", strokeWidth=1)
        .encode(
            x=alt.X("competency:N", title="Skill"),
            y=alt.Y("employee_name:N", title="Employee"),
            color=alt.Color(
                "score:Q",
                title="Skill Score",
                scale=alt.Scale(domain=[0, 100], range=["#F8FAFC", "#BFDBFE", "#1D4ED8"]),
            ),
            tooltip=[
                alt.Tooltip("employee_name:N", title="Employee"),
                alt.Tooltip("competency:N", title="Skill"),
                alt.Tooltip("status:N", title="Qualification"),
                alt.Tooltip("score:Q", title="Skill Score"),
            ],
        )
        .properties(height=max(180, 60 + 28 * len(all_employee_names)))
    )
    neutral_cells = (
        alt.Chart(chart_df[chart_df["status"] == "Not Qualified"])
        .mark_rect(stroke="#D1D5DB", strokeWidth=1, color="#F8FAFC")
        .encode(
            x=alt.X("competency:N", title="Skill"),
            y=alt.Y("employee_name:N", title="Employee"),
            tooltip=[
                alt.Tooltip("employee_name:N", title="Employee"),
                alt.Tooltip("competency:N", title="Skill"),
                alt.Tooltip("status:N", title="Qualification"),
            ],
        )
    )
    skill_text = (
        alt.Chart(chart_df)
        .mark_text(fontSize=11, fontWeight="bold")
        .encode(
            x=alt.X("competency:N"),
            y=alt.Y("employee_name:N"),
            text=alt.condition(
                alt.datum.status == "Not Qualified",
                alt.value("N/A"),
                alt.Text("score:Q", format=".0f"),
            ),
            color=alt.condition(
                alt.datum.status == "Not Qualified",
                alt.value("#9CA3AF"),
                alt.value("#FFFFFF"),
            ),
        )
    )
    st.altair_chart(
        (neutral_cells + skill_chart + skill_text)
        .configure_axis(labelColor="#374151", titleColor="#374151")
        .configure_view(stroke="#D1D5DB"),
        use_container_width=True,
    )
    if strongest_by_skill:
        strongest_df = pd.DataFrame(
            [
                {
                    "Skill": skill,
                    "Top Employee(s)": ", ".join(
                        sorted(
                            chart_df[
                                (chart_df["competency"] == skill)
                                & (chart_df["score"] == score)
                                & (chart_df["status"] == "Qualified")
                            ]["employee_name"].tolist()
                        )
                    ),
                    "Top Score": int(score),
                }
                for skill, score in strongest_by_skill.items()
            ]
        )
        with st.expander("Top employees by skill", expanded=False):
            st.dataframe(strongest_df, use_container_width=True, hide_index=True)

    availability_rows: list[dict[str, Any]] = []
    for _, row in employees_df.iterrows():
        days = row.get("available_days_json", [])
        if isinstance(days, str):
            try:
                days = json.loads(days)
            except Exception:
                days = []
        for day_name in days:
            availability_rows.append(
                {
                    "employee_name": row.get("employee_name", row.get("employee_id", "")),
                    "day": day_name,
                    "availability": "Available",
                }
            )
    availability_df = pd.DataFrame(availability_rows)
    all_employee_names = sorted(set(employee_names))
    all_days = DAY_ORDER[:5]
    full_rows: list[dict[str, Any]] = []
    for employee_name in all_employee_names:
        available_days = set(availability_df[availability_df["employee_name"] == employee_name]["day"].tolist())
        for day_name in all_days:
            full_rows.append(
                {
                    "employee_name": employee_name,
                    "day": day_name,
                    "availability": "Available" if day_name in available_days else "Not Available",
                }
            )
    full_availability_df = pd.DataFrame(full_rows)
    constrained_df = full_availability_df[full_availability_df["availability"] == "Not Available"].copy()

    st.markdown("**Employee Availability**")
    if constrained_df.empty:
        availability_cards = st.columns(3)
        availability_cards[0].metric("Employees", int(len(all_employee_names)))
        availability_cards[1].metric("Work Days", int(len(all_days)))
        availability_cards[2].metric("Availability Constraints", "None")
        st.caption("All employees are available on every demo work day. No day-based availability constraints need attention.")
    else:
        availability_cards = st.columns(3)
        availability_cards[0].metric("Employees", int(len(all_employee_names)))
        availability_cards[1].metric("Constrained Employees", int(constrained_df["employee_name"].nunique()))
        availability_cards[2].metric("Unavailable Day Entries", int(len(constrained_df)))
        st.caption("Input data view. This shows employee day availability only. It does not represent staffing assignments or shift results.")
        availability_chart = (
            alt.Chart(full_availability_df)
            .mark_rect(stroke="#D1D5DB", strokeWidth=1)
            .encode(
                x=alt.X("day:N", title="Day", sort=all_days),
                y=alt.Y("employee_name:N", title="Employee", sort=all_employee_names),
                color=alt.Color(
                    "availability:N",
                    title="Availability",
                    scale=alt.Scale(
                        domain=["Available", "Not Available"],
                        range=["#DFF3E6", "#F8FAFC"],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("employee_name:N", title="Employee"),
                    alt.Tooltip("day:N", title="Day"),
                    alt.Tooltip("availability:N", title="Availability"),
                ],
            )
            .properties(height=max(180, 60 + 28 * len(all_employee_names)))
        )
        availability_text = (
            alt.Chart(full_availability_df)
            .mark_text(fontSize=11, fontWeight="bold")
            .encode(
                x=alt.X("day:N", sort=all_days),
                y=alt.Y("employee_name:N", sort=all_employee_names),
                text=alt.condition(
                    alt.datum.availability == "Available",
                    alt.value("Yes"),
                    alt.value("N/A"),
                ),
                color=alt.condition(
                    alt.datum.availability == "Available",
                    alt.value("#166534"),
                    alt.value("#9CA3AF"),
                ),
            )
        )
        st.altair_chart(
            (availability_chart + availability_text).configure_axis(labelColor="#374151", titleColor="#374151").configure_view(stroke="#D1D5DB"),
            use_container_width=True,
        )


def _render_changeovers_input_chart(changeovers_df: pd.DataFrame) -> None:
    if changeovers_df.empty:
        st.info("No product switch data is available.")
        return
    view_df = changeovers_df.copy()
    view_df["changeover_time_min"] = pd.to_numeric(view_df["changeover_time_min"], errors="coerce").fillna(0)
    view_df["changeover_cost"] = pd.to_numeric(view_df["changeover_cost"], errors="coerce").fillna(0)
    view_df["is_no_change"] = view_df["from_product_code"].astype(str) == view_df["to_product_code"].astype(str)

    st.markdown("**Product Switch Matrix**")
    st.markdown('<div class="compact-note" style="margin-bottom:0.2rem;">Color metric</div>', unsafe_allow_html=True)
    metric_mode = st.radio(
        "Switch metric",
        ["Switch Time", "Switch Cost"],
        horizontal=True,
        key="changeover_metric_mode",
        label_visibility="collapsed",
    )
    st.caption(
        "Input data view. Each cell shows the changeover required when switching from one product to another on a given line."
    )

    metric_col = "changeover_time_min" if metric_mode == "Switch Time" else "changeover_cost"
    metric_title = "Switch Time (min)" if metric_mode == "Switch Time" else "Switch Cost"
    palette = ["#EFF6FF", "#93C5FD", "#1D4ED8"] if metric_mode == "Switch Time" else ["#FFF7ED", "#FDBA74", "#C2410C"]
    value_suffix = " min" if metric_mode == "Switch Time" else " cost"
    offdiag_df = view_df[~view_df["is_no_change"]].copy()
    max_row = offdiag_df.sort_values(metric_col, ascending=False).iloc[0] if not offdiag_df.empty else None
    avg_metric = float(offdiag_df[metric_col].mean()) if not offdiag_df.empty else 0.0

    summary_cols = st.columns(4)
    summary_cols[0].metric("Lines", int(view_df["line_id"].nunique()))
    summary_cols[1].metric("Products", int(pd.unique(pd.concat([view_df["from_product_code"], view_df["to_product_code"]])).size))
    summary_cols[2].metric(
        f"Average {metric_mode}",
        f"{avg_metric:.0f}{value_suffix}",
    )
    summary_cols[3].metric(
        f"Highest {metric_mode}",
        f"{int(max_row[metric_col])}{value_suffix}" if max_row is not None else "0",
    )

    if max_row is not None:
        st.markdown(
            f'<div class="compact-note">Highest {metric_mode.lower()}: {max_row["line_id"]} | '
            f'{max_row["from_product_code"]} → {max_row["to_product_code"]} = {int(max_row[metric_col])}{value_suffix}</div>',
            unsafe_allow_html=True,
        )

    line_signatures = (
        view_df.sort_values(["line_id", "from_product_code", "to_product_code"])[
            ["line_id", "from_product_code", "to_product_code", "changeover_time_min", "changeover_cost"]
        ]
        .groupby("line_id")
        .apply(lambda df: tuple(map(tuple, df[["from_product_code", "to_product_code", "changeover_time_min", "changeover_cost"]].to_records(index=False))))
    )
    all_lines_same = len(set(line_signatures.tolist())) <= 1 if not line_signatures.empty else False
    chart_df = (
        view_df[view_df["line_id"] == view_df["line_id"].iloc[0]].copy()
        if all_lines_same
        else view_df.copy()
    )
    if all_lines_same:
        st.markdown(
            '<div class="compact-note" style="margin-bottom:0.35rem;">All production lines use the same switch values, so one shared matrix is shown.</div>',
            unsafe_allow_html=True,
        )

    base = alt.Chart(chart_df).encode(
        x=alt.X("to_product_code:N", title="To Product"),
        y=alt.Y("from_product_code:N", title="From Product"),
        tooltip=[
            alt.Tooltip("line_id:N", title="Line"),
            alt.Tooltip("from_product_code:N", title="From Product"),
            alt.Tooltip("to_product_code:N", title="To Product"),
            alt.Tooltip("changeover_time_min:Q", title="Switch Time (min)"),
            alt.Tooltip("changeover_cost:Q", title="Switch Cost"),
        ],
    )
    neutral_cells = (
        base.transform_filter(alt.datum.is_no_change)
        .mark_rect(stroke="#D1D5DB", strokeWidth=1, color="#F8FAFC")
    )
    metric_cells = (
        base.transform_filter(~alt.datum.is_no_change)
        .mark_rect(stroke="#D1D5DB", strokeWidth=1)
        .encode(
            color=alt.Color(
                f"{metric_col}:Q",
                title=metric_title,
                scale=alt.Scale(range=palette),
            )
        )
    )
    cell_labels = (
        base.mark_text(fontSize=12, fontWeight="bold")
        .encode(
            text=alt.condition(
                alt.datum.is_no_change,
                alt.value("—"),
                alt.Text(f"{metric_col}:Q", format=".0f"),
            ),
            color=alt.condition(
                alt.datum.is_no_change,
                alt.value("#9CA3AF"),
                alt.value("#374151"),
            ),
        )
    )
    layered = alt.layer(neutral_cells, metric_cells, cell_labels, data=chart_df).properties(width=280, height=240)
    chart = (
        layered
        if all_lines_same
        else layered.facet(column=alt.Column("line_id:N", title="Production Line"))
    )
    st.altair_chart(
        chart.configure_axis(labelColor="#374151", titleColor="#374151").configure_view(stroke="#D1D5DB"),
        use_container_width=True,
    )


def _render_input_visual(table_key: str, table_df: pd.DataFrame) -> None:
    if table_key == "machine_orders":
        _render_machine_orders_input_chart(table_df)
    elif table_key == "machine_lines":
        _render_machine_lines_input_chart(table_df)
    elif table_key == "machine_changeovers":
        _render_changeovers_input_chart(table_df)
    elif table_key == "employees":
        _render_employees_input_chart(table_df)
    elif table_key == "shifts":
        _render_shifts_input_chart(table_df)
    elif table_key == "line_shift_requirements":
        _render_requirements_input_chart(table_df)
    else:
        st.info("No visualization available for this table.")


def _render_output_summary_charts(
    machine_result: dict[str, Any] | None,
    manpower_result: dict[str, Any] | None,
) -> None:
    summary_cols = st.columns(3)
    with summary_cols[0]:
        st.markdown("**Production Plan**")
        if machine_result is None or machine_result["gantt_df"].empty:
            st.info("Run the production planning step to view the production plan.")
        else:
            gantt_df = machine_result["gantt_df"].copy()
            chart = (
                alt.Chart(gantt_df)
                .mark_bar(size=22)
                .encode(
                    x=alt.X("start_min:Q", title="Week Timeline"),
                    x2="end_min:Q",
                    y=alt.Y("display_name:N", title="Line"),
                    color=alt.Color("product_code:N", title="Product"),
                    tooltip=[
                        alt.Tooltip("bo_id:N", title="Order"),
                        alt.Tooltip("display_name:N", title="Line"),
                        alt.Tooltip("start_label:N", title="Start"),
                        alt.Tooltip("end_label:N", title="End"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)
    with summary_cols[1]:
        st.markdown("**Workforce Allocation**")
        if manpower_result is None or manpower_result["assignments_df"].empty:
            st.info("Run the workforce planning step to view the staffing chart.")
        else:
            assignments_df = manpower_result["assignments_df"].copy()
            allocation_chart = (
                alt.Chart(assignments_df)
                .mark_bar(size=24)
                .encode(
                    x=alt.X("count():Q", title="Assigned Workers"),
                    y=alt.Y("line_id:N", title="Line"),
                    color=alt.Color("competency:N", title="Skill"),
                    row=alt.Row("shift_name:N", title="Shift"),
                    tooltip=["line_id", "shift_name", "competency", alt.Tooltip("count():Q", title="Assigned Workers")],
                )
                .properties(height=70)
            )
            st.altair_chart(allocation_chart, use_container_width=True)
    with summary_cols[2]:
        st.markdown("**Cost Summary**")
        cost_rows: list[dict[str, Any]] = []
        if machine_result is not None:
            solver_summary = machine_result["solver_summary"]
            cost_rows.extend(
                [
                    {"category": "Production Setup", "value": int(solver_summary.get("total_setup_cost", 0))},
                    {"category": "Production Switch", "value": int(solver_summary.get("total_changeover_cost", 0))},
                    {"category": "Production Total", "value": int(solver_summary.get("total_machine_cost", 0))},
                ]
            )
        if manpower_result is not None:
            solver_summary = manpower_result["solver_summary"]
            cost_rows.extend(
                [
                    {"category": "Workforce Shift", "value": int(solver_summary.get("total_shift_cost", 0))},
                    {"category": "Workforce Total", "value": int(solver_summary.get("total_manpower_cost", 0))},
                ]
            )
        if not cost_rows:
            st.info("Run the planning steps to view the cost chart.")
        else:
            cost_df = pd.DataFrame(cost_rows)
            cost_chart = (
                alt.Chart(cost_df)
                .mark_bar(size=28)
                .encode(
                    x=alt.X("value:Q", title="Cost"),
                    y=alt.Y("category:N", title=None, sort="-x"),
                    color=alt.Color("category:N", legend=None),
                    tooltip=["category", "value"],
                )
                .properties(height=260)
            )
            st.altair_chart(cost_chart, use_container_width=True)
            _show_table(cost_df)


def _result_status_label(machine_result: dict[str, Any] | None, manpower_result: dict[str, Any] | None) -> str:
    if machine_result is None:
        return "Planning Not Run"
    if manpower_result is None:
        return "Production Ready"
    shortage_qty = int(manpower_result["solver_summary"].get("total_shortage_qty", 0) or 0)
    dropped_orders = int(machine_result["solver_summary"].get("dropped_orders", 0) or 0)
    if dropped_orders == 0 and shortage_qty == 0:
        return "Plan Ready"
    if dropped_orders > 0 and shortage_qty > 0:
        return "Needs Production And Staffing Action"
    if dropped_orders > 0:
        return "Needs Production Action"
    return "Needs Staffing Action"


def _render_results_takeaway(
    machine_result: dict[str, Any] | None,
    manpower_result: dict[str, Any] | None,
) -> None:
    if machine_result is None:
        _render_callout(
            "Planning Not Run",
            "Run the production plan first. This page is designed to summarize business outcomes once planning results are available.",
            tone="warning",
        )
        return

    dropped_orders = int(machine_result["solver_summary"].get("dropped_orders", 0) or 0)
    machine_cost = int(machine_result["solver_summary"].get("total_machine_cost", 0) or 0)
    if manpower_result is None:
        body = (
            f"Production planning completed with {dropped_orders} unscheduled order(s) and total production cost of {machine_cost:,}. "
            "Run workforce planning to complete the staffing story."
        )
        tone = "warning" if dropped_orders > 0 else "info"
    else:
        shortage_qty = int(manpower_result["solver_summary"].get("total_shortage_qty", 0) or 0)
        total_cost = machine_cost + int(manpower_result["solver_summary"].get("total_manpower_cost", 0) or 0)
        if dropped_orders == 0 and shortage_qty == 0:
            body = (
                f"The scenario is fully planned: all orders are scheduled, staffing is fully covered, and total combined cost is {total_cost:,}."
            )
            tone = "success"
        elif dropped_orders > 0 and shortage_qty > 0:
            body = (
                f"The scenario is constrained on both fronts: {dropped_orders} order(s) remain unscheduled and {shortage_qty} worker slot(s) remain unfilled."
            )
            tone = "danger"
        elif dropped_orders > 0:
            body = (
                f"The main issue is production capacity: {dropped_orders} order(s) remain unscheduled, while staffing covers the scheduled workload."
            )
            tone = "warning"
        else:
            body = (
                f"The production plan is feasible, but staffing still has {shortage_qty} unfilled worker slot(s) that need action."
            )
            tone = "warning"
    _render_callout("Executive Takeaway", body, tone=tone)


def _render_cost_overview_chart(
    machine_result: dict[str, Any] | None,
    manpower_result: dict[str, Any] | None,
) -> None:
    cost_rows: list[dict[str, Any]] = []
    if machine_result is not None:
        solver_summary = machine_result["solver_summary"]
        cost_rows.extend(
            [
                {"category": "Production Setup", "value": int(solver_summary.get("total_setup_cost", 0)), "group": "Production"},
                {"category": "Production Switch", "value": int(solver_summary.get("total_changeover_cost", 0)), "group": "Production"},
            ]
        )
    if manpower_result is not None:
        solver_summary = manpower_result["solver_summary"]
        shift_cost = int(solver_summary.get("total_shift_cost", 0) or 0)
        total_cost = int(solver_summary.get("total_manpower_cost", 0) or 0)
        label = "Workforce Cost" if shift_cost == total_cost else "Workforce Shift"
        cost_rows.append({"category": label, "value": shift_cost if label == "Workforce Shift" else total_cost, "group": "Workforce"})
        if label == "Workforce Shift" and total_cost != shift_cost:
            cost_rows.append({"category": "Workforce Total", "value": total_cost, "group": "Workforce"})

    if not cost_rows:
        st.info("Run the planning steps to view cost breakdown.")
        return

    cost_df = pd.DataFrame(cost_rows)
    chart = (
        alt.Chart(cost_df)
        .mark_bar(size=34, cornerRadiusEnd=4)
        .encode(
            x=alt.X("value:Q", title="Cost"),
            y=alt.Y("category:N", title=None, sort="-x"),
            color=alt.Color("group:N", title=None, scale=alt.Scale(range=["#1D4ED8", "#0F766E"])),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("value:Q", title="Cost"),
            ],
        )
        .properties(height=max(180, 70 * len(cost_df)))
    )
    st.altair_chart(chart.configure_view(stroke="#CBD5E1"), use_container_width=True)


def _render_production_demo_panel(machine_result: dict[str, Any] | None) -> None:
    st.markdown("**Production Overview**")
    if machine_result is None:
        st.info("Run the production plan to view the production outcome.")
        return

    solver_summary = machine_result["solver_summary"]
    gantt_df = machine_result["gantt_df"]
    dropped_df = machine_result["dropped_orders_df"]
    prod_cols = st.columns(3)
    prod_cols[0].metric("Run Status", str(solver_summary.get("status", "UNKNOWN")))
    prod_cols[1].metric("Unscheduled Orders", str(int(solver_summary.get("dropped_orders", 0) or 0)))
    prod_cols[2].metric("Production Cost", f"{int(solver_summary.get('total_machine_cost', 0) or 0):,}")

    if gantt_df.empty:
        st.info("No scheduled orders are available for the production timeline.")
        return

    chart = (
        alt.Chart(gantt_df)
        .mark_bar(size=24, cornerRadiusEnd=4)
        .encode(
            x=alt.X("start_min:Q", title="Production Timeline"),
            x2="end_min:Q",
            y=alt.Y("display_name:N", title="Line", sort=list(gantt_df["display_name"].drop_duplicates())),
            color=alt.Color("product_code:N", title="Product"),
            tooltip=[
                alt.Tooltip("bo_id:N", title="Order"),
                alt.Tooltip("display_name:N", title="Line"),
                alt.Tooltip("start_label:N", title="Start"),
                alt.Tooltip("end_label:N", title="End"),
                alt.Tooltip("duration_min:Q", title="Duration (min)"),
            ],
        )
        .properties(height=max(180, 80 + 56 * gantt_df["display_name"].nunique()))
    )
    st.altair_chart(chart.configure_view(stroke="#CBD5E1"), use_container_width=True)

    if dropped_df.empty:
        st.caption("All orders are scheduled in the current production run.")
    else:
        dropped_list = ", ".join(dropped_df["bo_id"].astype(str).tolist())
        st.caption(f"Unscheduled orders: {dropped_list}")


def _render_workforce_demo_panel(manpower_result: dict[str, Any] | None) -> None:
    st.markdown("**Workforce Overview**")
    if manpower_result is None:
        st.info("Run the workforce plan to view staffing coverage.")
        return

    solver_summary = manpower_result["solver_summary"]
    coverage_df = manpower_result["coverage_table_df"].copy()
    assignments_df = manpower_result["assignments_df"].copy()
    shortage_qty = int(solver_summary.get("total_shortage_qty", 0) or 0)
    workforce_cost = int(solver_summary.get("total_manpower_cost", 0) or 0)
    active_employees = int(assignments_df["employee_id"].nunique()) if not assignments_df.empty else 0

    work_cols = st.columns(4)
    work_cols[0].metric("Run Status", str(solver_summary.get("status", "UNKNOWN")))
    work_cols[1].metric("Unfilled Need", str(shortage_qty))
    work_cols[2].metric("Active Employees", str(active_employees))
    work_cols[3].metric("Workforce Cost", f"{workforce_cost:,}")

    if coverage_df.empty:
        st.info("No staffing coverage rows are available yet.")
        return

    summary_df = (
        coverage_df.groupby(["day", "shift_name"], as_index=False)
        .agg(
            required_qty=("required_qty", "sum"),
            assigned_qty=("assigned_qty", "sum"),
            shortage_qty=("shortage_qty", "sum"),
        )
    )
    summary_df["coverage_label"] = summary_df.apply(
        lambda row: f"{int(row['assigned_qty'])}/{int(row['required_qty'])}",
        axis=1,
    )
    chart_base = alt.Chart(summary_df).encode(
        y=alt.Y("shift_name:N", title="Shift", sort=summary_df["shift_name"].tolist()),
        tooltip=[
            alt.Tooltip("day:N", title="Day"),
            alt.Tooltip("shift_name:N", title="Shift"),
            alt.Tooltip("required_qty:Q", title="Required"),
            alt.Tooltip("assigned_qty:Q", title="Assigned"),
            alt.Tooltip("shortage_qty:Q", title="Unfilled"),
        ],
    )
    required_bars = chart_base.mark_bar(color="#DBEAFE", size=26).encode(
        x=alt.X("required_qty:Q", title="Workers"),
    )
    assigned_bars = chart_base.mark_bar(color="#1D4ED8", size=16).encode(
        x=alt.X("assigned_qty:Q"),
    )
    labels = chart_base.mark_text(align="left", dx=6, color="#0F172A", fontWeight="bold").encode(
        x=alt.X("required_qty:Q"),
        text="coverage_label:N",
    )
    chart = alt.layer(required_bars, assigned_bars, labels).properties(height=max(170, 52 * len(summary_df)))
    st.altair_chart(chart.configure_view(stroke="#CBD5E1"), use_container_width=True)

    compact_table = _friendly_dataframe(
        coverage_df[
            ["day", "shift_name", "line_id", "competency", "required_qty", "assigned_qty", "shortage_qty", "coverage_pct"]
        ].copy()
    )
    st.dataframe(compact_table, use_container_width=True, hide_index=True)


def _day_label_from_minute(total_minutes: int) -> str:
    day_index = max(0, int(total_minutes) // 1440)
    return DAY_ORDER[min(day_index, len(DAY_ORDER) - 1)]


def _clock_label_from_minute(total_minutes: int) -> str:
    minute_of_day = int(total_minutes) % 1440
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _build_operational_board_df(schedule_df: pd.DataFrame, shifts_df: pd.DataFrame | None = None) -> pd.DataFrame:
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame()
    shift_segments_df = _build_shift_segment_df(shifts_df if shifts_df is not None else pd.DataFrame())
    rows: list[dict[str, Any]] = []
    for rec in schedule_df.to_dict("records"):
        start_min = int(rec["start_min"])
        end_min = int(rec["end_min"])
        calendar_start_min = _compressed_minute_to_calendar_minute(start_min, shift_segments_df, is_end=False)
        calendar_end_min = _compressed_minute_to_calendar_minute(end_min, shift_segments_df, is_end=True)
        if not shift_segments_df.empty:
            for _, shift_row in shift_segments_df.iterrows():
                overlap_start = max(start_min, int(shift_row["compressed_start_min"]))
                overlap_end = min(end_min, int(shift_row["compressed_end_min"]))
                if overlap_start >= overlap_end:
                    continue
                actual_start = _compressed_minute_to_calendar_minute(overlap_start, shift_segments_df, is_end=False)
                actual_end = _compressed_minute_to_calendar_minute(overlap_end, shift_segments_df, is_end=True)
                rows.append(
                    {
                        "bo_id": str(rec["bo_id"]),
                        "display_name": str(rec["display_name"]),
                        "line_id": str(rec["line_id"]),
                        "product_code": str(rec["product_code"]),
                        "customer_name": str(rec.get("customer_name", "")),
                        "sequence": int(rec.get("sequence", 0)),
                        "day": str(shift_row["day"]),
                        "day_start_min": (actual_start // 1440) * 1440,
                        "start_clock_min": actual_start % 1440,
                        "end_clock_min": actual_end % 1440,
                        "start_label": _clock_label_from_minute(actual_start),
                        "end_label": _clock_label_from_minute(actual_end),
                        "calendar_start_label": _calendar_minute_label(calendar_start_min),
                        "calendar_end_label": _calendar_minute_label(calendar_end_min),
                        "duration_min": int(overlap_end - overlap_start),
                        "setup_time_min": int(rec.get("setup_time_min", 0)),
                        "setup_cost": int(rec.get("setup_cost", 0)),
                        "changeover_from_prev_min": int(rec.get("changeover_from_prev_min", 0)),
                        "changeover_from_prev_cost": int(rec.get("changeover_from_prev_cost", 0)),
                        "line_preference_penalty": int(rec.get("line_preference_penalty", 0)),
                        "demand_qty": int(rec.get("demand_qty", 0)),
                        "is_first_on_line": bool(rec.get("is_first_on_line", False)),
                    }
                )
        else:
            rows.append(
                {
                    "bo_id": str(rec["bo_id"]),
                    "display_name": str(rec["display_name"]),
                    "line_id": str(rec["line_id"]),
                    "product_code": str(rec["product_code"]),
                    "customer_name": str(rec.get("customer_name", "")),
                    "sequence": int(rec.get("sequence", 0)),
                    "day": _day_label_from_minute(start_min),
                    "day_start_min": (start_min // 1440) * 1440,
                    "start_clock_min": start_min % 1440,
                    "end_clock_min": end_min % 1440,
                    "start_label": _clock_label_from_minute(start_min),
                    "end_label": _clock_label_from_minute(end_min),
                    "calendar_start_label": _calendar_minute_label(start_min),
                    "calendar_end_label": _calendar_minute_label(end_min),
                    "duration_min": int(end_min - start_min),
                    "setup_time_min": int(rec.get("setup_time_min", 0)),
                    "setup_cost": int(rec.get("setup_cost", 0)),
                    "changeover_from_prev_min": int(rec.get("changeover_from_prev_min", 0)),
                    "changeover_from_prev_cost": int(rec.get("changeover_from_prev_cost", 0)),
                    "line_preference_penalty": int(rec.get("line_preference_penalty", 0)),
                    "demand_qty": int(rec.get("demand_qty", 0)),
                    "is_first_on_line": bool(rec.get("is_first_on_line", False)),
                }
            )
    board_df = pd.DataFrame(rows)
    board_df["board_label"] = board_df.apply(
        lambda row: f"{row['bo_id']} | {row['product_code']}",
        axis=1,
    )
    return board_df.sort_values(["day_start_min", "display_name", "start_clock_min", "bo_id"]).reset_index(drop=True)


def _build_shift_window_df(shifts_df: pd.DataFrame) -> pd.DataFrame:
    if shifts_df is None or shifts_df.empty:
        return pd.DataFrame()
    shift_df = shifts_df.copy()
    shift_df["day"] = shift_df["day"].astype(str)
    shift_df["shift_name"] = shift_df["shift_name"].astype(str)
    shift_df["start_clock_min"] = shift_df["start_min"].astype(int) % 1440
    shift_df["end_clock_min"] = shift_df["end_min"].astype(int) % 1440
    shift_df["shift_label"] = shift_df.apply(
        lambda row: f"{row['shift_name']} ({_clock_label_from_minute(int(row['start_min']))}-{_clock_label_from_minute(int(row['end_min']))})",
        axis=1,
    )
    return shift_df[["day", "shift_name", "start_clock_min", "end_clock_min", "shift_label"]].sort_values(
        ["day", "start_clock_min"]
    ).reset_index(drop=True)


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


def _calendar_minute_label(total_minutes: int) -> str:
    day_index = max(0, int(total_minutes) // 1440)
    day_name = DAY_ORDER[min(day_index, len(DAY_ORDER) - 1)]
    minute_of_day = int(total_minutes) % 1440
    return f"{day_name} {minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def _apply_calendar_labels_to_schedule_df(
    schedule_df: pd.DataFrame,
    shifts_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame() if schedule_df is None else schedule_df.copy()
    labeled_df = schedule_df.copy()
    shift_segments_df = _build_shift_segment_df(shifts_df if shifts_df is not None else pd.DataFrame())
    if shift_segments_df.empty:
        return labeled_df
    labeled_df["start_label"] = labeled_df["start_min"].apply(
        lambda value: _calendar_minute_label(
            _compressed_minute_to_calendar_minute(int(value), shift_segments_df, is_end=False)
        )
    )
    labeled_df["end_label"] = labeled_df["end_min"].apply(
        lambda value: _calendar_minute_label(
            _compressed_minute_to_calendar_minute(int(value), shift_segments_df, is_end=True)
        )
    )
    return labeled_df


def _build_staffing_board_df(
    assignments_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
) -> pd.DataFrame:
    if coverage_df is None or coverage_df.empty:
        return pd.DataFrame()
    coverage = coverage_df.copy()
    coverage["day"] = coverage["day"].astype(str)
    coverage["shift_name"] = coverage["shift_name"].astype(str)
    coverage["line_id"] = coverage["line_id"].astype(str)
    coverage["competency"] = coverage["competency"].astype(str)
    coverage["required_qty"] = pd.to_numeric(coverage["required_qty"], errors="coerce").fillna(0).astype(int)
    coverage["assigned_qty"] = pd.to_numeric(coverage["assigned_qty"], errors="coerce").fillna(0).astype(int)
    coverage["shortage_qty"] = pd.to_numeric(coverage["shortage_qty"], errors="coerce").fillna(0).astype(int)

    if assignments_df is None or assignments_df.empty:
        coverage["people_label"] = "No assignment"
        coverage["staffing_status"] = coverage["shortage_qty"].apply(lambda v: "Shortage" if v > 0 else "Covered")
        coverage["coverage_label"] = coverage.apply(
            lambda row: f"{row['assigned_qty']}/{row['required_qty']}",
            axis=1,
        )
        return coverage

    assignments = assignments_df.copy()
    assignments["day"] = assignments["day"].astype(str)
    assignments["shift_name"] = assignments["shift_name"].astype(str)
    assignments["line_id"] = assignments["line_id"].astype(str)
    assignments["competency"] = assignments["competency"].astype(str)
    people_df = (
        assignments.groupby(["day", "shift_name", "line_id", "competency"], as_index=False)
        .agg(people_label=("employee_name", lambda vals: ", ".join(sorted(str(v) for v in vals if str(v).strip()))))
    )
    board_df = coverage.merge(
        people_df,
        on=["day", "shift_name", "line_id", "competency"],
        how="left",
    )
    board_df["people_label"] = board_df["people_label"].fillna("No assignment")
    board_df["staffing_status"] = board_df["shortage_qty"].apply(lambda v: "Shortage" if v > 0 else "Covered")
    board_df["coverage_label"] = board_df.apply(
        lambda row: f"{row['assigned_qty']}/{row['required_qty']}",
        axis=1,
    )
    return board_df


def _build_staffing_gantt_df(
    assignments_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    shifts_df: pd.DataFrame | None,
) -> pd.DataFrame:
    board_df = _build_staffing_board_df(assignments_df, coverage_df)
    if board_df.empty or shifts_df is None or shifts_df.empty:
        return pd.DataFrame()
    shift_window_df = _build_shift_window_df(shifts_df)
    gantt_df = board_df.merge(
        shift_window_df[["day", "shift_name", "start_clock_min", "end_clock_min"]],
        on=["day", "shift_name"],
        how="left",
    )
    gantt_df["staffing_bar_label"] = gantt_df.apply(
        lambda row: f"{row['coverage_label']} | {row['people_label']}",
        axis=1,
    )
    return gantt_df


def _render_detail_card(title: str, subtitle: str, fields: list[tuple[str, str]]) -> None:
    field_html = "".join(
        f"""
        <div class="detail-kv">
            <div class="detail-kv-label">{label}</div>
            <div class="detail-kv-value">{value}</div>
        </div>
        """
        for label, value in fields
    )
    st.markdown(
        f"""
        <div class="detail-card">
            <div class="detail-title">{title}</div>
            <div class="detail-subtitle">{subtitle}</div>
            <div class="detail-kv-grid">{field_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_operational_view(
    machine_result: dict[str, Any] | None,
    manpower_result: dict[str, Any] | None,
    shifts_df: pd.DataFrame | None = None,
) -> None:
    st.markdown("**Machine Overview**")
    if machine_result is None or machine_result["schedule_df"].empty:
        st.info("Run the production plan to view the operational scheduling board.")
        return

    schedule_df = machine_result["schedule_df"].copy()
    capacity_df = machine_result["line_summary_df"].copy()
    board_df = _build_operational_board_df(schedule_df, shifts_df)
    shift_segments_df = _build_shift_segment_df(shifts_df if shifts_df is not None else pd.DataFrame())
    shift_window_df = _build_shift_window_df(shifts_df if shifts_df is not None else pd.DataFrame())
    selection_options = schedule_df["bo_id"].astype(str).tolist()
    if not selection_options:
        st.info("No scheduled orders are available for the operational board.")
        return

    selected_bo = st.selectbox(
        "Selected BO",
        selection_options,
        format_func=lambda bo_id: (
            f"{bo_id} | "
            f"{schedule_df.loc[schedule_df['bo_id'].astype(str) == bo_id, 'product_code'].iloc[0]} | "
            f"{schedule_df.loc[schedule_df['bo_id'].astype(str) == bo_id, 'display_name'].iloc[0]}"
        ),
        key="results_selected_bo",
    )

    board_df["selection_state"] = board_df["bo_id"].astype(str).apply(
        lambda bo_id: "Selected BO" if bo_id == selected_bo else "Other Orders"
    )
    selected_row = schedule_df[schedule_df["bo_id"].astype(str) == selected_bo].iloc[0]
    selected_line = str(selected_row["line_id"])
    line_summary = capacity_df[capacity_df["line_id"].astype(str) == selected_line]
    line_summary_row = line_summary.iloc[0] if not line_summary.empty else None

    board_cols = st.columns([2.9, 1.3])
    with board_cols[0]:
        st.caption(
            "Weekly line board inspired by the operational planner. Select a BO to highlight it on the board and open its detail context on the right."
        )
        if not shift_window_df.empty:
            shift_summary = " | ".join(shift_window_df["shift_label"].drop_duplicates().tolist())
            # st.markdown(
            #     f'<div class="compact-note" style="margin-bottom:0.35rem;">Shift windows: {shift_summary}</div>',
            #     unsafe_allow_html=True,
            # )
        shift_axis_values = (
            sorted(
                {
                    *shift_window_df["start_clock_min"].astype(int).tolist(),
                    *shift_window_df["end_clock_min"].astype(int).tolist(),
                }
            )
            if not shift_window_df.empty
            else [360, 840, 1320]
        )
        shift_domain = (
            [
                int(shift_window_df["start_clock_min"].min()),
                int(shift_window_df["end_clock_min"].max()),
            ]
            if not shift_window_df.empty
            else [360, 1320]
        )
        base = alt.Chart(board_df).encode(
            x=alt.X(
                "start_clock_min:Q",
                title="Time of Day",
                scale=alt.Scale(domain=shift_domain, clamp=True),
                axis=alt.Axis(
                    values=shift_axis_values,
                    labelExpr="floor(datum.value / 60) % 24 < 10 ? '0' + floor(datum.value / 60) % 24 + ':' + (datum.value % 60 === 0 ? '00' : datum.value % 60) : floor(datum.value / 60) % 24 + ':' + (datum.value % 60 === 0 ? '00' : datum.value % 60)",
                    labelColor="#374151",
                    titleColor="#374151",
                    labelFontSize=12,
                    titleFontSize=13,
                ),
            ),
            x2="end_clock_min:Q",
            y=alt.Y(
                "display_name:N",
                title="Production Line",
                sort=list(board_df["display_name"].drop_duplicates()),
                axis=alt.Axis(labelColor="#374151", titleColor="#374151", labelFontSize=12, titleFontSize=13),
            ),
            tooltip=[
                alt.Tooltip("bo_id:N", title="BO"),
                alt.Tooltip("product_code:N", title="Product"),
                alt.Tooltip("display_name:N", title="Line"),
                alt.Tooltip("calendar_start_label:N", title="Start"),
                alt.Tooltip("calendar_end_label:N", title="End"),
                alt.Tooltip("duration_min:Q", title="Duration (min)"),
            ],
        )
        bars = base.mark_bar(cornerRadiusEnd=4, height=24, stroke="#E2E8F0", strokeWidth=1).encode(
            color=alt.Color(
                "selection_state:N",
                scale=alt.Scale(domain=["Selected BO", "Other Orders"], range=["#0F766E", "#60A5FA"]),
                legend=None,
            ),
            opacity=alt.condition(alt.datum.selection_state == "Selected BO", alt.value(1.0), alt.value(0.78)),
        )
        labels = base.mark_text(fontSize=7, color="#FFFFFF", fontWeight="bold", align="left", dx=3).encode(
            text="board_label:N"
        )
        layered_board = alt.layer(bars, labels, data=board_df).properties(
            height=max(220, 62 * board_df["display_name"].nunique()),
            width=195,
        )
        board_chart = layered_board.facet(
            column=alt.Column(
                "day:N",
                sort=DAY_ORDER,
                title=None,
                header=alt.Header(labelColor="#1E3A8A", labelFontSize=13, labelFontWeight="bold"),
            )
        )
        st.altair_chart(board_chart.configure_view(stroke="#CBD5E1"), use_container_width=True)

    with board_cols[1]:
        detail_fields = [
            ("Line", str(selected_row["display_name"])),
            ("Product", str(selected_row["product_code"])),
            ("BO", str(selected_row["bo_id"])),
            ("Customer", str(selected_row.get("customer_name", "-"))),
            ("Start", _calendar_minute_label(_compressed_minute_to_calendar_minute(int(selected_row["start_min"]), shift_segments_df, is_end=False))),
            ("End", _calendar_minute_label(_compressed_minute_to_calendar_minute(int(selected_row["end_min"]), shift_segments_df, is_end=True))),
            ("Duration", f"{int(selected_row['duration_min'])} min"),
            ("Demand Qty", f"{int(selected_row.get('demand_qty', 0))}"),
        ]
        _render_detail_card("Order Detail", "Operational block detail inspired by the live planner", detail_fields)

        planning_fields = [
            ("Setup", f"{int(selected_row.get('setup_time_min', 0))} min"),
            ("Changeover", f"{int(selected_row.get('changeover_from_prev_min', 0))} min"),
            ("Setup Cost", f"{int(selected_row.get('setup_cost', 0)):,}"),
            ("Switch Cost", f"{int(selected_row.get('changeover_from_prev_cost', 0)):,}"),
            ("Sequence", str(int(selected_row.get("sequence", 0)))),
            ("First On Line", "Yes" if bool(selected_row.get("is_first_on_line", False)) else "No"),
            ("Line Pref Penalty", str(int(selected_row.get("line_preference_penalty", 0)))),
            ("Utilization", f"{float(line_summary_row['utilization_pct']):.1f}%" if line_summary_row is not None else "-"),
        ]
        _render_detail_card("Planning Metrics", "Line and order planning context", planning_fields)

        st.markdown("**Supporting Detail**")
        if manpower_result is not None and not manpower_result["assignments_df"].empty:
            assignments_df = manpower_result["assignments_df"].copy()
            assignments_df["source_match"] = assignments_df["source_bo_ids_json"].apply(lambda raw: selected_bo in json.loads(raw) if raw else False)
            bo_assignments = assignments_df[assignments_df["source_match"]].copy()
            if not bo_assignments.empty:
                support_df = _friendly_dataframe(
                    bo_assignments[["shift_name", "employee_name", "competency", "skill_score"]].copy()
                )
                st.dataframe(support_df, use_container_width=True, hide_index=True)
            else:
                st.caption("No workforce assignments are tied directly to this BO in the current staffing result.")
        else:
            st.caption("Workforce detail appears here after the workforce plan is run.")


def _render_operational_manpower_view(
    manpower_result: dict[str, Any] | None,
    shifts_df: pd.DataFrame | None = None,
) -> None:
    if manpower_result is None:
        st.info("Run the workforce plan to view line and shift staffing.")
        return

    st.markdown("**Workforce Overview**")
    coverage_df = manpower_result["coverage_table_df"].copy()
    assignments_df = manpower_result["assignments_df"].copy()
    solver_summary = manpower_result["solver_summary"]
    shortage_qty = int(solver_summary.get("total_shortage_qty", 0) or 0)
    employee_options = sorted(assignments_df["employee_name"].astype(str).unique().tolist()) if not assignments_df.empty else []
    selected_employees = st.multiselect(
        "Filter manpower by employee name",
        employee_options,
        placeholder="All assigned employees",
        key="results_manpower_employee_filter",
    )
    filtered_assignments_df = (
        assignments_df[assignments_df["employee_name"].astype(str).isin(selected_employees)].copy()
        if selected_employees
        else assignments_df
    )

    gantt_df = _build_staffing_gantt_df(filtered_assignments_df, coverage_df, shifts_df)
    if gantt_df.empty:
        st.info("No staffing coverage rows are available yet.")
        return

    line_order = gantt_df["line_id"].drop_duplicates().tolist()
    shift_order = (
        gantt_df[["shift_name"]]
        .drop_duplicates()
        .assign(_sort_key=lambda df: df["shift_name"].map(_natural_shift_sort_key))
        .sort_values("_sort_key")["shift_name"]
        .tolist()
    )
    shift_window_df = _build_shift_window_df(shifts_df if shifts_df is not None else pd.DataFrame())
    shift_axis_values = (
        sorted(
            {
                *shift_window_df["start_clock_min"].astype(int).tolist(),
                *shift_window_df["end_clock_min"].astype(int).tolist(),
            }
        )
        if not shift_window_df.empty
        else [360, 840, 1320]
    )
    shift_domain = (
        [
            int(shift_window_df["start_clock_min"].min()),
            int(shift_window_df["end_clock_min"].max()),
        ]
        if not shift_window_df.empty
        else [360, 1320]
    )
    base = alt.Chart(gantt_df).encode(
        x=alt.X(
            "start_clock_min:Q",
            title="Shift Window",
            scale=alt.Scale(domain=shift_domain),
            axis=alt.Axis(
                values=shift_axis_values,
                labelExpr="floor(datum.value / 60) % 24 < 10 ? '0' + floor(datum.value / 60) % 24 + ':' + (datum.value % 60 === 0 ? '00' : datum.value % 60) : floor(datum.value / 60) % 24 + ':' + (datum.value % 60 === 0 ? '00' : datum.value % 60)",
                labelColor="#374151",
                titleColor="#374151",
                labelFontSize=12,
                titleFontSize=13,
            ),
        ),
        x2="end_clock_min:Q",
        y=alt.Y(
            "line_id:N",
            title="Line",
            sort=line_order,
            axis=alt.Axis(labelColor="#374151", titleColor="#374151", labelFontSize=12, titleFontSize=13),
        ),
        tooltip=[
            alt.Tooltip("day:N", title="Day"),
            alt.Tooltip("shift_name:N", title="Shift"),
            alt.Tooltip("line_id:N", title="Line"),
            alt.Tooltip("competency:N", title="Skill"),
            alt.Tooltip("assigned_qty:Q", title="Assigned"),
            alt.Tooltip("required_qty:Q", title="Required"),
            alt.Tooltip("shortage_qty:Q", title="Shortage"),
            alt.Tooltip("people_label:N", title="Assigned People"),
        ],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, height=42, stroke="#CBD5E1", strokeWidth=1).encode(
        color=alt.Color(
            "staffing_status:N",
            scale=alt.Scale(domain=["Covered", "Shortage"], range=["#DBEAFE", "#FECACA"]),
            legend=None,
        )
    )
    coverage_labels = base.mark_text(fontSize=12, fontWeight="bold", color="#0F172A", dy=-11).encode(
        text="coverage_label:N"
    )
    people_labels = base.mark_text(fontSize=11, color="#0F172A", dy=9).encode(
        text="people_label:N"
    )
    layered_chart = alt.layer(bars, coverage_labels, people_labels, data=gantt_df).properties(
        height=max(320, 104 * max(1, len(line_order))),
        width=300,
    )
    chart = layered_chart.facet(
        column=alt.Column(
            "day:N",
            sort=DAY_ORDER,
            title=None,
            header=alt.Header(labelColor="#1E3A8A", labelFontSize=13, labelFontWeight="bold"),
        )
    )
    st.altair_chart(chart.configure_view(stroke="#CBD5E1"), use_container_width=True)

    if selected_employees:
        st.caption(
            f"Showing assigned people for {len(selected_employees)} selected employee(s). Coverage totals remain based on the full workforce plan."
        )
    if shortage_qty <= 0:
        st.caption("All required line and shift staffing is covered in the current workforce plan.")


def _render_result_exceptions(
    machine_result: dict[str, Any] | None,
    manpower_result: dict[str, Any] | None,
) -> None:
    unscheduled_count = int(machine_result["solver_summary"].get("dropped_orders", 0)) if machine_result else 0
    shortage_qty = int(manpower_result["solver_summary"].get("total_shortage_qty", 0)) if manpower_result else 0

    exception_cols = st.columns(2)
    with exception_cols[0]:
        st.markdown("**Production Exceptions**")
        if unscheduled_count <= 0:
            st.caption("No unscheduled orders in the current production run.")
        else:
            dropped_df = machine_result["dropped_orders_df"].copy()
            show_cols = [col for col in ["bo_id", "product_code", "demand_qty", "duration_min"] if col in dropped_df.columns]
            exception_table = _friendly_dataframe(dropped_df[show_cols].copy())
            st.dataframe(exception_table, use_container_width=True, hide_index=True)

    with exception_cols[1]:
        st.markdown("**Staffing Exceptions**")
        if manpower_result is None or shortage_qty <= 0:
            st.caption("No unfilled staffing need in the current workforce plan.")
        else:
            shortage_df = manpower_result["shortage_heatmap_df"].copy()
            show_cols = [col for col in ["day", "shift_name", "line_id", "competency", "required_qty", "assigned_qty", "shortage_qty"] if col in shortage_df.columns]
            exception_table = _friendly_dataframe(shortage_df[show_cols].copy())
            st.dataframe(exception_table, use_container_width=True, hide_index=True)


def _render_input_workspace(scenario: dict[str, Any]) -> None:
    input_tabs = st.tabs([cfg["label"] for cfg in TABLE_CONFIGS])
    for tab, cfg in zip(input_tabs, TABLE_CONFIGS):
        filename = cfg["filename"]
        scenario_key = cfg["scenario_key"]
        normalized_df = scenario[scenario_key]
        with tab:
            inner_tabs = st.tabs(["Visual", "Table"])
            with inner_tabs[0]:
                _render_input_visual(scenario_key, normalized_df)
            with inner_tabs[1]:
                _show_table(normalized_df)


def _render_machine_result_ui(
    machine_result: dict[str, Any],
    shifts_df: pd.DataFrame | None = None,
) -> None:
    solver_summary = machine_result["solver_summary"]
    kpis_df = machine_result["kpis_df"]
    cost_breakdown_df = machine_result["cost_breakdown_df"]
    schedule_df = _apply_calendar_labels_to_schedule_df(machine_result["schedule_df"], shifts_df)
    gantt_df = _apply_calendar_labels_to_schedule_df(machine_result["gantt_df"], shifts_df)
    capacity_df = machine_result["capacity_chart_df"]
    dropped_df = machine_result["dropped_orders_df"]

    kpi_cols = st.columns(6)
    kpi_cols[0].metric(
        "Run Status",
        _get_kpi_display_value(kpis_df, "solver_status", str(solver_summary.get("status", "UNKNOWN"))),
    )
    objective_fallback = "0"
    if solver_summary.get("objective_value") is not None:
        objective_fallback = f"{float(solver_summary.get('objective_value')):.0f}"
    kpi_cols[1].metric(
        "Planning Score",
        _get_kpi_display_value(kpis_df, "objective_value", objective_fallback),
    )
    kpi_cols[2].metric(
        "Unscheduled Orders",
        _get_kpi_display_value(kpis_df, "dropped_orders", str(int(solver_summary.get("dropped_orders", 0)))),
    )
    kpi_cols[3].metric("Setup Cost", str(int(solver_summary.get("total_setup_cost", 0))))
    kpi_cols[4].metric("Switch Cost", str(int(solver_summary.get("total_changeover_cost", 0))))
    kpi_cols[5].metric(
        "Total Production Cost",
        _get_kpi_display_value(
            kpis_df,
            "total_machine_cost",
            str(int(solver_summary.get("total_machine_cost", 0))),
        ),
    )

    st.caption(
        "Production cost is shown separately from technical run details. Orders are left unscheduled only when the optimizer "
        "cannot fit every order across available lines without violating available time and sequencing constraints."
    )

    overview_tabs = st.tabs([
        "Plan Table",
        "Timeline View",
        "Line Usage",
        "Unscheduled Orders",
        "Cost Summary",
        "Technical Details",
    ])

    with overview_tabs[0]:
        _show_table(schedule_df)

    with overview_tabs[1]:
        if gantt_df.empty:
            st.info("No scheduled orders are available for the timeline view.")
        else:
            gantt_chart = (
                alt.Chart(gantt_df)
                .mark_bar(size=28)
                .encode(
                    x=alt.X("start_min:Q", title="Minutes From Week Start"),
                    x2="end_min:Q",
                    y=alt.Y("display_name:N", title="Line", sort=list(gantt_df["display_name"].drop_duplicates())),
                    color=alt.Color("product_code:N", title="Product"),
                    tooltip=[
                        alt.Tooltip("display_name:N", title="Line"),
                        alt.Tooltip("bo_id:N", title="Order"),
                        alt.Tooltip("product_code:N", title="Product"),
                        alt.Tooltip("sequence:Q", title="Sequence"),
                        alt.Tooltip("start_label:N", title="Start"),
                        alt.Tooltip("end_label:N", title="End"),
                        alt.Tooltip("duration_min:Q", title="Duration Min"),
                        alt.Tooltip("setup_time_min:Q", title="Setup Min"),
                        alt.Tooltip("changeover_from_prev_min:Q", title="Switch Time (min)"),
                    ],
                )
                .properties(height=max(180, 80 + 60 * gantt_df["display_name"].nunique()))
            )
            st.altair_chart(gantt_chart, use_container_width=True)

    with overview_tabs[2]:
        if capacity_df.empty:
            st.info("No line usage data is available yet.")
        else:
            capacity_long_df = capacity_df.melt(
                id_vars=["display_name", "utilization_pct", "assigned_order_count", "capacity_min"],
                value_vars=["used_min", "remaining_min"],
                var_name="capacity_component",
                value_name="minutes",
            )
            capacity_long_df["capacity_component"] = capacity_long_df["capacity_component"].map({
                "used_min": "Used Time",
                "remaining_min": "Remaining Time",
            })
            capacity_chart = (
                alt.Chart(capacity_long_df)
                .mark_bar(size=36)
                .encode(
                    x=alt.X("minutes:Q", title="Minutes", stack=True),
                    y=alt.Y("display_name:N", title="Line", sort=list(capacity_df["display_name"])),
                    color=alt.Color("capacity_component:N", title="Line Usage"),
                    order=alt.Order("capacity_component:N", sort="ascending"),
                    tooltip=[
                        alt.Tooltip("display_name:N", title="Line"),
                        alt.Tooltip("capacity_component:N", title="Type"),
                        alt.Tooltip("minutes:Q", title="Minutes"),
                        alt.Tooltip("capacity_min:Q", title="Line Time"),
                        alt.Tooltip("utilization_pct:Q", title="Used %"),
                        alt.Tooltip("assigned_order_count:Q", title="Assigned Orders"),
                    ],
                )
                .properties(height=max(180, 80 + 60 * capacity_df["display_name"].nunique()))
            )
            st.altair_chart(capacity_chart, use_container_width=True)
            _show_table(capacity_df)

    with overview_tabs[3]:
        if dropped_df.empty:
            st.success("No orders were left unscheduled in this machine run.")
        else:
            st.warning(
                "Unscheduled orders indicate limited available time or a sequencing tradeoff across the available lines."
            )
            _show_table(dropped_df)

    with overview_tabs[4]:
        _show_table(cost_breakdown_df)

    with overview_tabs[5]:
        _render_kpi_cards(kpis_df, "diagnostic", columns=3)
        diagnostics_df = pd.DataFrame(
            [
                {"metric": "Drop Penalty Units", "value": int(solver_summary.get("drop_penalty_units", 0))},
                {"metric": "Total Setup Min", "value": int(solver_summary.get("total_setup_min", 0))},
                {"metric": "Total Switch Min", "value": int(solver_summary.get("total_changeover_min", 0))},
                {"metric": "Total Processing Min", "value": int(solver_summary.get("total_processing_min", 0))},
                {"metric": "Time Limit Sec", "value": float(solver_summary.get("time_limit_sec", 0))},
                {"metric": "Random Seed", "value": int(solver_summary.get("random_seed", 0))},
            ]
        )
        _show_table(diagnostics_df)


def _render_demand_ui(demand_df: pd.DataFrame) -> None:
    if demand_df.empty:
        st.info("No workforce demand was generated from the current production plan.")
        return

    demand_view_df = demand_df.copy()
    demand_view_df["source_bo_list"] = demand_view_df["source_bo_ids_json"].apply(
        lambda raw: ", ".join(json.loads(raw)) if raw else ""
    )
    demand_view_df["why_workers_needed"] = demand_view_df.apply(
        lambda row: (
            f"{row['line_id']} {row['shift_name']} on {row['day']} is active because orders {row['source_bo_list']} "
            f"overlap the shift, so {row['required_qty']} {row['competency']} worker(s) are needed."
        ),
        axis=1,
    )

    summary_cols = st.columns(4)
    summary_cols[0].metric("Demand Rows", int(len(demand_view_df)))
    summary_cols[1].metric("Workers Needed", int(demand_view_df["required_qty"].sum()))
    summary_cols[2].metric("Active Lines", int(demand_view_df["line_id"].nunique()))
    summary_cols[3].metric("Triggered Orders", int(demand_view_df["source_bo_count"].sum()))

    st.caption(
        "This simplified step turns the production plan into workforce demand. A demand row appears only when an order "
        "scheduled on a line overlaps a shift, and the row keeps the source order trace so you can see why workers are needed."
    )

    demand_tabs = st.tabs(["Demand Table", "Why Workers Are Needed"])
    with demand_tabs[0]:
        _show_table(demand_view_df)
    with demand_tabs[1]:
        explanation_df = demand_view_df[[
            "day",
            "shift_id",
            "shift_name",
            "line_id",
            "competency",
            "required_qty",
            "source_bo_count",
            "source_bo_list",
            "why_workers_needed",
        ]]
        _show_table(explanation_df)


def _render_manpower_result_ui(manpower_result: dict[str, Any]) -> None:
    solver_summary = manpower_result["solver_summary"]
    kpis_df = manpower_result["kpis_df"]
    cost_breakdown_df = manpower_result["cost_breakdown_df"]
    coverage_df = manpower_result["coverage_table_df"].copy()
    assignments_df = manpower_result["assignments_df"].copy()
    shortage_df = manpower_result["shortage_heatmap_df"].copy()
    employee_schedule_df = manpower_result["employee_schedule_df"].copy()

    active_employees = int(assignments_df["employee_id"].nunique()) if not assignments_df.empty else 0
    objective_fallback = "0"
    if solver_summary.get("objective_value") is not None:
        objective_fallback = f"{float(solver_summary.get('objective_value')):.0f}"

    kpi_cols = st.columns(6)
    kpi_cols[0].metric(
        "Run Status",
        _get_kpi_display_value(kpis_df, "solver_status", str(solver_summary.get("status", "UNKNOWN"))),
    )
    kpi_cols[1].metric(
        "Planning Score",
        _get_kpi_display_value(kpis_df, "objective_value", objective_fallback),
    )
    kpi_cols[2].metric(
        "Unfilled Need",
        _get_kpi_display_value(kpis_df, "total_shortage_qty", str(int(solver_summary.get("total_shortage_qty", 0)))),
    )
    kpi_cols[3].metric("Shift Cost", str(int(solver_summary.get("total_shift_cost", 0))))
    kpi_cols[4].metric(
        "Total Workforce Cost",
        _get_kpi_display_value(
            kpis_df,
            "total_manpower_cost",
            str(int(solver_summary.get("total_manpower_cost", 0))),
        ),
    )
    kpi_cols[5].metric("Active Employees", str(active_employees))

    st.caption(
        "Unfilled rows represent demand that still remains after employees are assigned. "
        "Each row is tied back to the source orders so you can see which active line, shift, and skill requirement remains uncovered."
    )

    if not shortage_df.empty:
        shortage_df["source_bo_list"] = shortage_df["source_bo_ids_json"].apply(
            lambda raw: ", ".join(json.loads(raw)) if raw else ""
        )
        shortage_df["shortage_reason"] = shortage_df.apply(
            lambda row: (
                f"{row['line_id']} {row['shift_name']} on {row['day']} still needs {row['shortage_qty']} "
                f"more {row['competency']} worker(s) after assigning {row['assigned_qty']} of {row['required_qty']} needed. "
                f"Source orders: {row['source_bo_list']}."
            ),
            axis=1,
        )

    view_tabs = st.tabs([
        "Staffing Summary",
        "Unfilled Needs",
        "Assignments",
        "Employee Schedule",
        "Cost Summary",
        "Technical Details",
    ])

    with view_tabs[0]:
        _show_table(coverage_df)

    with view_tabs[1]:
        if shortage_df.empty:
            st.success("All active line and shift needs are fully staffed in this workforce plan.")
        else:
            st.warning("These are the exact line, shift, and skill needs that remain unfilled.")
            explanation_df = shortage_df[[
                "day",
                "shift_id",
                "shift_name",
                "line_id",
                "competency",
                "required_qty",
                "assigned_qty",
                "shortage_qty",
                "coverage_pct",
                "source_bo_list",
                "shortage_reason",
            ]]
            _show_table(explanation_df)

    with view_tabs[2]:
        _show_table(assignments_df)

    with view_tabs[3]:
        _show_table(employee_schedule_df)

    with view_tabs[4]:
        _show_table(cost_breakdown_df)

    with view_tabs[5]:
        _render_kpi_cards(kpis_df, "diagnostic", columns=4)
        diagnostics_df = pd.DataFrame(
            [
                {"metric": "Active Employee Shifts", "value": int(solver_summary.get("activated_employee_shifts", 0))},
                {"metric": "Assignments", "value": int(solver_summary.get("assignments_count", 0))},
                {"metric": "Unfilled Rows", "value": int(solver_summary.get("shortage_rows", 0))},
                {"metric": "Total Skill Penalty", "value": int(solver_summary.get("total_skill_penalty", 0))},
                {"metric": "Time Limit Sec", "value": float(solver_summary.get("time_limit_sec", 0))},
                {"metric": "Random Seed", "value": int(solver_summary.get("random_seed", 0))},
            ]
        )
        _show_table(diagnostics_df)


_inject_app_css()
_render_hero()
_render_callout(
    "Simplified Demo Scope",
    "This version is intentionally simplified for stakeholder demonstrations. The business flow and optimization outcomes are preserved, while the interface focuses on clarity and presentation quality.",
    tone="info",
)

scenarios = _list_scenarios()
scenario_lookup = {item["name"]: item for item in scenarios}
scenario_names = list(scenario_lookup.keys())
if scenario_names and st.session_state.get("demo_selected_name") not in scenario_lookup:
    st.session_state["demo_selected_name"] = scenario_names[0]
selected_name = (
    st.selectbox(
        "Scenario",
        scenario_names,
        format_func=lambda name: scenario_lookup[name]["title"],
        key="demo_selected_name",
    )
    if scenario_names
    else None
)
selected_record = scenario_lookup.get(selected_name) if selected_name else None
selected_path = str(selected_record["path"]) if selected_record else None
scenario = _ensure_workspace(selected_record, selected_name)
raw_tables = st.session_state.get("workspace_raw_tables", {})
validation_errors = _validate_runtime_scenario(raw_tables) if raw_tables else ["No scenario selected."]

if st.session_state.get("reset_notice"):
    _render_callout("Data Reset Complete", str(st.session_state.pop("reset_notice")), tone="success")
if st.session_state.get("run_notice"):
    notice_tone, notice_title, notice_body = st.session_state.pop("run_notice")
    _render_callout(str(notice_title), str(notice_body), tone=str(notice_tone))

machine_result = st.session_state.get("workspace_machine_result")
manpower_result = st.session_state.get("workspace_manpower_result")
demand_df = st.session_state.get("workspace_demand_df")

step_options = [
    "1. Choose Data",
    "2. Review Inputs",
    "3. Run Planning",
    "4. Review Results",
    "5. Export",
]
current_step = st.radio(
    "Workflow",
    step_options,
    horizontal=True,
    label_visibility="collapsed",
)
step_labels = [
    ("1. Choose Data", "Load a demo-ready example"),
    ("2. Review Inputs", "Explain key master data"),
    ("3. Run Planning", "Execute planning scenarios"),
    ("4. Review Results", "Present business outcomes"),
    ("5. Export", "Download shareable outputs"),
]
step_html = "".join(
    f'<span class="step-badge {"step-badge-active" if label == current_step else ""}">{label}</span>'
    for label, _ in step_labels
)
st.markdown(f'<div class="stepper-row" style="margin:0.15rem 0 1rem 0;">{step_html}</div>', unsafe_allow_html=True)

if current_step == "1. Choose Data":
    _render_section_header(
        "Choose a Demo Scenario",
        "Start with one of the prepared example datasets.",
        eyebrow="Step 1",
    )
    if scenario is None:
        _render_callout("No Example Selected", "Select one of the example data sets to begin.", tone="warning")
    else:
        meta = scenario["meta"]
        _render_metric_cards(
            [
                {"label": "Selected Example", "value": str(meta.get("title", scenario["name"])), "icon": "📁", "note": str(meta.get("difficulty", "")).title()},
                {"label": "Orders", "value": str(int(len(scenario["machine_orders"]))), "icon": "🧾", "note": "Production demand in scope"},
                {"label": "Lines", "value": str(int(scenario["machine_lines"]["line_id"].nunique())), "icon": "🏭", "note": "Available production lines"},
                {"label": "Employees", "value": str(int(len(scenario["employees"]))), "icon": "👥", "note": "Available workforce pool"},
            ],
            columns=4,
        )
        st.caption(str(meta.get("description", "")))
        if validation_errors:
            _render_callout("Validation Needs Attention", "Planning is blocked until the input issues below are fixed.", tone="danger")
            for err in validation_errors:
                st.write(f"- {err}")

elif current_step == "2. Review Inputs":
    _render_section_header(
        "Review Input Data",
        eyebrow="Step 2",
    )
    if scenario is None:
        _render_callout("No Example Selected", "Select an example data set to review its input tables.", tone="warning")
    else:
        _render_metric_cards(
            [
                {"label": "Orders", "value": str(int(len(scenario["machine_orders"]))), "icon": "🧾", "note": "Demand included in the plan"},
                {"label": "Production Lines", "value": str(int(scenario["machine_lines"]["line_id"].nunique())), "icon": "🏭", "note": "Assets available for planning"},
                {"label": "Employees", "value": str(int(len(scenario["employees"]))), "icon": "👥", "note": "Workforce available for assignment"},
                {"label": "Shifts", "value": str(int(len(scenario["shifts"]))), "icon": "🕒", "note": "Work periods defined"},
                {"label": "Staffing Rows", "value": str(int(len(scenario["line_shift_requirements"]))), "icon": "📋", "note": "Line and skill requirements"},
            ],
            columns=5,
        )

        _render_input_workspace(scenario)

elif current_step == "3. Run Planning":
    _render_section_header(
        "Run Planning Scenarios",
        "Use the control panel below to execute the production plan first, then generate the workforce plan from the resulting schedule.",
        eyebrow="Step 3",
    )
    machine_cost = int(machine_result["solver_summary"].get("total_machine_cost", 0)) if machine_result else 0
    manpower_cost = int(manpower_result["solver_summary"].get("total_manpower_cost", 0)) if manpower_result else 0
    _render_metric_cards(
        [
            {"label": "Production Cost", "value": f"{machine_cost:,}", "icon": "🏭", "note": "Latest production run"},
            {"label": "Workforce Cost", "value": f"{manpower_cost:,}", "icon": "👥", "note": "Latest workforce run"},
            {"label": "Combined Cost", "value": f"{machine_cost + manpower_cost:,}", "icon": "💼", "note": "Current scenario total"},
        ],
        columns=3,
    )
    _render_status_pills(
        [
            ("Inputs validated" if not validation_errors else "Validation required", "good" if not validation_errors else "stop"),
            ("Production plan complete" if machine_result is not None else "Production plan pending", "good" if machine_result is not None else "ready"),
            ("Workforce plan complete" if manpower_result is not None else "Workforce plan pending", "good" if manpower_result is not None else "wait"),
        ]
    )
    control_cols = st.columns([1.2, 1.2, 1])
    run_machine_disabled = bool(validation_errors) or scenario is None
    with control_cols[0]:
        if st.button("Run Production Plan", disabled=run_machine_disabled, use_container_width=True, type="primary"):
            machine_result = _run_machine_for_scenario(scenario)
            demand_df = _build_demand_for_scenario(scenario, machine_result)
            st.session_state["workspace_machine_result"] = machine_result
            st.session_state["workspace_demand_df"] = demand_df
            st.session_state["workspace_manpower_result"] = None
            manpower_result = None
            st.session_state["run_notice"] = (
                "success",
                "Production Planning Complete",
                "The production plan and downstream workforce demand were generated successfully.",
            )
            st.rerun()
    run_manpower_disabled = bool(validation_errors) or machine_result is None or demand_df is None
    with control_cols[1]:
        if st.button("Run Workforce Plan", disabled=run_manpower_disabled, use_container_width=True, type="primary"):
            manpower_result = _run_manpower_for_scenario(scenario, demand_df)
            st.session_state["workspace_manpower_result"] = manpower_result
            st.session_state["run_notice"] = (
                "success",
                "Workforce Planning Complete",
                "The workforce plan was generated from the latest production schedule.",
            )
            st.rerun()
    with control_cols[2]:
        st.markdown(
            """
            <div class="ui-card" style="padding:0.95rem 1rem;">
                <div class="metric-label">Prerequisites</div>
                <div class="compact-note" style="margin-top:0.35rem;">
                    • Inputs must pass validation<br/>
                    • Workforce planning depends on the production plan
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if demand_df is None:
        _render_callout("Workforce Demand Pending", "Run the production plan first. Workforce demand is derived from the resulting production schedule.", tone="warning")

elif current_step == "4. Review Results":
    _render_section_header(
        "Review Planning Results",
        "The default view is designed for a fast business readout first, with detailed analysis kept available underneath.",
        eyebrow="Step 4",
    )
    total_combined_cost = (
        (int(machine_result["solver_summary"].get("total_machine_cost", 0)) if machine_result else 0)
        + (int(manpower_result["solver_summary"].get("total_manpower_cost", 0)) if manpower_result else 0)
    )
    executive_cards = [
        {"label": "Production Status", "value": str(machine_result["solver_summary"].get("status", "Not run")) if machine_result else "Not run", "icon": "🏭", "note": "Latest production run"},
        {"label": "Workforce Status", "value": str(manpower_result["solver_summary"].get("status", "Not run")) if manpower_result else "Not run", "icon": "👥", "note": "Latest workforce run"},
        {"label": "Combined Cost", "value": f"{(int(machine_result['solver_summary'].get('total_machine_cost', 0)) if machine_result else 0) + (int(manpower_result['solver_summary'].get('total_manpower_cost', 0)) if manpower_result else 0):,}", "icon": "💼", "note": "Current scenario total"},
        {"label": "Unfilled Need", "value": str(int(manpower_result["solver_summary"].get("total_shortage_qty", 0))) if manpower_result else "0", "icon": "⚠️", "note": "Only applies after workforce planning"},
    ]
    executive_cards = [
        {"label": "Overall Status", "value": _result_status_label(machine_result, manpower_result), "icon": "Status", "note": "Current planning outcome"},
        {"label": "Total Combined Cost", "value": f"{total_combined_cost:,}", "icon": "Cost", "note": "Production plus workforce cost"},
        {"label": "Unscheduled Orders", "value": str(int(machine_result["solver_summary"].get("dropped_orders", 0))) if machine_result else "0", "icon": "Orders", "note": "Orders not placed on a line"},
        {"label": "Unfilled Need", "value": str(int(manpower_result["solver_summary"].get("total_shortage_qty", 0))) if manpower_result else "0", "icon": "Staffing", "note": "Staffing still missing"},
    ]
    _render_metric_cards(executive_cards, columns=4)
    _render_results_takeaway(machine_result, manpower_result)
    _render_operational_view(
        machine_result,
        manpower_result,
        scenario["shifts"] if scenario is not None else None,
    )

    _render_operational_manpower_view(
        manpower_result,
        scenario["shifts"] if scenario is not None else None,
    )

    st.markdown("**Cost Overview**")
    _render_cost_overview_chart(machine_result, manpower_result)

    _render_result_exceptions(machine_result, manpower_result)

    st.caption(
        "Detailed production tables, staffing allocations, and solver diagnostics remain available in the technical sections below."
    )

    with st.expander("Show Detailed Production Review", expanded=False):
        if machine_result is None:
            _render_callout("Production Results Not Available", "Run the production plan to review schedule, line usage, and unscheduled orders.", tone="warning")
        else:
            _render_machine_result_ui(
                machine_result,
                scenario["shifts"] if scenario is not None else None,
            )

    with st.expander("Show Detailed Workforce Review", expanded=False):
        if manpower_result is None:
            _render_callout("Workforce Results Not Available", "Run the workforce plan to review staffing coverage and unfilled needs.", tone="warning")
        else:
            _render_manpower_result_ui(manpower_result)

elif current_step == "5. Export":
    _render_section_header(
        "Export Outputs",
        "Download the production plan, workforce outputs, or a complete bundle for follow-up discussions and documentation.",
        eyebrow="Step 5",
    )
    export_cols = st.columns(2)
    with export_cols[0]:
        if machine_result is None:
            _render_callout("Production Export Locked", "Run the production plan to enable production exports.", tone="warning")
        else:
            st.download_button(
                "Download Production Plan CSV",
                data=_df_to_csv_bytes(machine_result["schedule_df"]),
                file_name=f"{selected_name or 'example'}_production_plan.csv",
                mime="text/csv",
                use_container_width=True,
            )
    with export_cols[1]:
        if manpower_result is None:
            _render_callout("Workforce Export Locked", "Run the workforce plan to enable workforce exports.", tone="warning")
        else:
            st.download_button(
                "Download Workforce Assignments CSV",
                data=_df_to_csv_bytes(manpower_result["assignments_df"]),
                file_name=f"{selected_name or 'example'}_workforce_assignments.csv",
                mime="text/csv",
                use_container_width=True,
            )

    secondary_export_cols = st.columns(2)
    with secondary_export_cols[0]:
        if manpower_result is None:
            _render_callout("Unfilled Needs Export Locked", "The unfilled-needs export becomes available after the workforce plan runs.", tone="warning")
        else:
            st.download_button(
                "Download Unfilled Needs CSV",
                data=_df_to_csv_bytes(manpower_result["shortage_heatmap_df"]),
                file_name=f"{selected_name or 'example'}_unfilled_needs.csv",
                mime="text/csv",
                use_container_width=True,
            )
    with secondary_export_cols[1]:
        if machine_result is None and manpower_result is None:
            _render_callout("Export Bundle Locked", "Run one or both planning steps to enable the bundled export file.", tone="warning")
        else:
            st.download_button(
                "Download Export ZIP",
                data=_build_export_bundle(selected_name or "scenario", machine_result, demand_df, manpower_result),
                file_name=f"{selected_name or 'example'}_planning_outputs.zip",
                mime="application/zip",
                use_container_width=True,
            )

    reset_cols = st.columns([2, 1])
    with reset_cols[0]:
        st.markdown('<div class="compact-note">Reset restores the example data sets and clears the saved run results.</div>', unsafe_allow_html=True)
    with reset_cols[1]:
        if st.button("Reset Example Data", use_container_width=True):
            _reset_demo_state()
            st.session_state["workspace_signature"] = None
            _clear_workspace_run_results()
            st.rerun()
