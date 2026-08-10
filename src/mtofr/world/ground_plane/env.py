"""Defines the ground_plane environment"""
from mtofr.world.base import Environment


class GroundPlaneEnv(Environment):
    """Infinite 2D plane, no bounds, no collisions."""

    def step_dynamics_all(self, platforms: dict, dt: float) -> None:
        for platform in platforms.values():
            platform.step_dynamics(dt)