"""Defines the bicycle UGV platform's Hardware (bicycle dynamics, for the ground_plane environment)"""
from mtofr.environments.ground_plane.hardware import GroundPlaneHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.dynamics import bicycle_step
from mtofr.environments.ground_plane.state import GroundPlaneState


#========================================#
# Config
#========================================#

DEFAULT_WHEELBASE = 0.33   # m, F1Tenth-class
DEFAULT_MIN_SPEED = -2.0   # m/s
DEFAULT_MAX_SPEED = 8.0    # m/s
DEFAULT_MIN_STEER = -0.4   # rad
DEFAULT_MAX_STEER = 0.4    # rad
IDLE_CONTROLS = {"vel": 0.0, "steer": 0.0}   # stopped, wheels straight







#========================================#
# Hardware
#========================================#

class BicycleHardware(GroundPlaneHardware):
    """The MCU/actuator-equivalent layer for a UGV with bicycle dynamics. Uses
    GroundPlaneHardware's default (wheeled-vehicle) terrain response as-is.

    Controls:
    - "vel": desired forward speed in m/s
    - "steer": desired steering angle in rad around +z
    """
    idle_controls = IDLE_CONTROLS

    def __init__(self, wheelbase=DEFAULT_WHEELBASE, min_speed=DEFAULT_MIN_SPEED, max_speed=DEFAULT_MAX_SPEED,
                 min_steer=DEFAULT_MIN_STEER, max_steer=DEFAULT_MAX_STEER, initial_state: GroundPlaneState = None):
        """A stopped vehicle at `initial_state` (the origin by default) with the given limits."""
        super().__init__()
        self.wheelbase = wheelbase   # m
        self.min_speed = min_speed   # m/s
        self.max_speed = max_speed   # m/s
        self.min_steer = min_steer   # rad
        self.max_steer = max_steer   # rad
        self.state = initial_state or GroundPlaneState()

    def calculate_dynamics(self, state: GroundPlaneState, controls: dict, dt: float,
                            max_speed_multiplier: float = 1.0) -> GroundPlaneState:
        """One bicycle_step() of dt (s) under `controls`, with max speed scaled by the terrain multiplier."""
        x, y, theta, vx, vy, vtheta = bicycle_step(
            state.x, state.y, state.theta, controls["vel"], controls["steer"],
            self.wheelbase, self.min_speed, self.max_speed * max_speed_multiplier,
            self.min_steer, self.max_steer, dt,
        )
        return GroundPlaneState(t=state.t + dt, x=x, y=y, theta=theta, vx=vx, vy=vy, vtheta=vtheta)
