"""Defines platforms to be used with the ground_plane environment"""
import numpy as np
from mtofr.world.base import Platform, WorldState


class BicycleUGV(Platform):
    """A UGV with bicycle dynamics

    Controls:
    - "vel": desired forward speed in m/s
    - "steer": desired steering angle in rad around +z
    """
    def __init__(self, wheelbase=0.33, min_speed=-2.0, max_speed=8.0,
                 min_steer=-0.4, max_steer=0.4, initial_state: WorldState = None):
        self.wheelbase = wheelbase
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.min_steer = min_steer
        self.max_steer = max_steer
        self.state = initial_state or WorldState()

    def step_dynamics(self, state: WorldState, controls: dict, dt: float) -> WorldState:
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