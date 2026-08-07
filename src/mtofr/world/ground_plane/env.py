"""Defines the ground_plane environment"""
from mtofr.world.base import Environment, WorldState


class GroundPlaneEnv(Environment):
    """Infinite 2D plane, no bounds, no collisions."""

    def __init__(self, platforms: dict, initial_states: dict = None):
        self.platforms = platforms       # eid -> Platform
        self.states = initial_states or {eid: WorldState() for eid in platforms}

    def step_all(self, controls: dict, dt: float) -> None:
        for eid, control in controls.items():
            self.states[eid] = self.platforms[eid].step(self.states[eid], control, dt)

    def get_states(self) -> dict:
        return self.states