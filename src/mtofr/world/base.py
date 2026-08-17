"""Defines the core physical interfaces: WorldState, Hardware, Frontseater, Environment."""
from abc import ABC, abstractmethod
import numpy as np
from mtofr.capability.capability import CapabilityRegistry


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
        self.platform_id: str | None = None

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
    _platform_id: str | None = None

    @property
    def platform_id(self) -> str | None:
        return self._platform_id

    @platform_id.setter
    def platform_id(self, value: str | None) -> None:
        self._platform_id = value
        self.hardware.platform_id = value

    @abstractmethod
    def compute_controls(self, state: WorldState) -> dict:
        """Derive current controls from whatever tasks/avoid-state are active."""

    def begin_update(self) -> None:
        """Starts this tick's control computation. Default: computes synchronously and
        stashes the result for finish_update(). A Frontseater whose compute_controls is
        expensive (e.g. an MPC solve) can override this pair to dispatch the work to a
        worker process here and collect the result in finish_update() instead, so World
        can start every platform's work before blocking on any one of them -- see
        BicycleFrontseater for the concrete case this exists for."""
        self._pending_controls = self.compute_controls(self.hardware.read_state())

    def finish_update(self) -> None:
        """Completes this tick's control computation started by begin_update() and
        applies it. Default: the result is already in hand (begin_update computed it
        synchronously), so this just applies it."""
        self.hardware.send_controls(self._pending_controls)

    def update(self) -> None:
        """Convenience for callers that don't need begin_update/finish_update split
        across other platforms' work (e.g. direct single-platform use in tests)."""
        self.begin_update()
        self.finish_update()

    @abstractmethod
    def capabilities(self) -> CapabilityRegistry:
        """Returns this platform's advertised capabilities — the query path a Backseater
        (and eventually a planner) uses instead of assuming what the platform can do."""

    @abstractmethod
    def start_capability(self, capability: str, inputs: dict) -> str:
        """Start a capability task. Returns a handle. Status begins as 'received'."""

    @abstractmethod
    def poll_status(self, handle: str) -> dict:
        """Returns {"status": "received"|"in_progress"|"success"|"fail"|"timeout",
        "outputs": {name: value, ...}}. `outputs` may include any subset of the
        capability's declared OutputSpecs, whichever are meaningful for the current status."""

    @abstractmethod
    def cancel(self, handle: str) -> None: ...


class Environment(ABC):
    """Steps physical dynamics for a set of hardware instances"""

    @abstractmethod
    def step_dynamics_all(self, hardware: dict, dt: float) -> None:
        """hardware: eid -> Hardware. Mutates each hardware's state in place."""