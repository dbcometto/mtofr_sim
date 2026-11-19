"""Defines StationaryHardware, the Hardware base for platforms that can live in any environment"""
from dataclasses import replace

from mtofr.core.hardware import Hardware
from mtofr.core.state import State


class StationaryHardware(Hardware):
    """Hardware that never moves, whatever controls it's sent, and so needs nothing
    from its environment, which is exactly what lets it live in any of them. It is
    still placed in its host environment's terms: it holds whatever State it's given
    (e.g. a GroundPlaneState, so it can be drawn on a map and later ranged for comms),
    and World checks that State matches the environment's state_type."""
    environment_type = None   # any environment

    def __init__(self, initial_state: State | None = None):
        """Placed at `initial_state` (a bare State, i.e. nowhere in particular, by default)."""
        super().__init__()
        self.state = initial_state or State()

    def step_dynamics(self, dt: float, environment=None) -> None:
        """Advances time only; every other field of the state (whatever its type) is kept."""
        self.state = replace(self.state, t=self.state.t + dt)
