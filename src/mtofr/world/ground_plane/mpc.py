"""Defines the MPC solve used by BicycleFrontseater, and the worker process entry point
that runs it off the main process so multiple platforms' solves can overlap."""
import math
import numpy as np
from scipy.optimize import minimize

from mtofr.world.ground_plane.dynamics import bicycle_step


#==========# Solve #==========#

def solve_mpc(nav_horizon: int, nav_dt: float, wheelbase: float, min_speed: float, max_speed: float,
              min_steer: float, max_steer: float, prev_solution: np.ndarray, state_xytheta: tuple,
              target_xy: tuple, avoid_regions: list) -> tuple:
    """Solves for the next (vel, steer) via a receding-horizon rollout, warm-started from
    prev_solution. Operates only on plain floats/tuples/arrays -- no Frontseater/Hardware/
    Location objects -- so it runs identically whether called in-process or from a worker
    process, with minimal data crossing that boundary. Returns (vel, steer, new_prev_solution).
    """
    state_x, state_y, state_theta = state_xytheta
    target_x, target_y = target_xy

    # Plain math (not numpy arrays/matrices): this closure runs ~150+ times per solve
    # (rollout length x finite-difference gradient probes), where numpy's per-call
    # dispatch overhead swamps the actual arithmetic for scalars. R = diag([1.0, 0.1])
    # and Q = eye(2) are fixed, so their quadratic forms are inlined as scalar sums.
    def cost_fn(x, y, theta, vel, steer):
        bearing = math.atan2(target_y - y, target_x - x)
        heading_error = math.atan2(math.sin(theta - bearing), math.cos(theta - bearing))
        platform_cost = 20 * heading_error**2

        standard_cost = vel * vel * 1.0 + steer * steer * 0.1

        error_x, error_y = x - target_x, y - target_y
        mission_cost = error_x * error_x + error_y * error_y
        for point_x, point_y, radius in avoid_regions:
            d = math.hypot(x - point_x, y - point_y)
            mission_cost += 100.0 * max(0.0, radius - d)**2

            # Penalize heading directly at the obstacle, scaled by proximity
            avoid_bearing = math.atan2(point_y - y, point_x - x)
            heading_toward_avoid = math.atan2(math.sin(theta - avoid_bearing), math.cos(theta - avoid_bearing))
            proximity = 1.0 / (d + 0.5)   # stronger penalty the closer you are
            mission_cost += 10.0 * proximity * math.cos(heading_toward_avoid)**2

        return platform_cost + standard_cost + mission_cost

    def rollout_cost(control_seq):
        controls = control_seq.reshape(nav_horizon, 2)
        x, y, theta = state_x, state_y, state_theta
        cost = 0.0
        for vel, steer in controls:
            x, y, theta, _, _, _ = bicycle_step(x, y, theta, vel, steer, wheelbase,
                                                  min_speed, max_speed, min_steer, max_steer, nav_dt)
            cost += cost_fn(x, y, theta, vel, steer)
        return cost

    prev = prev_solution.reshape(nav_horizon, 2)
    x0 = np.vstack([prev[1:], prev[-1]]).flatten()
    bounds = [(min_speed, max_speed), (min_steer, max_steer)] * nav_horizon

    # Capped well below scipy's default of 100: since this re-solves every tick with a
    # warm start anyway (standard receding-horizon MPC practice), an unconverged solve
    # near a hard obstacle-avoidance case would otherwise burn the full 100 iterations
    # trying to reach an optimum that isn't much better than what a much shorter budget
    # already finds, at several times the wall-clock cost -- see notes.md for the
    # measurements behind this number.
    result = minimize(rollout_cost, x0, bounds=bounds, method="SLSQP", options={"maxiter": 20})
    vel, steer = result.x[0], result.x[1]
    return vel, steer, result.x


#==========# Worker process #==========#

def run_mpc_worker(request_queue, response_queue, nav_horizon: int, nav_dt: float, wheelbase: float,
                    min_speed: float, max_speed: float, min_steer: float, max_steer: float) -> None:
    """Entry point for a platform's dedicated, persistent MPC worker process (started once
    by BicycleFrontseater, not per-tick). Holds the warm-start solution and avoid-region
    list resident for the platform's lifetime -- both are that platform's own persistent
    planning state, so only the current hardware state and target need to cross the
    process boundary each tick, not the full solver state. Naive request/response loop,
    no timeout or crash recovery -- matches this project's other placeholder comms seams
    (e.g. Relay's clock sync) ahead of the real comms-boundary work planned for build order
    step 4."""
    prev_solution = np.zeros(nav_horizon * 2)
    avoid_regions = []   # [(point_x, point_y, radius), ...]

    while True:
        request = request_queue.get()
        request_type = request["type"]

        if request_type == "shutdown":
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