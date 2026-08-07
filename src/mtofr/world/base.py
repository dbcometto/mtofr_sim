"""Defines the core physical interfaces: WorldState, Platform, Environment."""
from abc import ABC, abstractmethod
import numpy as np


class WorldState:
    """Shared physical state interface"""
    def __init__(self, t=0.0, x=0.0, y=0.0, theta=0.0, vx=0.0, vy=0.0, vtheta=0.0):
        self.t = t

        self.x = x
        self.y = y
        self.theta = theta

        self.vx = vx
        self.vy = vy
        self.vtheta = vtheta

    def __repr__(self):
        return (f"WorldState(t={self.t}, x={self.x}, y={self.y}, theta={self.theta}, "
                f"vx={self.vx}, vy={self.vy}, vtheta={self.vtheta})")

    def pose2d(self) -> np.ndarray:
        return np.array([self.x, self.y, self.theta])

    def vel2d(self) -> np.ndarray:
        return np.array([self.vx, self.vy, self.vtheta])


class Platform(ABC):
    """Pure physical dynamics, stateful"""
    state: WorldState

    @abstractmethod
    def step_dynamics(self, state: WorldState, controls: dict, dt: float) -> WorldState: ...


class Environment(ABC):
    """Steps physical dynamics for a set of platforms"""

    @abstractmethod
    def step_dynamics_all(self, platforms: dict, controls: dict, dt: float) -> dict:
        """platforms: eid -> Platform, controls: eid -> control dict.
        Returns eid -> new WorldState."""