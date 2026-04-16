from __future__ import annotations

import socket
import subprocess
import sys
import time
import types
from pathlib import Path

for module_name in ("numexpr", "bottleneck"):
    if module_name not in sys.modules:
        stub = types.ModuleType(module_name)
        stub.__version__ = "999.0"
        sys.modules[module_name] = stub

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.bridge import build_line_shift_demand
from src.config import DATA_DIR
from src.io import list_scenarios, load_scenario
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
from src.validators import validate_scenario_folder


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_streamlit_app() -> None:
    port = 8765
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless",
        "true",
        "--server.port",
        str(port),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    deadline = time.time() + 30
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                raise AssertionError("Streamlit exited before becoming ready.")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.25)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    return
            time.sleep(0.25)
        raise AssertionError("Timed out waiting for Streamlit to accept connections.")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _run_scenario_checks() -> None:
    expected = {
        "scenario_balanced": {
            "dropped_orders": 0,
            "min_shortage": 0,
            "max_shortage": 0,
        },
        "scenario_machine_bottleneck": {
            "min_dropped_orders": 1,
            "max_shortage": 0,
        },
        "scenario_manpower_shortage": {
            "dropped_orders": 0,
            "min_shortage": 1,
        },
    }

    scenarios = list_scenarios(DATA_DIR)
    _assert(len(scenarios) == 3, f"Expected 3 bundled scenarios, found {len(scenarios)}")

    for record in scenarios:
        scenario_name = record["name"]
        scenario_path = record["path"]
        validation_errors = validate_scenario_folder(scenario_path)
        _assert(not validation_errors, f"Validation failed for {scenario_name}: {validation_errors}")

        scenario = load_scenario(scenario_path)
        machine_result = solve_machine_demo(
            scenario["machine_orders"],
            scenario["machine_lines"],
            scenario["machine_changeovers"],
        )
        _assert(
            machine_result["solver_summary"]["status"] in {"OPTIMAL", "FEASIBLE"},
            f"Machine solve failed for {scenario_name}: {machine_result['solver_summary']}",
        )
        _assert(
            len(machine_result["schedule_df"]) > 0,
            f"Machine schedule is empty for {scenario_name}",
        )

        machine_kpis = build_machine_kpis(
            machine_result["schedule_df"],
            machine_result["dropped_df"],
            machine_result["line_summary_df"],
            machine_result["solver_summary"],
        )
        machine_costs = build_machine_cost_breakdown_df(
            machine_result["schedule_df"],
            machine_result["dropped_df"],
            machine_result["line_summary_df"],
            machine_result["solver_summary"],
        )
        machine_gantt = build_machine_gantt_df(machine_result["schedule_df"])
        machine_capacity = build_capacity_chart_df(machine_result["line_summary_df"])
        dropped_orders = build_dropped_orders_df(machine_result["dropped_df"])
        _assert(not machine_kpis.empty, f"Machine KPI formatter returned empty output for {scenario_name}")
        _assert(not machine_costs.empty, f"Machine cost formatter returned empty output for {scenario_name}")
        _assert(not machine_gantt.empty, f"Machine gantt formatter returned empty output for {scenario_name}")
        _assert(not machine_capacity.empty, f"Machine capacity formatter returned empty output for {scenario_name}")

        demand_df = build_line_shift_demand(
            machine_result["schedule_df"],
            scenario["shifts"],
            scenario["line_shift_requirements"],
        )
        _assert(not demand_df.empty, f"Derived demand is empty for {scenario_name}")

        manpower_result = solve_manpower_demo(
            scenario["employees"],
            scenario["shifts"],
            demand_df,
        )
        _assert(
            manpower_result["solver_summary"]["status"] in {"OPTIMAL", "FEASIBLE"},
            f"Manpower solve failed for {scenario_name}: {manpower_result['solver_summary']}",
        )

        manpower_kpis = build_manpower_kpis(
            manpower_result["assignments_df"],
            manpower_result["shortage_df"],
            manpower_result["coverage_summary_df"],
            manpower_result["solver_summary"],
        )
        manpower_costs = build_manpower_cost_breakdown_df(
            manpower_result["assignments_df"],
            manpower_result["shortage_df"],
            manpower_result["coverage_summary_df"],
            manpower_result["solver_summary"],
        )
        shortage_heatmap = build_shortage_heatmap_df(manpower_result["shortage_df"])
        employee_schedule = build_employee_schedule_df(manpower_result["assignments_df"])
        coverage_table = build_coverage_table_df(manpower_result["coverage_summary_df"])
        _assert(not manpower_kpis.empty, f"Manpower KPI formatter returned empty output for {scenario_name}")
        _assert(not manpower_costs.empty, f"Manpower cost formatter returned empty output for {scenario_name}")
        _assert(not coverage_table.empty, f"Coverage formatter returned empty output for {scenario_name}")
        if not manpower_result["assignments_df"].empty:
            _assert(not employee_schedule.empty, f"Employee schedule formatter returned empty output for {scenario_name}")
        if not manpower_result["shortage_df"].empty:
            _assert(not shortage_heatmap.empty, f"Shortage formatter returned empty output for {scenario_name}")

        expectation = expected[scenario_name]
        dropped_count = int(machine_result["solver_summary"].get("dropped_orders", 0))
        shortage_qty = int(manpower_result["solver_summary"].get("total_shortage_qty", 0))

        if "dropped_orders" in expectation:
            _assert(
                dropped_count == expectation["dropped_orders"],
                f"Unexpected dropped order count for {scenario_name}: expected {expectation['dropped_orders']}, got {dropped_count}",
            )
        if "min_dropped_orders" in expectation:
            _assert(
                dropped_count >= expectation["min_dropped_orders"],
                f"Expected at least {expectation['min_dropped_orders']} dropped orders for {scenario_name}, got {dropped_count}",
            )
        if "min_shortage" in expectation:
            _assert(
                shortage_qty >= expectation["min_shortage"],
                f"Expected shortage >= {expectation['min_shortage']} for {scenario_name}, got {shortage_qty}",
            )
        if "max_shortage" in expectation:
            _assert(
                shortage_qty <= expectation["max_shortage"],
                f"Expected shortage <= {expectation['max_shortage']} for {scenario_name}, got {shortage_qty}",
            )

        print(
            f"PASS {scenario_name}: machine_status={machine_result['solver_summary']['status']} dropped={dropped_count} "
            f"demand_rows={len(demand_df)} manpower_status={manpower_result['solver_summary']['status']} shortage={shortage_qty}"
        )
        if scenario_name == "scenario_machine_bottleneck":
            _assert(not dropped_orders.empty, "Machine bottleneck scenario should expose dropped BO rows")
        if scenario_name == "scenario_manpower_shortage":
            _assert(not shortage_heatmap.empty, "Manpower shortage scenario should expose shortage rows")


def main() -> None:
    _run_scenario_checks()
    _check_streamlit_app()
    print("PASS streamlit_app: headless startup succeeded")
    print("All Stage 18 smoke checks passed.")


if __name__ == "__main__":
    main()
