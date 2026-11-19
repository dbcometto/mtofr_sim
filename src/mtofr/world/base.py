"""Defines the core physical interfaces: WorldState, Hardware, Frontseater, Environment."""
from abc import ABC, abstractmethod
import numpy as np
from mtofr.capability.capability import CapabilityRegistry


#========================================#
# State and Sensing
#========================================#

class WorldState:
    """Shared physical state interface"""
    def __init__(self, t=0.0, x=0.0, y=0.0, theta=0.0, vx=0.0, vy=0.0, vtheta=0.0):
        """A state at rest at the origin unless given otherwise."""
        self.t = t   # s, sim time

        self.x = x            # m, world frame
        self.y = y            # m, world frame
        self.theta = theta    # rad, heading CCW from world +x

        self.vx = vx          # m/s, world frame
        self.vy = vy          # m/s, world frame
        self.vtheta = vtheta  # rad/s

    def __repr__(self):
        """Shows every field."""
        return (f"WorldState(t={self.t}, x={self.x}, y={self.y}, theta={self.theta}, "
                f"vx={self.vx}, vy={self.vy}, vtheta={self.vtheta})")

    def pose2d(self) -> np.ndarray:
        """[x, y, theta] (m, m, rad)."""
        return np.array([self.x, self.y, self.theta])

    def vel2d(self) -> np.ndarray:
        """[vx, vy, vtheta] (m/s, m/s, rad/s)."""
        return np.array([self.vx, self.vy, self.vtheta])


class PerfectSensor:
    """Reports ground-truth state exactly. Placeholder seam for a future
    noisy/partial-observability sensor model, without changing Hardware's interface."""
    def read(self, state: WorldState) -> WorldState:
        """Returns `state` unchanged."""
        return state







#========================================#
# Platform Layers
#========================================#

class Hardware(ABC):
    """Owns physical state and executes low-level controls each tick: the
    MCU/actuator-equivalent layer, including its own dynamics. step_dynamics() queries
    the (passive) Environment for whatever it needs, since how the world affects a
    vehicle is that vehicle's business. Knows nothing about capabilities or missions.
    Every subclass must set `environment_type` (the Environment class it can live in,
    or None for any), which World checks at construction."""
    # NOTE: environment_type deliberately has no default here, so forgetting it is an
    # error rather than a silent "lives anywhere".
    state: WorldState
    environment_type: type | None

    def __init__(self):
        """Sets up the sensor and empty pending controls; the subclass sets `state`."""
        self._sensor = PerfectSensor()
        self._pending_controls: dict = {}
        self.platform_id: str | None = None

    @abstractmethod
    def step_dynamics(self, dt: float, environment: "Environment") -> None:
        """Advances self.state by dt (s) under the last controls sent, in this environment."""

    def send_controls(self, controls: dict) -> None:
        """Stores `controls` for the next step_dynamics()."""
        self._pending_controls = controls

    def read_state(self) -> WorldState:
        """The state as seen through this hardware's sensor."""
        return self._sensor.read(self.state)


class Frontseater(ABC):
    """Platform-specific planning/control brain. Talks to its Hardware only
    through send_controls/read_state, never touching Hardware.state directly.
    Backseater never sends controls, only capability requests. `backseater` is
    set by Backseater's constructor (mirroring the platform_id cascade below) so a
    running capability can call query()/publish() on its own Backseater at any time."""
    hardware: Hardware
    backseater: object = None
    _platform_id: str | None = None

    #===============# Identity #===============#

    @property
    def platform_id(self) -> str | None:
        """This platform's id, cascaded down from the Backseater."""
        return self._platform_id

    @platform_id.setter
    def platform_id(self, value: str | None) -> None:
        """Sets the id here and cascades it on to the Hardware."""
        self._platform_id = value
        self.hardware.platform_id = value





    #===============# Setup #===============#

    def default_mission_graph(self) -> dict:
        """The mission graph a Backseater falls back to when constructed with
        mission_graph=None: what a platform boots into before a real mission is
        delegated to it. Base implementation is a bare, inert placeholder (a single
        node with no primitives, no transitions); a concrete Frontseater overrides
        this with whatever "safe idle" behavior actually suits its platform type
        (e.g. loitering for a UGV, hovering for a UAV)."""
        return {"knowledge": {}, "nodes": {"startup": {"primitives": {}}}, "edges": {}, "start": "startup"}

    def attach(self, world, window_root=None) -> None:
        """Called once by Platform.attach() after World (and, unless headless, the
        dashboard's Tk root as window_root) exist, for setup that can't happen at
        construction because those objects don't exist yet. Base implementation does
        nothing; a Frontseater that opens its own windows (e.g. MissionEditorFrontseater)
        overrides it, so main.py never needs to special-case a platform type."""





    #===============# Controls #===============#

    @abstractmethod
    def compute_controls(self, state: WorldState) -> dict:
        """Derive current controls from whatever tasks/avoid-state are active."""

    def begin_update(self) -> None:
        """Starts this tick's control computation. Default: computes synchronously and
        stashes the result for finish_update(). A Frontseater whose compute_controls is
        expensive (e.g. an MPC solve) can override this pair to dispatch the work to a
        worker process here and collect the result in finish_update() instead, so World
        can start every platform's work before blocking on any one of them (see
        BicycleFrontseater)."""
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





    #===============# Capabilities #===============#

    @abstractmethod
    def capabilities(self) -> CapabilityRegistry:
        """Returns this platform's advertised capabilities: the query path a Backseater
        (and eventually a planner) uses instead of assuming what the platform can do."""

    @abstractmethod
    def set_active_primitives(self, primitives: dict) -> None:
        """Tells this Frontseater which primitives should currently be running: the
        active mission-graph node's `{name: {"capability", "inputs", "outputs"}}` dict,
        called only when it differs from the last dict this Frontseater was given (a
        mission/node change included, since the new node's dict simply differs from the
        old one). `inputs`/`outputs` are field-name -> Knowledge-key maps, not resolved
        values. This Frontseater is fully responsible for everything downstream: noticing
        which primitive names are new (start them), which are no longer present (stop
        them), and which are unchanged (leave them running); running each one however it
        sees fit (this tick's update(), a thread, a state machine, real ROS nodes...); and
        calling self.backseater.query()/publish() on its own schedule to read/write actual
        data. There is no separate poll/status contract; introspection instead goes
        through describe_status() below."""

    @abstractmethod
    def describe_status(self) -> dict:
        """Returns {"overall": str, "primitives": {name: str}}: human-readable status
        text, entirely in this Frontseater's own words, for a visualization tool to
        display. Required (not by-convention) so every Frontseater is guaranteed to offer
        some introspection into what it's currently doing, however minimal (e.g.
        {"overall": "idle", "primitives": {}} is a valid response). Purely for display:
        Backseater never uses this for mission logic, only forwards it. `primitives`
        need not cover every name Backseater currently considers active; a missing name
        just means this Frontseater has nothing to say about it yet."""







#========================================#
# Environment
#========================================#

class Environment(ABC):
    """A passive description of the world (terrain, bounds, ...) that each Hardware
    queries while stepping its own dynamics; it never steps anything itself. Each
    concrete environment defines whatever queries its vehicles need (e.g.
    GroundPlaneEnv.is_blocked()), alongside the Hardware base those vehicles subclass."""
