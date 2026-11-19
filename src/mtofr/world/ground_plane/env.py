"""Defines the ground_plane environment"""
from mtofr.world.base import Environment
from mtofr.maps import GroundMap


class GroundPlaneEnv(Environment):
    """2D plane whose terrain comes from an optional GroundMap, answering the terrain
    queries a GroundPlaneHardware steps itself against: is_blocked() and
    speed_multiplier_at(). Passive -- what a blocked cell or a slow surface actually
    does to a vehicle is that vehicle's own step_dynamics(). With no GroundMap (the
    default), this is an unbounded plane with no terrain effects at all."""

    def __init__(self, ground_map: GroundMap | None = None):
        self.ground_map = ground_map

    def speed_multiplier_at(self, x: float, y: float) -> float:
        """The terrain's max-speed multiplier at (x, y); 1.0 (no effect) with no map."""
        return 1.0 if self.ground_map is None else self.ground_map.speed_multiplier_at(x, y)

    def is_blocked(self, x: float, y: float) -> bool:
        """Whether (x, y) is impassable terrain (or off the map); never blocked with no map."""
        return False if self.ground_map is None else self.ground_map.is_blocked(x, y)
