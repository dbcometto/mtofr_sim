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
    def calculate_dynamics(self, state: WorldState, controls: dict, dt: float,
                            max_speed_multiplier: float = 1.0) -> WorldState:
        """max_speed_multiplier scales the platform's own max speed (e.g. from an
        Environment's terrain lookup); 1.0 is a no-op for a Hardware with no such
        concept."""

    def send_controls(self, controls: dict) -> None:
        self._pending_controls = controls

    def read_state(self) -> WorldState:
        return self._sensor.read(self.state)

    def step_dynamics(self, dt: float, max_speed_multiplier: float = 1.0) -> None:
        self.state = self.calculate_dynamics(self.state, self._pending_controls, dt, max_speed_multiplier)


class Frontseater(ABC):
    """Platform-specific planning/control brain. Talks to its Hardware only
    through send_controls/read_state — never touches Hardware.state directly.
    Backseater never sends controls, only capability requests. `backseater` is
    set by Backseater's constructor (mirroring the platform_id cascade below) so a
    running capability can call query()/publish() on its own Backseater at any time."""
    hardware: Hardware
    backseater: object = None
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

    def default_mission_graph(self) -> dict:
        """The mission graph a Backseater falls back to when constructed with
        mission_graph=None -- what a platform boots into before a real mission is
        delegated to it. Base implementation is a bare, inert placeholder (a single
        node with no primitives, no transitions); a concrete Frontseater overrides
        this with whatever "safe idle" behavior actually suits its platform type
        (e.g. loitering for a UGV, hovering for a UAV)."""
        return {"knowledge": {}, "nodes": {"startup": {"primitives": {}}}, "edges": {}, "start": "startup"}

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
    def set_active_primitives(self, primitives: dict) -> None:
        """Tells this Frontseater which primitives should currently be running — the
        active mission-graph node's `{name: {"capability", "inputs", "outputs"}}` dict,
        called only when it differs from the last dict this Frontseater was given (a
        mission/node change included, since the new node's dict simply differs from the
        old one). `inputs`/`outputs` are field-name -> Knowledge-key maps, not resolved
        values. This Frontseater is fully responsible for everything downstream: noticing
        which primitive names are new (start them), which are no longer present (stop
        them), and which are unchanged (leave them running); running each one however it
        sees fit (this tick's update(), a thread, a state machine, real ROS nodes...); and
        calling self.backseater.query()/publish() on its own schedule to read/write actual
        data. There is no separate poll/status contract — introspection instead goes
        through describe_status() below."""

    @abstractmethod
    def describe_status(self) -> dict:
        """Returns {"overall": str, "primitives": {name: str}} — human-readable status
        text, entirely in this Frontseater's own words, for a visualization tool to
        display. Required (not by-convention) so every Frontseater is guaranteed to offer
        some introspection into what it's currently doing, however minimal (e.g.
        {"overall": "idle", "primitives": {}} is a valid response). Purely for display —
        Backseater never uses this for mission logic, only forwards it. `primitives`
        need not cover every name Backseater currently considers active; a missing name
        just means this Frontseater has nothing to say about it yet."""


class Environment(ABC):
    """Steps physical dynamics for a set of hardware instances"""

    @abstractmethod
    def step_dynamics_all(self, hardware: dict, dt: float) -> None:
        """hardware: eid -> Hardware. Mutates each hardware's state in place."""