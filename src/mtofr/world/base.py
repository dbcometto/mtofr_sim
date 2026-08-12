"""Defines the core physical interfaces: WorldState, Hardware, Frontseater, Environment."""
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


class PerfectSensor:
    """Reports ground-truth state exactly. Placeholder seam for a future
    noisy/partial-observability sensor model, without changing Hardware's interface."""
    def read(self, state: WorldState) -> WorldState:
        return state


class Hardware(ABC):
    """Owns physical state and executes low-level controls each tick — the
    MCU/actuator-equivalent layer. Knows nothing about capabilities or missions;
    only ever sees raw controls in and raw (sensed) state out."""
    state: WorldState

    def __init__(self):
        self._sensor = PerfectSensor()
        self._pending_controls: dict = {}

    @abstractmethod
    def calculate_dynamics(self, state: WorldState, controls: dict, dt: float) -> WorldState: ...

    def send_controls(self, controls: dict) -> None:
        self._pending_controls = controls

    def read_state(self) -> WorldState:
        return self._sensor.read(self.state)

    def step_dynamics(self, dt: float) -> None:
        self.state = self.calculate_dynamics(self.state, self._pending_controls, dt)


class Frontseater(ABC):
    """Platform-specific planning/control brain. Talks to its Hardware only
    through send_controls/read_state — never touches Hardware.state directly.
    Backseater never sends controls, only capability requests."""
    hardware: Hardware

    @abstractmethod
    def compute_controls(self, state: WorldState) -> dict:
        """Derive current controls from whatever tasks/avoid-state are active."""

    def update(self) -> None:
        controls = self.compute_controls(self.hardware.read_state())
        self.hardware.send_controls(controls)

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
    """Steps physical dynamics for a set of hardware instances"""

    @abstractmethod
    def step_dynamics_all(self, hardware: dict, dt: float) -> None:
        """hardware: eid -> Hardware. Mutates each hardware's state in place."""