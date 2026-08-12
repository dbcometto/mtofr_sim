"""Defines the ground_plane environment"""
from mtofr.world.base import Environment


class GroundPlaneEnv(Environment):
    """Infinite 2D plane, no bounds, no collisions."""

    def step_dynamics_all(self, hardware: dict, dt: float) -> None:
        for hardware_instance in hardware.values():
            hardware_instance.step_dynamics(dt)