"""Defines the environment and platform interfaces"""
from abc import ABC, abstractmethod
import numpy as np


class WorldState:
    """Shared state interface"""
    def __init__(self, t=0.0, x=0.0, y=0.0, theta=0.0, vx=0.0, vy=0.0, vtheta=0.0):
        self.t = t

        # Position
        self.x = x
        self.y = y
        self.theta = theta

        # Velocities in world frame
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
    """Handles platform logic"""

    @abstractmethod
    def step(self, state: WorldState, controls: dict, dt: float) -> WorldState: ...


class Environment(ABC):
    """Manages platform data and steps the world"""
    platforms: dict
    states: dict

    @abstractmethod
    def step_all(self, controls: dict, dt: float) -> None: ...

    @abstractmethod
    def get_states(self) -> dict: ...

