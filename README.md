# Demo

## Purpose

This folder contains a self-contained demo of a simplified two-stage AVATAR planning workflow:

- machine scheduling
- manpower scheduling

The goal is to let someone run a small, deterministic planning story locally with bundled CSV scenarios, inspect tradeoffs in the UI, and understand how machine output turns into manpower demand.

## What Is Simplified Vs Production

This demo intentionally cuts scope relative to the production pipeline.

Included in demo v1:

- local CSV scenario inputs under `demo/data/`
- a Monday-Friday planning horizon
- machine scheduling in `minutes from week start`
- manpower planning in `whole shift buckets`
- a machine-to-manpower bridge based on `line x shift x competency`
- business-facing tables, charts, diagnostics, and browser downloads

Explicitly excluded from demo v1:

- BigQuery and SQL inputs
- production preprocessing pipeline reuse
- compressed timeline logic and compressed-to-real mapping
- atomic window slicing
- pinned assignments
- locked sequence or locked shift behavior
- overtime and weekend penalty logic
- full production reporting outputs
- manpower demand derived as `line x product x competency`

## Locked Assumptions

- Framework: `Streamlit`
- Solver: `OR-Tools CP-SAT`
- Horizon: `Monday-Friday`
- Machine time unit: `minutes from week start`
- Manpower time unit: `whole shift buckets`
- Manpower demand basis: `line x shift x competency`

### Machine objective

1. Minimize dropped BOs.
2. Minimize setup and changeover cost.
3. Minimize optional line preference penalty.

### Manpower objective

1. Minimize shortage.
2. Minimize lower-skill assignments.
3. Minimize shift activation cost.

## Folder Structure

```text
demo/
  README.md
  DEMO_PLAN.md
  DEMO_TODO.md
  requirements.txt
  app.py
  data/
    scenario_balanced/
    scenario_machine_bottleneck/
    scenario_manpower_shortage/
  src/
    __init__.py
    bridge.py
    config.py
    dummy_data.py
    io.py
    machine_demo_model.py
    manpower_demo_model.py
    result_formatters.py
    validators.py
  outputs/
```

## Scenario List

### `scenario_balanced`

- Purpose: baseline feasible case
- Expected machine behavior: all BOs should fit in the available line capacity
- Expected manpower behavior: active demand buckets should be fully staffed with no shortage

### `scenario_machine_bottleneck`

- Purpose: show machine-side tradeoffs under insufficient capacity
- Expected machine behavior: at least one lower-priority BO should be dropped
- Expected manpower behavior: manpower should generally remain feasible for whatever work is actually scheduled

### `scenario_manpower_shortage`

- Purpose: show downstream staffing shortage after machine scheduling succeeds
- Expected machine behavior: machine scheduling should remain feasible
- Expected manpower behavior: some active `line x shift x competency` buckets should remain understaffed

## CSV Schema Summary

### `machine_orders.csv`

- `bo_id`: unique BO identifier
- `product_code`: product or family code
- `duration_min`: processing duration in minutes
- `eligible_lines_json`: JSON array of allowed lines
- `priority`: lower number means more important
- `setup_time_min`: first-job setup minutes
- `setup_cost`: first-job setup cost
- `line_preference_penalty_json`: JSON object mapping line to soft penalty
- `demand_qty`: optional display-only quantity
- `customer_name`: optional display-only customer label

### `machine_lines.csv`

- `line_id`: unique line identifier
- `capacity_min`: available minutes in the planning horizon
- `display_name`: user-facing line label

### `machine_changeovers.csv`

- `line_id`: line identifier
- `from_product_code`: previous product
- `to_product_code`: next product
- `changeover_time_min`: changeover minutes
- `changeover_cost`: changeover cost

### `employees.csv`

- `employee_id`: unique employee identifier
- `employee_name`: user-facing employee name
- `skills_json`: JSON object mapping competency to score
- `shift_cost`: per-shift business cost
- `available_days_json`: JSON array of available weekdays
- `can_work_long_shift`: optional boolean placeholder
- `team`: optional grouping field

### `shifts.csv`

- `shift_id`: unique shift identifier
- `day`: weekday label
- `shift_name`: user-facing shift label
- `start_min`: shift start in minutes from week start
- `end_min`: shift end in minutes from week start

### `line_shift_requirements.csv`

- `line_id`: line identifier
- `shift_name`: shift label used by the bridge
- `competency`: required competency
- `required_qty`: number of workers required when the line is active in that shift
- `scenario_note`: optional business explanation shown in the UI

### `scenario_meta.json`

- `scenario_id`
- `title`
- `description`
- `expected_behavior`
- `difficulty`

## How Machine And Manpower Stages Connect

1. The machine model assigns BOs to eligible lines and sequences them.
2. The resulting machine schedule is checked against the shift calendar.
3. If a scheduled BO overlaps a shift on a line, that line-shift bucket becomes active.
4. The bridge joins active line-shift buckets with static competency requirements from `line_shift_requirements.csv`.
5. The manpower model staffs those active buckets and records explicit shortage rows when demand cannot be fully covered.

## Install

Run from the repository root:

```bash
pip install -r demo/requirements.txt
```

If you prefer to work from inside `demo/`, use:

```bash
pip install -r requirements.txt
```

## Run

From the repository root:

```bash
streamlit run demo/app.py
```

From inside `demo/`:

```bash
streamlit run app.py
```

## Quick Start Runbook

1. Install the demo requirements.
2. Start the Streamlit app.
3. In the scenario selector, choose `Balanced Feasible Scenario` first.
4. Confirm that validation passes near the top of the page.
5. Click `Run Machine Model`.
6. Review machine KPIs, schedule, Gantt, capacity, and dropped-order sections.
7. Review the derived demand section to see how machine activity turns into manpower requirements.
8. Click `Run Manpower Model`.
9. Review coverage, understaffed buckets, assignments, employee schedule, cost breakdown, and diagnostics.
10. Use the export section to download CSVs or the bundled zip archive.

## Expected Smoke Checks

A new engineer should be able to verify the demo with these three runs:

### Balanced scenario

- machine run succeeds
- no dropped BOs are expected
- manpower run succeeds
- no understaffed buckets are expected

### Machine bottleneck scenario

- machine run succeeds
- dropped BO table should be non-empty
- manpower run should reflect only the BOs that remain scheduled

### Manpower shortage scenario

- machine run succeeds
- derived demand appears
- manpower run succeeds
- understaffed buckets table should be non-empty

## Export And Reset Tools

The app exposes browser-side tools so users do not need to manipulate output files manually.

Available exports:

- machine schedule CSV
- manpower assignments CSV
- shortage summary CSV
- bundled zip archive containing machine, demand, and manpower outputs

Reset behavior:

- `Reset Bundled Scenarios` rewrites the bundled scenario folders using the deterministic generator in `demo/src/dummy_data.py`
- reset also clears cached scenario loads and solver results in the app

## Isolation From Production Code

Demo v1 is intended to be independent of:

- `main.py`
- `src/preprocessing/*`
- SQL files under `sql/`
- BigQuery credentials and production runtime configuration

The demo should use only local artifacts under `demo/`.

## Known Limitations

- the demo is intentionally smaller than production and does not represent every planning rule
- manpower demand is derived as `line x shift x competency`, not `line x product x competency`
- the UI is read-only for bundled scenarios unless files are edited outside the app
- solver settings are intentionally minimal and not exposed as a full tuning surface
- local generated folders such as `__pycache__/` and `.ipynb_checkpoints/` are not part of the intended demo contract

## Troubleshooting

### `ModuleNotFoundError: No module named demo`

Run the app from the repository root with:

```bash
streamlit run demo/app.py
```

### Streamlit command not found

Reinstall requirements and ensure the active Python environment is the one where `streamlit` was installed.

### Validation errors block the run

Use the bundled reset button in the app, or regenerate scenarios from Python by calling `reset_all_scenarios()` from `demo/src/dummy_data.py`.

## Current Status

The v1 demo flow now includes:

- scenario loading and validation
- simplified machine solver and machine result UI
- machine-to-manpower bridge and derived demand UI
- simplified manpower solver and manpower result UI
- browser-side export tools and deterministic scenario reset

For implementation history and remaining tasks, see [DEMO_PLAN.md](./DEMO_PLAN.md) and [DEMO_TODO.md](./DEMO_TODO.md).
