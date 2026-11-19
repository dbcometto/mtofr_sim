"""Defines GroundPlaneHardware, the Hardware base every ground_plane vehicle subclasses"""
from abc import abstractmethod

from mtofr.core.hardware import Hardware
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.state import GroundPlaneState


class GroundPlaneHardware(Hardware):
    """A vehicle that lives in a GroundPlaneEnv. Subclasses implement pure
    calculate_dynamics(); the default step_dynamics() is a wheeled vehicle's terrain
    response (slowed by the surface underneath it, stopped dead at a blocked cell),
    which a vehicle reacting to terrain differently overrides."""
    environment_type = GroundPlaneEnv
    state: GroundPlaneState

    @abstractmethod
    def calculate_dynamics(self, state: GroundPlaneState, controls: dict, dt: float,
                            max_speed_multiplier: float = 1.0) -> GroundPlaneState:
        """Pure: the state after dt (s), with this vehicle's own max speed scaled by max_speed_multiplier."""

    def step_dynamics(self, dt: float, environment: GroundPlaneEnv) -> None:
        """Steps under the terrain's speed multiplier at the current position; if that
        lands in a blocked cell, keeps the previous pose with velocity zeroed instead:
        an approximate "stop at the boundary," fine at the map's raster resolution."""
        # Ground truth, not read_state(): physics shouldn't see the world through the sensor.
        previous_state = self.state
        speed_multiplier = environment.speed_multiplier_at(previous_state.x, previous_state.y)
        new_state = self.calculate_dynamics(previous_state, self._pending_controls, dt, speed_multiplier)
        if environment.is_blocked(new_state.x, new_state.y):
            new_state = GroundPlaneState(t=new_state.t, x=previous_state.x, y=previous_state.y,
                                         theta=previous_state.theta)
        self.state = new_state
