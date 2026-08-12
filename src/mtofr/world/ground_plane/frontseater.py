"""Defines frontseaters to be used with the ground_plane environment"""
import uuid
import numpy as np
from scipy.optimize import minimize
from mtofr.world.base import Frontseater, WorldState
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.knowledge.knowledge import Location


class BicycleFrontseater(Frontseater):
    """The planning/control brain for a UGV with bicycle dynamics. Runs its own
    internal MPC against its Hardware's dynamics model, never touching
    Hardware.state directly — only send_controls/read_state."""
    def __init__(self, hardware: BicycleHardware, nav_horizon=10, nav_dt=0.1, nav_tolerance=0.5, debug=False):
        self.hardware = hardware
        self.debug = debug

        self.nav_horizon = nav_horizon
        self.nav_dt = nav_dt
        self.nav_tolerance = nav_tolerance
        self._prev_solution = np.zeros(nav_horizon * 2)   # warm-start cache

        self._avoid_regions = []   # persistent, not a task: [{"point": Location, "radius": float}]

        self._active_handle = None
        self._active_target = None   # Location
        self._task_status = {}     # handle -> status string

        self._capability_registry = CapabilityRegistry([
            Capability(
                ipl_type="move_to",
                description="Navigate to a target location until within tolerance, using the internal MPC.",
                params=(ParamSpec("target", Location, "Location to navigate to", is_knowledge_ref=True),),
            ),
            Capability(
                ipl_type="avoid",
                description="Add a persistent circular avoid-region; instantaneous, not a duration task.",
                params=(
                    ParamSpec("point", Location, "Center of the avoid-region", is_knowledge_ref=True),
                    ParamSpec("radius", float, "Avoid-region radius in meters"),
                ),
            ),
        ])

    #=====# Capabilities #=====#
    def capabilities(self) -> CapabilityRegistry:
        return self._capability_registry

    def actuate(self, capability: str, params: dict) -> str:
        handle = str(uuid.uuid4())
        if self.debug:
            print(f"[Frontseater] actuate('{capability}', {params}) -> handle {handle[:8]}")

        if capability == "move_to":
            self._active_handle = handle
            self._active_target = params["target"]
            self._task_status[handle] = "received"

        elif capability == "avoid":
            self._avoid_regions.append(params)   # {"point": Location, "radius": float}
            self._task_status[handle] = "success"   # instantaneous, not a duration task

        else:
            raise ValueError(f"Unknown capability: {capability}")

        return handle

    def poll_status(self, handle: str) -> dict:
        status = self._task_status.get(handle, "fail")

        if handle == self._active_handle and status in ("received", "in_progress"):
            current_state = self.hardware.read_state()
            distance = np.hypot(current_state.x - self._active_target.x,
                                 current_state.y - self._active_target.y)
            if distance <= self.nav_tolerance:
                status = "success"
                self._active_handle = None
                self._active_target = None
            else:
                status = "in_progress"
            self._task_status[handle] = status

        return {"status": status}

    def cancel(self, handle: str) -> None:
        if handle == self._active_handle:
            self._active_handle = None
            self._active_target = None
        self._task_status[handle] = "fail"

    #=====# Controls (internal MPC) #=====#
    def _rollout_cost(self, control_seq, cost_fn, start_state):
        controls = control_seq.reshape(self.nav_horizon, 2)
        cost = 0.0
        state = start_state

        for vel, steer in controls:
            u = [vel, steer]
            state = self.hardware.calculate_dynamics(state, {"vel": vel, "steer": steer}, self.nav_dt)
            cost += cost_fn(state, u)
        return cost

    def compute_controls(self, state: WorldState) -> dict:
        if self._active_target is None:
            return {"vel": 0.0, "steer": 0.0}

        target = self._active_target
        avoid = self._avoid_regions

        def platform_cost_fn(s, u):
            bearing = np.arctan2(target.y - s.y, target.x - s.x)
            heading_error = np.arctan2(np.sin(s.theta - bearing), np.cos(s.theta - bearing))
            return 20 * heading_error**2

        def standard_cost_fn(s, u, R=None):
            u = np.array(u)
            if R is None:
                R = np.diag([1.0, 0.1])
            return u.T @ R @ u

        def mission_cost_fn(s, u, Q=None, avoid_weight=100.0, avoid_heading_weight=10.0):
            if Q is None:
                Q = np.eye(2)
            e = np.array([s.x - target.x, s.y - target.y])
            cost = e.T @ Q @ e

            for region in avoid:
                point, radius = region["point"], region["radius"]
                d = np.hypot(s.x - point.x, s.y - point.y)
                cost += avoid_weight * max(0.0, radius - d)**2

                # Penalize heading directly at the obstacle, scaled by proximity
                avoid_bearing = np.arctan2(point.y - s.y, point.x - s.x)
                heading_toward_avoid = np.arctan2(np.sin(s.theta - avoid_bearing), np.cos(s.theta - avoid_bearing))
                proximity = 1.0 / (d + 0.5)   # stronger penalty the closer you are
                cost += avoid_heading_weight * proximity * np.cos(heading_toward_avoid)**2

            return cost

        def cost_fn(s, u):
            return platform_cost_fn(s, u) + standard_cost_fn(s, u) + mission_cost_fn(s, u)

        prev = self._prev_solution.reshape(self.nav_horizon, 2)
        x0 = np.vstack([prev[1:], prev[-1]]).flatten()

        bounds = [(self.hardware.min_speed, self.hardware.max_speed),
                  (self.hardware.min_steer, self.hardware.max_steer)] * self.nav_horizon

        result = minimize(self._rollout_cost, x0, args=(cost_fn, state), bounds=bounds, method="SLSQP")

        self._prev_solution = result.x
        vel, steer = result.x[0], result.x[1]
        return {"vel": vel, "steer": steer}