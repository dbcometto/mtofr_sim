"""Defines the ground_plane environment"""
from mtofr.world.base import Environment


class GroundPlaneEnv(Environment):
    """Infinite 2D plane, no bounds, no collisions."""

    def step_dynamics_all(self, platforms: dict, controls: dict, dt: float) -> dict:
        return {
            eid: platform.step_dynamics(platform.state, controls[eid], dt)
            for eid, platform in platforms.items()
        }