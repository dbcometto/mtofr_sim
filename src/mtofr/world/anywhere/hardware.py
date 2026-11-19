"""Defines StationaryHardware, the Hardware base for platforms that can live in any environment"""
from mtofr.world.base import Hardware, WorldState


class StationaryHardware(Hardware):
    """Hardware that never moves, whatever controls it's sent, and so needs nothing
    from its environment, which is exactly what lets it live in any of them. It still
    has a real WorldState, so it can be placed (and drawn) somewhere on a map."""
    environment_type = None   # any environment

    def __init__(self, initial_state: WorldState = None):
        """Placed at `initial_state` (the origin by default)."""
        super().__init__()
        self.state = initial_state or WorldState()

    def step_dynamics(self, dt: float, environment=None) -> None:
        """Advances time only; position and heading never change."""
        self.state = WorldState(t=self.state.t + dt, x=self.state.x, y=self.state.y, theta=self.state.theta)
