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
    """Owns physical state and its own active tasks. Computes its own controls
    internally each tick — Agent never sends controls, only capability requests."""
    state: WorldState

    @abstractmethod
    def calculate_dynamics(self, state: WorldState, controls: dict, dt: float) -> WorldState: ...

    @abstractmethod
    def compute_controls(self) -> dict:
        """Derive current controls from whatever tasks/avoid-state are active."""

    def step_dynamics(self, dt: float) -> None:
        controls = self.compute_controls()
        self.state = self.calculate_dynamics(self.state, controls, dt)

    @abstractmethod
    def capabilities(self) -> dict:
        """Maps IPL primitive type -> this platform's capability name."""

    @abstractmethod
    def actuate(self, capability: str, params: dict) -> str:
        """Start a capability task. Returns a handle. Status begins as 'received'."""

    @abstractmethod
    def poll_status(self, handle: str) -> dict:
        """Returns {"status": "received"|"in_progress"|"success"|"fail"|"timeout"}."""

    @abstractmethod
    def cancel(self, handle: str) -> None: ...


class Environment(ABC):
    """Steps physical dynamics for a set of platforms"""

    @abstractmethod
    def step_dynamics_all(self, platforms: dict, dt: float) -> None:
        """platforms: eid -> Platform. Mutates each platform's state in place."""