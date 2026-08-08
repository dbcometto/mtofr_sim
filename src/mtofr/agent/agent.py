"""Defines an agent"""
import numpy as np
from scipy.optimize import minimize

class Agent:
    """Wraps a Platform with memory and mission tracking

    Mission spec: list of nodes, each a dict:
      {"target": (x, y), "avoid": [(x, y), ...]}
    "avoid" is optional per node (defaults to none).
    """


    def __init__(self, platform, memory, mission=None, horizon=10, dt=0.1, tolerance=0.5):
        self.platform = platform
        self.memory = memory
        self.mission = mission or []
        self.active_node = 0
        self.tolerance = tolerance
        self.horizon = horizon
        self.dt = dt
        self._prev_solution = np.zeros(horizon * 2)   # warm-start cache



    #=====# Helpers #=====#
    def _rollout_cost(self, control_seq, state, cost_fn):
        controls = control_seq.reshape(self.horizon, 2)
        cost = 0.0
        s = state

        for vel, steer in controls:
            u = [vel, steer]
            s = self.platform.step_dynamics(s, {"vel": vel, "steer": steer}, self.dt)
            cost += cost_fn(s, u)
        return cost



    #=====# Mission State Observation #=====#
    def update_mission(self, state) -> list:
        if not self.mission:
            return []

        node = self.mission[self.active_node]
        target = node["target"]

        if np.hypot(state.x - target[0], state.y - target[1]) <= self.tolerance:
            self.active_node = (self.active_node + 1) % len(self.mission)
            node = self.mission[self.active_node]

        return [node]



    #=====# Control Generation #=====#
    def plan(self, state) -> dict:
        active_primitives = self.update_mission(state)

        #-----# Cost Functions #-----#
        def platform_cost_fn(s, u: list):
            if not active_primitives:
                return 0.0

            target = active_primitives[0]["target"]
            bearing = np.arctan2(target[1] - s.y, target[0] - s.x)
            heading_error = np.arctan2(np.sin(s.theta - bearing), np.cos(s.theta - bearing))

            return 20 * heading_error**2

        def standard_cost_fn(s, u: list, R=None):
            u = np.array(u)

            if R is None:
                R = np.diag([1.0, 0.1])   # hardcoded diagonal weight for now

            return u.T @ R @ u

        def mission_cost_fn(s, u, Q=None, avoid_weight=100.0):
            if Q is None:
                Q = np.eye(2)   # hardcoded identity for now

            cost = 0.0
            for primitive in active_primitives:
                target = primitive["target"]
                e = np.array([s.x - target[0], s.y - target[1]])
                cost += e.T @ Q @ e

                for avoid in primitive.get("avoid", []):
                    point, radius = avoid["point"], avoid["radius"]
                    d = np.hypot(s.x - point[0], s.y - point[1])
                    cost += avoid_weight * max(0.0, radius - d)**2

            return cost

        def cost_fn(s, u: list):
            return platform_cost_fn(s, u) + standard_cost_fn(s, u) + mission_cost_fn(s, u)


        #-----# MPC #-----#
        prev = self._prev_solution.reshape(self.horizon, 2)
        x0 = np.vstack([prev[1:], prev[-1]]).flatten()

        bounds = [(self.platform.min_speed, self.platform.max_speed),
                  (self.platform.min_steer, self.platform.max_steer)] * self.horizon

        result = minimize(self._rollout_cost, x0, args=(state, cost_fn), bounds=bounds, method="SLSQP")

        self._prev_solution = result.x
        vel, steer = result.x[0], result.x[1]
        return {"vel": vel, "steer": steer}