"""Defines hardware to be used with the ground_plane environment"""
from mtofr.world.base import Hardware, WorldState
from mtofr.world.ground_plane.dynamics import bicycle_step


class BicycleHardware(Hardware):
    """The MCU/actuator-equivalent layer for a UGV with bicycle dynamics.

    Controls:
    - "vel": desired forward speed in m/s
    - "steer": desired steering angle in rad around +z
    """
    def __init__(self, wheelbase=0.33, min_speed=-2.0, max_speed=8.0,
                 min_steer=-0.4, max_steer=0.4, initial_state: WorldState = None):
        super().__init__()
        self.wheelbase = wheelbase
        self.min_speed = min_speed
        self.max_speed = max_speed
        self.min_steer = min_steer
        self.max_steer = max_steer
        self.state = initial_state or WorldState()
        self._pending_controls = {"vel": 0.0, "steer": 0.0}

    def calculate_dynamics(self, state: WorldState, controls: dict, dt: float,
                            max_speed_multiplier: float = 1.0) -> WorldState:
        x, y, theta, vx, vy, vtheta = bicycle_step(
            state.x, state.y, state.theta, controls["vel"], controls["steer"],
            self.wheelbase, self.min_speed, self.max_speed * max_speed_multiplier,
            self.min_steer, self.max_steer, dt,
        )
        return WorldState(t=state.t + dt, x=x, y=y, theta=theta, vx=vx, vy=vy, vtheta=vtheta)