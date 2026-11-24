"""Defines the MPC solve used by BicycleFrontseater, and the worker process entry point
that runs it off the main process so multiple platforms' solves can overlap."""
import math
import numpy as np
from scipy.optimize import minimize

from mtofr.environments.ground_plane.platforms.bicycle_ugv.dynamics import bicycle_step


#========================================#
# Config
#========================================#

CONTROLS_PER_STEP = 2   # (vel, steer)

# Cost weights. The control weights are R = diag([VELOCITY_WEIGHT, STEER_WEIGHT]);
# the target-distance weight Q = eye(2) is implicit.
HEADING_ERROR_WEIGHT = 20.0   # per rad^2 of heading error toward the target
VELOCITY_WEIGHT = 1.0         # per (m/s)^2
STEER_WEIGHT = 0.1            # per rad^2
AVOID_PENETRATION_WEIGHT = 100.0   # per m^2 inside an avoid-region's radius
AVOID_HEADING_WEIGHT = 10.0        # scales the heading-at-obstacle penalty
AVOID_PROXIMITY_SOFTENING = 0.5    # m added to the distance, so proximity stays finite at the obstacle

# Pose-tracking cost (a target with a heading, e.g. follow's offhooked point).
# NOTE: weights from Cometto et al., "A Method for Human-Led UGV Convoying in Unstructured
# Environments", sec. IV-I: W_s = diag(1, 1, 0.1), W_a = diag(0.2, 0.7).  Raising the steer
# cost and lowering the heading cost is what kept the convoy string-stable there.  The paper
# works in the follower's frame; equal x/y weights make the world frame equivalent.
TRACKING_POSITION_WEIGHT = 1.0   # per m^2
TRACKING_HEADING_WEIGHT = 0.1    # per rad^2
TRACKING_VELOCITY_WEIGHT = 0.2   # per (m/s)^2
TRACKING_STEER_WEIGHT = 0.7      # per rad^2

# NOTE: capped well below scipy's default of 100: since this re-solves every tick with a
# warm start anyway (standard receding-horizon MPC practice), an unconverged solve
# near a hard obstacle-avoidance case would otherwise burn the full 100 iterations
# trying to reach an optimum that isn't much better than what a much shorter budget
# already finds, at several times the wall-clock cost -- see docs/notes.md (note 14)
# for the measurements behind this number.
MPC_MAX_ITERATIONS = 20







#========================================#
# Solve
#========================================#

def solve_mpc(nav_horizon: int, nav_dt: float, wheelbase: float, min_speed: float, max_speed: float,
              min_steer: float, max_steer: float, prev_solution: np.ndarray, state_xytheta: tuple,
              target_xy: tuple, target_heading: float | None, avoid_regions: list) -> tuple:
    """Solves for the next (vel, steer) (m/s, rad) via a receding-horizon rollout of
    `nav_horizon` steps of `nav_dt` (s), warm-started from prev_solution. Positions are
    m in the world frame, theta in rad. Operates only on plain floats/tuples/arrays --
    no Frontseater/Hardware/Location objects -- so it runs identically whether called
    in-process or from a worker process, with minimal data crossing that boundary.
    With `target_heading` None it reaches a point (steering toward its bearing); with a
    heading (rad) it tracks that pose with the TRACKING_* cost.
    Returns (vel, steer, new_prev_solution).
    """
    state_x, state_y, state_theta = state_xytheta
    target_x, target_y = target_xy

    # NOTE: plain math (not numpy arrays/matrices): these closures run ~150+ times per solve
    # (rollout length x finite-difference gradient probes), where numpy's per-call
    # dispatch overhead swamps the actual arithmetic for scalars, so the fixed R and Q
    # quadratic forms are inlined as scalar sums.
    def point_cost(x, y, theta, vel, steer):
        """Point-reaching stage cost: heading toward the target, control effort, and target distance."""
        bearing = math.atan2(target_y - y, target_x - x)
        heading_error = math.atan2(math.sin(theta - bearing), math.cos(theta - bearing))
        platform_cost = HEADING_ERROR_WEIGHT * heading_error**2

        standard_cost = vel * vel * VELOCITY_WEIGHT + steer * steer * STEER_WEIGHT

        error_x, error_y = x - target_x, y - target_y
        return platform_cost + standard_cost + error_x * error_x + error_y * error_y

    def pose_cost(x, y, theta, vel, steer):
        """Pose-tracking stage cost: (s - s_target)^T W_s (s - s_target) + a^T W_a a."""
        error_x, error_y = x - target_x, y - target_y
        heading_error = math.atan2(math.sin(theta - target_heading), math.cos(theta - target_heading))
        return (TRACKING_POSITION_WEIGHT * (error_x * error_x + error_y * error_y)
                + TRACKING_HEADING_WEIGHT * heading_error * heading_error
                + TRACKING_VELOCITY_WEIGHT * vel * vel + TRACKING_STEER_WEIGHT * steer * steer)

    target_cost = point_cost if target_heading is None else pose_cost

    def cost_fn(x, y, theta, vel, steer):
        """Stage cost of one rollout step: the target cost plus avoid-regions."""
        mission_cost = target_cost(x, y, theta, vel, steer)
        for point_x, point_y, radius in avoid_regions:
            distance = math.hypot(x - point_x, y - point_y)
            mission_cost += AVOID_PENETRATION_WEIGHT * max(0.0, radius - distance)**2

            # Penalize heading directly at the obstacle, scaled by proximity
            avoid_bearing = math.atan2(point_y - y, point_x - x)
            heading_toward_avoid = math.atan2(math.sin(theta - avoid_bearing), math.cos(theta - avoid_bearing))
            proximity = 1.0 / (distance + AVOID_PROXIMITY_SOFTENING)   # stronger penalty the closer you are
            mission_cost += AVOID_HEADING_WEIGHT * proximity * math.cos(heading_toward_avoid)**2

        return mission_cost

    def rollout_cost(control_sequence):
        """Total cost of rolling the bicycle model forward under a flattened control sequence."""
        controls = control_sequence.reshape(nav_horizon, CONTROLS_PER_STEP)
        x, y, theta = state_x, state_y, state_theta
        cost = 0.0
        for vel, steer in controls:
            x, y, theta, _, _, _ = bicycle_step(x, y, theta, vel, steer, wheelbase,
                                                  min_speed, max_speed, min_steer, max_steer, nav_dt)
            cost += cost_fn(x, y, theta, vel, steer)
        return cost


    # Warm start: shift the previous solution one step, repeating its last control
    previous = prev_solution.reshape(nav_horizon, CONTROLS_PER_STEP)
    initial_guess = np.vstack([previous[1:], previous[-1]]).flatten()
    bounds = [(min_speed, max_speed), (min_steer, max_steer)] * nav_horizon


    result = minimize(rollout_cost, initial_guess, bounds=bounds, method="SLSQP",
                      options={"maxiter": MPC_MAX_ITERATIONS})
    vel, steer = result.x[0], result.x[1]
    return vel, steer, result.x







#========================================#
# Worker Process
#========================================#

def run_mpc_worker(request_queue, response_queue, nav_horizon: int, nav_dt: float, wheelbase: float,
                    min_speed: float, max_speed: float, min_steer: float, max_steer: float) -> None:
    """Entry point for a platform's dedicated, persistent MPC worker process (started once
    by BicycleFrontseater, not per-tick). Holds the warm-start solution and avoid-region
    list resident for the platform's lifetime -- both are that platform's own persistent
    planning state, so only the current hardware state and target need to cross the
    process boundary each tick, not the full solver state. Serves requests until a
    "shutdown" request arrives."""
    # TODO: naive request/response loop with no timeout or crash recovery, a placeholder
    # ahead of the real comms-boundary work (see roadmap.md).
    prev_solution = np.zeros(nav_horizon * CONTROLS_PER_STEP)
    avoid_regions = []   # [(point_x, point_y, radius), ...], m, world frame

    request = request_queue.get()
    while request["type"] != "shutdown":
        if request["type"] == "add_avoid_region":
            avoid_regions.append((request["point_x"], request["point_y"], request["radius"]))
        elif request["type"] == "compute":
            vel, steer, prev_solution = solve_mpc(
                nav_horizon, nav_dt, wheelbase, min_speed, max_speed, min_steer, max_steer,
                prev_solution, request["state"], request["target"], request["target_heading"], avoid_regions,
            )
            response_queue.put({"vel": vel, "steer": steer})
        request = request_queue.get()
