"""Defines GroundPlaneState, the physical state of anything placed on the ground plane."""
from dataclasses import dataclass

import numpy as np

from mtofr.core.state import State


@dataclass
class GroundPlaneState(State):
    """2D pose and velocity in the world frame (origin at the map center, +y up), at rest
    at the origin unless given otherwise.  GroundPlaneEnv.state_type."""
    x: float = 0.0        # m, world frame
    y: float = 0.0        # m, world frame
    theta: float = 0.0    # rad, heading CCW from world +x

    vx: float = 0.0       # m/s, world frame
    vy: float = 0.0       # m/s, world frame
    vtheta: float = 0.0   # rad/s

    def pose2d(self) -> np.ndarray:
        """[x, y, theta] (m, m, rad)."""
        return np.array([self.x, self.y, self.theta])

    def vel2d(self) -> np.ndarray:
        """[vx, vy, vtheta] (m/s, m/s, rad/s)."""
        return np.array([self.vx, self.vy, self.vtheta])
