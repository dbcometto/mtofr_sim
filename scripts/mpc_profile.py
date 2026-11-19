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


#========================================#
# Config
#========================================#

STEP_COUNT = 600
DT = 0.1   # s per sim step
WORKER_JOIN_TIMEOUT = 5.0   # s
MILLISECONDS_PER_SECOND = 1000
REPORT_PERCENTILES = (("p25", 0.25), ("median", 0.5), ("p75", 0.75), ("p90", 0.9), ("p99", 0.99))







#========================================#
# Reporting
#========================================#

def _percentile(sorted_data: list, fraction: float):
    """The value at `fraction` (0-1) of the way through already-sorted data."""
    index = min(int(len(sorted_data) * fraction), len(sorted_data) - 1)
    return sorted_data[index]


def _report(label: str, sorted_data: list) -> None:
    """Prints min, the REPORT_PERCENTILES, and max of already-sorted data on one line."""
    percentiles = "  ".join(f"{name}: {_percentile(sorted_data, fraction):.2f}" for name, fraction in REPORT_PERCENTILES)
    print(f"{label} -- min: {sorted_data[0]:.2f}  {percentiles}  max: {sorted_data[-1]:.2f}")







#========================================#
# Profiling Worker
#========================================#

def _logging_worker(request_queue, response_queue, nav_horizon, nav_dt, wheelbase,
                     min_speed, max_speed, min_steer, max_steer) -> None:
    """Same as mtofr.world.ground_plane.platforms.bicycle_ugv.mpc.run_mpc_worker, but wraps minimize() to
    also record each solve's (elapsed time, iterations, rollout evals) -- this replaces
    the worker entry point for the duration of this profiling run only."""
    import numpy as np
    import mtofr.world.ground_plane.platforms.bicycle_ugv.mpc as mpc_module
    from scipy.optimize import minimize as real_minimize

    solve_log = []   # (elapsed_seconds, iterations, evaluations)

    def logging_minimize(fun, x0, bounds, method, options=None):
        """scipy's minimize(), recording its time and iteration/evaluation counts."""
        start_time = time.perf_counter()
        result = real_minimize(fun, x0, bounds=bounds, method=method, options=options)
        solve_log.append((time.perf_counter() - start_time, result.nit, result.nfev))
        return result

    mpc_module.minimize = logging_minimize
    from mtofr.world.ground_plane.platforms.bicycle_ugv.mpc import solve_mpc, CONTROLS_PER_STEP

    prev_solution = np.zeros(nav_horizon * CONTROLS_PER_STEP)
    avoid_regions = []

    request = request_queue.get()
    while request["type"] != "shutdown":
        if request["type"] == "add_avoid_region":
            avoid_regions.append((request["point_x"], request["point_y"], request["radius"]))
        elif request["type"] == "compute":
            vel, steer, prev_solution = solve_mpc(
                nav_horizon, nav_dt, wheelbase, min_speed, max_speed, min_steer, max_steer,
                prev_solution, request["state"], request["target"], avoid_regions,
            )
            response_queue.put({"vel": vel, "steer": steer})
        request = request_queue.get()

    with open(request["log_path"], "a") as log_file:
        for elapsed, iterations, evaluations in solve_log:
            log_file.write(f"{elapsed * MILLISECONDS_PER_SECOND:.4f},{iterations},{evaluations}\n")







#========================================#
# Main
#========================================#

def main() -> None:
    """Runs the SPLIT mission for STEP_COUNT ticks with the logging worker and prints the report."""
    import mtofr.world.ground_plane.platforms.bicycle_ugv.frontseater as frontseater_module
    frontseater_module.run_mpc_worker = _logging_worker

    from mtofr.world.world import World
    from mtofr.world.ground_plane.env import GroundPlaneEnv
    from mtofr.world.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
    from mtofr.world.ground_plane.platforms.bicycle_ugv.mpc import MPC_MAX_ITERATIONS
    from mtofr.world.platform import Platform, PlatformSpec
    from mtofr.missions import mission_split_ugv1, mission_split_ugv2

    import tempfile
    import os
    solve_log_path = os.path.join(tempfile.gettempdir(), "mtofr_mpc_profile_solve_log.txt")
    if os.path.exists(solve_log_path):
        os.remove(solve_log_path)

    # Built via frontseater_module (not a spec factory) so the patched run_mpc_worker above is used.
    def build_frontseater(debug: bool = False):
        """Builds a default BicycleHardware/BicycleFrontseater pair at the origin."""
        return frontseater_module.BicycleFrontseater(hardware=BicycleHardware())
    platforms = {
        "ugv1": Platform(PlatformSpec("ugv1", build_frontseater, mission_graph=mission_split_ugv1)),
        "ugv2": Platform(PlatformSpec("ugv2", build_frontseater, mission_graph=mission_split_ugv2)),
    }
    environment = GroundPlaneEnv()
    world = World(environment, platforms=platforms)


    # Run
    tick_times = []   # s
    try:
        for _ in range(STEP_COUNT):
            start_time = time.perf_counter()
            world.step(DT)
            tick_times.append(time.perf_counter() - start_time)
    finally:
        # shutdown() blocks on the worker's queue, so route the log path through the
        # same "shutdown" message rather than a second round-trip.
        for frontseater in (platform.frontseater for platform in platforms.values()):
            if frontseater._worker_process.is_alive():
                frontseater._request_queue.put({"type": "shutdown", "log_path": solve_log_path})
                frontseater._worker_process.join(timeout=WORKER_JOIN_TIMEOUT)


    # Report
    cold_start_ms = tick_times[0] * MILLISECONDS_PER_SECOND
    tick_times_ms = sorted(tick_time * MILLISECONDS_PER_SECOND for tick_time in tick_times[1:])   # drop the cold-start tick

    with open(solve_log_path) as log_file:
        rows = [line.strip().split(",") for line in log_file if line.strip()]
    solve_times_ms = sorted(float(row[0]) for row in rows)
    iteration_counts = sorted(int(row[1]) for row in rows)
    evaluation_counts = sorted(int(row[2]) for row in rows)
    hit_cap = sum(1 for iterations in iteration_counts if iterations >= MPC_MAX_ITERATIONS)

    print(f"{STEP_COUNT} ticks, {STEP_COUNT * DT:.0f}s sim time, {len(platforms)} platforms (SPLIT mission)")
    print(f"first tick (worker cold start, excluded below): {cold_start_ms:.2f}ms\n")
    _report("World.step() wall time (ms)", tick_times_ms)
    _report("MPC solve time (ms)", solve_times_ms)
    _report("MPC iterations to solution", iteration_counts)
    _report("MPC rollout evaluations", evaluation_counts)
    print(f"hit the {MPC_MAX_ITERATIONS}-iteration cap: {hit_cap}/{len(iteration_counts)} "
          f"({100 * hit_cap / len(iteration_counts):.1f}%)")

    os.remove(solve_log_path)


if __name__ == "__main__":
    main()
