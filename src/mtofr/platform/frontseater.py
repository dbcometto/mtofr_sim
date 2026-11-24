"""Defines Frontseater, the platform-specific planning/control layer."""
from mtofr.core.capability import Capability, CapabilityRegistry
from mtofr.core.hardware import Hardware
from mtofr.core.state import State
from mtofr.mission.graph import MissionGraph, CapabilityRequest


class Frontseater:
    """Platform-specific planning/control brain. Talks to its Hardware only
    through send_controls/read_state, never touching Hardware.state directly.
    Backseater never sends controls, only capability requests. `backseater` is
    set by Backseater's constructor (mirroring the platform_id cascade below) so a
    running capability can query()/publish() on its own Backseater at any time.

    A subclass lists its Capability classes in CAPABILITIES; this base owns everything
    else about running them (starting, ticking, stopping, status).  It overrides
    begin_controls()/finish_controls() or compute_controls() only if it moves."""
    CAPABILITIES: tuple[type[Capability], ...] = ()
    hardware: Hardware
    backseater: object = None   # set by Backseater's constructor
    _platform_id: str | None = None

    def __init__(self, hardware: Hardware, debug: bool = False):
        """Builds the capability registry from CAPABILITIES, with nothing running yet."""
        self.hardware = hardware
        self.debug = debug
        self._capability_registry = CapabilityRegistry(list(self.CAPABILITIES))
        self._running: dict[str, Capability] = {}   # request name -> its running Capability instance
        self._pending_controls: dict = {}   # set in begin_controls(), sent in finish_controls()





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

    def default_mission_graph(self) -> MissionGraph:
        """The mission graph a Backseater falls back to when constructed with
        mission_graph=None: what a platform boots into before a real mission is
        delegated to it. Base implementation is a bare, inert placeholder (a single
        node with no capability requests, no transitions); a concrete Frontseater overrides
        this with whatever "safe idle" behavior actually suits its platform type
        (e.g. loitering for a UGV, hovering for a UAV)."""
        return {"knowledge": {}, "nodes": {"startup": {"capabilities": {}}}, "edges": {}, "start": "startup"}

    def attach(self, world, window_root=None) -> None:
        """Called once by Platform.attach() after World (and, unless headless, the
        dashboard's Tk root as window_root) exist, for setup that can't happen at
        construction because those objects don't exist yet. Base implementation does
        nothing; a Frontseater that opens its own windows (e.g. MissionEditorFrontseater)
        overrides it, so main.py never needs to special-case a platform type."""

    def shutdown(self) -> None:
        """Stops every running capability (closing whatever they opened).  Platform.shutdown()
        calls this at exit; a Frontseater holding its own resources (e.g. a worker process)
        overrides it and calls super().shutdown() first."""
        self.set_active_capabilities({})





    #===============# Capabilities #===============#

    def capabilities(self) -> CapabilityRegistry:
        """Returns this platform's advertised capabilities: the query path a Backseater
        (and eventually a planner) uses instead of assuming what the platform can do."""
        return self._capability_registry

    def set_active_capabilities(self, capability_requests: dict[str, CapabilityRequest]) -> None:
        """Tells this Frontseater which capability requests should currently be running: the
        active mission-graph node's `{name: {"capability", "inputs", "outputs"}}` dict,
        called only when it differs from the last dict this Frontseater was given.  Diffs by
        name: a request that is gone, or whose request dict changed, is stopped; a new or
        changed one gets a fresh Capability instance and is started; an equal one keeps
        running untouched (e.g. a stopwatch spanning two nodes keeps counting)."""
        for name in list(self._running):
            if capability_requests.get(name) != self._running[name].request:
                self._running.pop(name).stop()
                if self.debug:
                    print(f"[Frontseater] '{name}' -> stopped")

        for name, capability_request in capability_requests.items():
            if name not in self._running:
                capability_class = self._capability_registry.get(capability_request["capability"])
                if capability_class is None:
                    raise ValueError(f"Unknown capability: {capability_request['capability']}")
                capability = capability_class(self, name, capability_request)
                capability.start()
                self._running[name] = capability
                if self.debug:
                    print(f"[Frontseater] '{name}' ({capability.ipl_type}) -> started")

    def tick_capabilities(self) -> None:
        """Runs one tick of every running capability.  Called every sim tick from begin_update()."""
        for capability in self._running.values():
            capability.tick()

    def describe_status(self) -> dict:
        """Returns {"overall": str, "capabilities": {name: str}}: human-readable status
        text for a visualization tool, from each running capability's status().  Purely
        for display: Backseater never uses this for mission logic, only forwards it."""
        overall = f"{len(self._running)} capability request(s) active" if self._running else "idle"
        return {"overall": overall,
                "capabilities": {name: capability.status() for name, capability in self._running.items()}}





    #===============# Controls #===============#

    def compute_controls(self, state: State) -> dict:
        """Derive current controls from whatever capabilities are running.  Default: idle
        (the Hardware's idle_controls), for a platform that never moves itself."""
        return dict(self.hardware.idle_controls)

    def begin_controls(self) -> None:
        """Starts this tick's control computation. Default: computes synchronously and
        stashes the result for finish_controls(). A Frontseater whose compute_controls is
        expensive (e.g. an MPC solve) can override this pair to dispatch the work to a
        worker process here and collect the result in finish_controls() instead, so World
        can start every platform's work before blocking on any one of them (see
        BicycleFrontseater)."""
        self._pending_controls = self.compute_controls(self.hardware.read_state())

    def finish_controls(self) -> None:
        """Completes this tick's control computation started by begin_controls() and
        applies it. Default: the result is already in hand, so this just applies it."""
        self.hardware.send_controls(self._pending_controls)

    def begin_update(self) -> None:
        """World's first per-tick call: ticks every running capability, then starts the
        controls (so controls always see this tick's capability state)."""
        self.tick_capabilities()
        self.begin_controls()

    def finish_update(self) -> None:
        """World's second per-tick call, after every platform's begin_update(): applies the controls."""
        self.finish_controls()

    def update(self) -> None:
        """Convenience for callers that don't need begin_update/finish_update split
        across other platforms' work (e.g. direct single-platform use in tests)."""
        self.begin_update()
        self.finish_update()
