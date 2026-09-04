"""Defines frontseaters to be used with the ground_plane environment"""
import multiprocessing
import numpy as np
from mtofr.world.base import Frontseater, WorldState
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.mpc import run_mpc_worker
from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import Location


class BicycleFrontseater(Frontseater):
    """The planning/control brain for a UGV with bicycle dynamics. Runs its internal MPC
    in a dedicated, persistent worker process (see mtofr.world.ground_plane.mpc) so that
    multiple platforms' solves can overlap instead of serializing on one core -- this
    Frontseater never touches Hardware.state directly, only send_controls/read_state.
    set_active_primitives() is the one entry point Backseater calls; it farms out to
    _start/_stop/_step per primitive, each a plain if/elif over the three capabilities
    below -- a template for what implementing a new Frontseater looks like, not a
    general-purpose capability framework."""

    #==========# Construction #==========#
    def __init__(self, hardware: BicycleHardware, nav_horizon=10, nav_dt=0.1, debug=False):
        #-----# Construction parameters #-----#
        self.hardware = hardware
        self.nav_horizon = nav_horizon
        self.nav_dt = nav_dt
        self.debug = debug

        #-----# Admin / cascaded state #-----#
        self.backseater = None   # set by Backseater's constructor
        self._awaiting_response = False   # set in begin_update(), consumed in finish_update()

        #-----# MPC target state #-----#
        # Single-target only: at most one move_to primitive's target/tolerance drives
        # the MPC solve at a time, regardless of how many primitives are active.
        self._active_target = None      # Location, live-queried each step while a move_to is active
        self._active_tolerance = None   # float, live-queried each step while a move_to is active

        #-----# Capability bookkeeping #-----#
        self._active_primitive_specs = {}    # name -> {"capability", "inputs", "outputs"}, as given by Backseater
        self._primitive_runtime_state = {}   # name -> capability-specific state dict, owned by _start/_stop/_step

        self._capability_registry = CapabilityRegistry([
            Capability(
                ipl_type="move_to",
                description="Navigate to a target location until within tolerance, using the internal MPC.",
                inputs=(
                    ParamSpec("target", Location, "Location to navigate to"),
                    ParamSpec("tolerance", float, "Distance within which the target counts as reached, in meters"),
                ),
                outputs=(ParamSpec("arrived", bool, "True once within tolerance of the current target"),),
            ),
            Capability(
                ipl_type="avoid",
                description="Add a persistent circular avoid-region; instantaneous, not a duration task.",
                inputs=(
                    ParamSpec("point", Location, "Center of the avoid-region"),
                    ParamSpec("radius", float, "Avoid-region radius in meters"),
                ),
                outputs=(ParamSpec("registered", bool, "True once the avoid-region has been registered"),),
            ),
            Capability(
                ipl_type="stopwatch",
                description="Reports simulation time (seconds) elapsed since this capability instance "
                            "was (re)started; resets to zero every time it is started again.",
                inputs=(),
                outputs=(ParamSpec("elapsed_time", float, "Seconds since this stopwatch instance started"),),
            ),
        ])

        #-----# MPC worker process #-----#
        # The worker holds the warm-start solution and avoid-region list resident for
        # this platform's lifetime -- see run_mpc_worker. daemon=True so a forgotten
        # shutdown() doesn't keep the interpreter alive on exit.
        self._request_queue = multiprocessing.Queue()
        self._response_queue = multiprocessing.Queue()
        self._worker_process = multiprocessing.Process(
            target=run_mpc_worker,
            args=(self._request_queue, self._response_queue, nav_horizon, nav_dt,
                  hardware.wheelbase, hardware.min_speed, hardware.max_speed,
                  hardware.min_steer, hardware.max_steer),
            daemon=True,
        )
        self._worker_process.start()


    #==========# Capability discovery #==========#

    def capabilities(self) -> CapabilityRegistry:
        return self._capability_registry

    def default_mission_graph(self) -> dict:
        """Boots this platform into an idle loiter -- just runs the stopwatch
        capability with nothing bound to it -- until a real mission is delegated."""
        return {
            "knowledge": {
                "startup/elapsed_time": {"type": float, "value": 0.0},
            },
            "nodes": {
                "startup": {"primitives": {
                    "loiter": {"capability": "stopwatch", "inputs": {},
                               "outputs": {"elapsed_time": "startup/elapsed_time"}},
                }},
            },
            "edges": {},
            "start": "startup",
        }


    #==========# Capability lifecycle #==========#

    def set_active_primitives(self, primitives: dict) -> None:
        """The one entry point Backseater calls. Diffs `primitives` against what's
        currently running, by name: a new name is started, a name no longer present is
        stopped, an unchanged name is left alone. Running itself happens per-tick in
        _step_active_primitives(), called from begin_update()."""
        for name in list(self._active_primitive_specs):
            if name not in primitives:
                self._stop(name)

        for name, primitive in primitives.items():
            if name not in self._active_primitive_specs:
                self._start(name, primitive)

        self._active_primitive_specs = dict(primitives)

    def _start(self, name: str, primitive: dict) -> None:
        capability, inputs = primitive["capability"], primitive.get("inputs", {})

        if capability == "move_to":
            self._active_target = self.backseater.query("knowledge", inputs["target"])
            self._active_tolerance = self.backseater.query("knowledge", inputs["tolerance"])
            self._primitive_runtime_state[name] = {"arrived": False}

        elif capability == "avoid":
            point = self.backseater.query("knowledge", inputs["point"])
            radius = self.backseater.query("knowledge", inputs["radius"])
            self._request_queue.put({"type": "add_avoid_region", "point_x": point.x, "point_y": point.y, "radius": radius})
            self._primitive_runtime_state[name] = {}   # instantaneous, not a duration task

        elif capability == "stopwatch":
            self._primitive_runtime_state[name] = {"start_time": self.hardware.read_state().t}

        else:
            raise ValueError(f"Unknown capability: {capability}")

        if self.debug:
            print(f"[Frontseater] '{name}' ({capability}) -> started")

    def _stop(self, name: str) -> None:
        capability = self._active_primitive_specs[name]["capability"]

        if capability == "move_to":
            self._active_target = None
            self._active_tolerance = None

        del self._primitive_runtime_state[name]

        if self.debug:
            print(f"[Frontseater] '{name}' ({capability}) -> stopped")

    def _step_active_primitives(self) -> None:
        """Runs one tick of every currently active primitive, querying/publishing
        through this platform's own Backseater. Called every tick from begin_update()."""
        for name, primitive in self._active_primitive_specs.items():
            capability, inputs = primitive["capability"], primitive.get("inputs", {})
            outputs = primitive.get("outputs", {})
            state = self._primitive_runtime_state[name]

            if capability == "move_to":
                self._active_target = self.backseater.query("knowledge", inputs["target"])
                self._active_tolerance = self.backseater.query("knowledge", inputs["tolerance"])
                current_state = self.hardware.read_state()
                distance = np.hypot(current_state.x - self._active_target.x, current_state.y - self._active_target.y)
                state["arrived"] = bool(distance <= self._active_tolerance)
                if "arrived" in outputs:
                    self.backseater.publish("knowledge", outputs["arrived"], state["arrived"])

            elif capability == "avoid":
                if "registered" in outputs:
                    self.backseater.publish("knowledge", outputs["registered"], True)

            elif capability == "stopwatch":
                elapsed_time = self.hardware.read_state().t - state["start_time"]
                if "elapsed_time" in outputs:
                    self.backseater.publish("knowledge", outputs["elapsed_time"], elapsed_time)


    #==========# Status introspection #==========#

    def describe_status(self) -> dict:
        """Purely for display -- see Frontseater.describe_status."""
        active_primitives = self._active_primitive_specs
        overall = f"{len(active_primitives)} primitive(s) active" if active_primitives else "idle"

        primitive_lines = {}
        for name, primitive in active_primitives.items():
            capability = primitive["capability"]
            state = self._primitive_runtime_state[name]

            if capability == "move_to":
                primitive_lines[name] = "arrived" if state["arrived"] else "en route"
            elif capability == "avoid":
                primitive_lines[name] = "registered"
            elif capability == "stopwatch":
                primitive_lines[name] = f"{self.hardware.read_state().t - state['start_time']:.1f}s elapsed"

        return {"overall": overall, "primitives": primitive_lines}


    #==========# Controls (internal MPC) #==========#

    def compute_controls(self, state: WorldState) -> dict:
        """Synchronous, single-process reference path: only ever idle here, since the
        real per-tick solve goes through begin_update()/finish_update() and the worker
        process instead (see World.step(), which calls those, not this). Kept so
        BicycleFrontseater still satisfies Frontseater's abstract interface directly."""
        if self._active_target is None:
            return {"vel": 0.0, "steer": 0.0}
        raise NotImplementedError(
            "BicycleFrontseater solves the MPC via its worker process through "
            "begin_update()/finish_update(), not by calling compute_controls() directly."
        )

    def begin_update(self) -> None:
        """Dispatches this tick's MPC solve to the worker process without blocking on the
        result. Overrides Frontseater's synchronous default because the solve is
        expensive: World.step() calls begin_update() for every platform first, then
        finish_update() for every platform, so every platform's request is already
        in-flight on its own worker process before any one of them is waited on --
        letting independent platforms' solves overlap instead of serializing on one core.
        Also steps every active primitive (capability queries/publishes), since this is
        the same per-tick cadence controls are computed on. If there's no active target,
        there's nothing to solve -- skip the dispatch and let finish_update() send zero
        controls."""
        self._step_active_primitives()

        if self._active_target is None:
            self._awaiting_response = False
            return

        state = self.hardware.read_state()
        self._request_queue.put({
            "type": "compute",
            "state": (state.x, state.y, state.theta),
            "target": (self._active_target.x, self._active_target.y),
        })
        self._awaiting_response = True

    def finish_update(self) -> None:
        """Collects the result begin_update() dispatched and applies it to Hardware.
        Blocks on this platform's own response queue -- but only after every platform's
        begin_update() has already run, so the blocking wait here overlaps with every
        other platform's solve rather than each platform waiting in turn."""
        if not self._awaiting_response:
            self.hardware.send_controls({"vel": 0.0, "steer": 0.0})
            return

        result = self._response_queue.get()
        self.hardware.send_controls({"vel": result["vel"], "steer": result["steer"]})


    #==========# Lifecycle #==========#

    def shutdown(self) -> None:
        """Stops this platform's worker process. Not called automatically by anything
        in World/Backseater -- a caller (e.g. main.py) that started this Frontseater is
        responsible for calling it before exit."""
        if not self._worker_process.is_alive():
            return
        self._request_queue.put({"type": "shutdown"})
        self._worker_process.join(timeout=2.0)

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass