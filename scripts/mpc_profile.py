"""Profiles BicycleFrontseater's per-tick MPC worker: per-tick World.step() wall time
and per-solve iteration/eval counts, both as percentiles, for the SPLIT mission (the
one with avoid regions, i.e. the hard case). Run from the repo root: python scripts/mpc_profile.py

Excludes World.step()'s first tick from the timing percentiles: that tick includes each
platform's one-time worker-process cold start (spawn + import numpy/scipy inside the
child before it can service its first request), which would otherwise look like an
outlier MPC solve rather than the one-time startup cost it actually is.
"""
import sys
import time

sys.path.insert(0, "src")

N_STEPS = 600
DT = 0.1


def _percentile(sorted_data: list, fraction: float):
    index = min(int(len(sorted_data) * fraction), len(sorted_data) - 1)
    return sorted_data[index]


def _report(label: str, sorted_data: list) -> None:
    print(f"{label} -- min: {sorted_data[0]:.2f}  p25: {_percentile(sorted_data, 0.25):.2f}  "
          f"median: {_percentile(sorted_data, 0.5):.2f}  p75: {_percentile(sorted_data, 0.75):.2f}  "
          f"p90: {_percentile(sorted_data, 0.9):.2f}  p99: {_percentile(sorted_data, 0.99):.2f}  "
          f"max: {sorted_data[-1]:.2f}")


def _logging_worker(request_queue, response_queue, nav_horizon, nav_dt, wheelbase,
                     min_speed, max_speed, min_steer, max_steer) -> None:
    """Same as mtofr.world.ground_plane.mpc.run_mpc_worker, but wraps minimize() to
    also record each solve's (elapsed time, iterations, rollout evals) -- this replaces
    the worker entry point for the duration of this profiling run only."""
    import numpy as np
    import mtofr.world.ground_plane.mpc as mpc_module
    from scipy.optimize import minimize as real_minimize

    solve_log = []   # (elapsed_seconds, nit, nfev)

    def logging_minimize(fun, x0, bounds, method, options=None):
        t0 = time.perf_counter()
        result = real_minimize(fun, x0, bounds=bounds, method=method, options=options)
        solve_log.append((time.perf_counter() - t0, result.nit, result.nfev))
        return result

    mpc_module.minimize = logging_minimize
    from mtofr.world.ground_plane.mpc import solve_mpc

    prev_solution = np.zeros(nav_horizon * 2)
    avoid_regions = []

    while True:
        request = request_queue.get()
        request_type = request["type"]

        if request_type == "shutdown":
            with open(request["log_path"], "a") as log_file:
                for elapsed, nit, nfev in solve_log:
                    log_file.write(f"{elapsed * 1000:.4f},{nit},{nfev}\n")
            return

        if request_type == "add_avoid_region":
            avoid_regions.append((request["point_x"], request["point_y"], request["radius"]))
            continue

        if request_type == "compute":
            vel, steer, prev_solution = solve_mpc(
                nav_horizon, nav_dt, wheelbase, min_speed, max_speed, min_steer, max_steer,
                prev_solution, request["state"], request["target"], avoid_regions,
            )
            response_queue.put({"vel": vel, "steer": steer})


def main() -> None:
    import mtofr.world.ground_plane.frontseater as frontseater_module
    frontseater_module.run_mpc_worker = _logging_worker

    from mtofr.world.world import World
    from mtofr.world.ground_plane.env import GroundPlaneEnv
    from mtofr.world.ground_plane.hardware import BicycleHardware
    from mtofr.backseater.backseater import Backseater
    from mtofr.knowledge.knowledge import Knowledge
    from mtofr.relay.relay import Relay
    from mtofr.missions import mission_split_ugv1, mission_split_ugv2

    import tempfile
    import os
    solve_log_path = os.path.join(tempfile.gettempdir(), "mtofr_mpc_profile_solve_log.txt")
    if os.path.exists(solve_log_path):
        os.remove(solve_log_path)

    ugv1_hardware = BicycleHardware()
    ugv1_frontseater = frontseater_module.BicycleFrontseater(hardware=ugv1_hardware)
    ugv1_knowledge = Knowledge()
    ugv1_backseater = Backseater(frontseater=ugv1_frontseater, knowledge=ugv1_knowledge,
                                  mission_graph=mission_split_ugv1, platform_id="ugv1")
    ugv2_hardware = BicycleHardware()
    ugv2_frontseater = frontseater_module.BicycleFrontseater(hardware=ugv2_hardware)
    ugv2_knowledge = Knowledge()
    ugv2_backseater = Backseater(frontseater=ugv2_frontseater, knowledge=ugv2_knowledge,
                                  mission_graph=mission_split_ugv2, platform_id="ugv2")
    environment = GroundPlaneEnv()
    relay = Relay()
    world = World(environment, backseaters={"ugv1": ugv1_backseater, "ugv2": ugv2_backseater}, relay=relay)

    tick_times = []
    try:
        for _ in range(N_STEPS):
            t0 = time.perf_counter()
            world.step(DT)
            tick_times.append(time.perf_counter() - t0)
    finally:
        # shutdown() blocks on the worker's queue, so route the log path through the
        # same "shutdown" message rather than a second round-trip.
        for frontseater in (ugv1_frontseater, ugv2_frontseater):
            if frontseater._worker_process.is_alive():
                frontseater._request_queue.put({"type": "shutdown", "log_path": solve_log_path})
                frontseater._worker_process.join(timeout=5.0)

    cold_start_ms = tick_times[0] * 1000
    tick_times_ms = sorted(t * 1000 for t in tick_times[1:])   # drop the one-time cold-start tick

    with open(solve_log_path) as log_file:
        rows = [line.strip().split(",") for line in log_file if line.strip()]
    solve_times_ms = sorted(float(row[0]) for row in rows)
    iteration_counts = sorted(int(row[1]) for row in rows)
    eval_counts = sorted(int(row[2]) for row in rows)
    hit_cap = sum(1 for n in iteration_counts if n >= 20)

    print(f"{N_STEPS} ticks, {N_STEPS * DT:.0f}s sim time, 2 platforms (SPLIT mission)")
    print(f"first tick (worker cold start, excluded below): {cold_start_ms:.2f}ms\n")
    _report("World.step() wall time (ms)", tick_times_ms)
    _report("MPC solve time (ms)", solve_times_ms)
    _report("MPC iterations to solution", iteration_counts)
    _report("MPC rollout evaluations", eval_counts)
    print(f"hit the 20-iteration cap: {hit_cap}/{len(iteration_counts)} "
          f"({100 * hit_cap / len(iteration_counts):.1f}%)")

    os.remove(solve_log_path)


if __name__ == "__main__":
    main()