"""Defines the ground_plane environment"""
from mtofr.world.base import Environment
from mtofr.maps import GroundMap


class GroundPlaneEnv(Environment):
    """2D plane whose terrain effects come from an optional GroundMap: a `blocking`
    cell stops a vehicle at its last valid position (velocity zeroed) instead of
    letting it pass through, and each cell's `speed_multiplier` scales the vehicle's
    own max speed for that step. With no GroundMap (the default), this is an
    unbounded plane with no terrain effects at all -- today's original behavior."""

    def __init__(self, ground_map: GroundMap | None = None):
        self.ground_map = ground_map

    def step_dynamics_all(self, hardware: dict, dt: float) -> None:
        for hardware_instance in hardware.values():
            if self.ground_map is None:
                hardware_instance.step_dynamics(dt)
                continue

            previous_state = hardware_instance.read_state()
            speed_multiplier = self.ground_map.speed_multiplier_at(previous_state.x, previous_state.y)
            hardware_instance.step_dynamics(dt, max_speed_multiplier=speed_multiplier)

            new_state = hardware_instance.read_state()
            if self.ground_map.is_blocked(new_state.x, new_state.y):
                # Stop at the last valid position/heading instead of entering the
                # blocked cell; time still advances, velocity is zeroed.
                previous_state.t = new_state.t
                previous_state.vx = previous_state.vy = previous_state.vtheta = 0.0
                hardware_instance.state = previous_state