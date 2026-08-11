"""Defines platforms to be used with the ground_plane environment"""
import uuid
import numpy as np
from scipy.optimize import minimize
from mtofr.world.base import Platform, WorldState


class BicycleUGV(Platform):
    """A UGV with bicycle dynamics

    Controls:
    - "vel": desired forward speed in m/s
    - "steer": desired steering angle in rad around +z
    """
    def __init__(self, wheelbase=0.33, min_speed=-2.0, max_speed=8.0,
                 min_steer=-0.4, max_steer=0.4, initial_state: WorldState = None,
                 nav_horizon=10, nav_dt=0.1, nav_tolerance=0.5):
        self.wheelbase = wheelbase
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.min_steer = min_steer
        self.max_steer = max_steer
        self.state = initial_state or WorldState()

        self.nav_horizon = nav_horizon
        self.nav_dt = nav_dt
        self.nav_tolerance = nav_tolerance
        self._prev_solution = np.zeros(nav_horizon * 2)   # warm-start cache

        self._avoid_regions = []   # persistent, not a task: [{"point": (x,y), "radius": r}]

        self._active_handle = None
        self._active_target = None
        self._task_status = {}     # handle -> status string

    def calculate_dynamics(self, state: WorldState, controls: dict, dt: float) -> WorldState:
        speed = np.clip(controls["vel"], self.min_speed, self.max_speed)
        steer = np.clip(controls["steer"], self.min_steer, self.max_steer)

        vtheta = (speed / self.wheelbase) * np.tan(steer)
        theta = state.theta + vtheta * dt
        vx = speed * np.cos(theta)
        vy = speed * np.sin(theta)

        return WorldState(
            t=state.t + dt,
            x=state.x + vx * dt,
            y=state.y + vy * dt,
            theta=theta,
            vx=vx, vy=vy, vtheta=vtheta,
        )

    #=====# Capabilities #=====#
    def capabilities(self) -> dict:
        return {"move_to": "navigate", "avoid": "set_avoid"}

    def actuate(self, capability: str, params: dict) -> str:
        handle = str(uuid.uuid4())
        print(f"[Platform] actuate('{capability}', {params}) -> handle {handle[:8]}")

        if capability == "navigate":
            self._active_handle = handle
            self._active_target = params["target"]
            self._task_status[handle] = "received"

        elif capability == "set_avoid":
            self._avoid_regions.append(params)   # {"point":..., "radius":...}
            self._task_status[handle] = "success"   # instantaneous, not a duration task

        else:
            raise ValueError(f"Unknown capability: {capability}")

        return handle

    def poll_status(self, handle: str) -> dict:
        status = self._task_status.get(handle, "fail")

        if handle == self._active_handle and status in ("received", "in_progress"):
            dist = np.hypot(self.state.x - self._active_target[0],
                             self.state.y - self._active_target[1])
            if dist <= self.nav_tolerance:
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
    def _rollout_cost(self, control_seq, cost_fn):
        controls = control_seq.reshape(self.nav_horizon, 2)
        cost = 0.0
        s = self.state

        for vel, steer in controls:
            u = [vel, steer]
            s = self.calculate_dynamics(s, {"vel": vel, "steer": steer}, self.nav_dt)
            cost += cost_fn(s, u)
        return cost

    def compute_controls(self) -> dict:
        if self._active_target is None:
            return {"vel": 0.0, "steer": 0.0}

        target = self._active_target
        avoid = self._avoid_regions

        def platform_cost_fn(s, u):
            bearing = np.arctan2(target[1] - s.y, target[0] - s.x)
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
            e = np.array([s.x - target[0], s.y - target[1]])
            cost = e.T @ Q @ e

            for pt in avoid:
                point, radius = pt["point"], pt["radius"]
                d = np.hypot(s.x - point[0], s.y - point[1])
                cost += avoid_weight * max(0.0, radius - d)**2

                # Penalize heading directly at the obstacle, scaled by proximity
                avoid_bearing = np.arctan2(point[1] - s.y, point[0] - s.x)
                heading_toward_avoid = np.arctan2(np.sin(s.theta - avoid_bearing), np.cos(s.theta - avoid_bearing))
                proximity = 1.0 / (d + 0.5)   # stronger penalty the closer you are
                cost += avoid_heading_weight * proximity * np.cos(heading_toward_avoid)**2

            return cost

        def cost_fn(s, u):
            return platform_cost_fn(s, u) + standard_cost_fn(s, u) + mission_cost_fn(s, u)

        prev = self._prev_solution.reshape(self.nav_horizon, 2)
        x0 = np.vstack([prev[1:], prev[-1]]).flatten()

        bounds = [(self.min_speed, self.max_speed), (self.min_steer, self.max_steer)] * self.nav_horizon

        result = minimize(self._rollout_cost, x0, args=(cost_fn,), bounds=bounds, method="SLSQP")

        self._prev_solution = result.x
        vel, steer = result.x[0], result.x[1]
        return {"vel": vel, "steer": steer}