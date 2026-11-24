"""Defines the bicycle UGV platform's Frontseater (MPC navigation, for the ground_plane environment)"""
import multiprocessing
import numpy as np
from mtofr.core.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import Location, Pose
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware, IDLE_CONTROLS
from mtofr.environments.ground_plane.platforms.bicycle_ugv.mpc import run_mpc_worker
from mtofr.environments.ground_plane.state import GroundPlaneState
from mtofr.platform.frontseater import Frontseater


#========================================#
# Config
#========================================#

DEFAULT_NAV_HORIZON = 10   # MPC rollout steps
DEFAULT_NAV_DT = 0.1       # s per MPC rollout step
WORKER_JOIN_TIMEOUT = 2.0  # s to wait for the MPC worker to exit at shutdown







#========================================#
# Frontseater
#========================================#

class BicycleFrontseater(Frontseater):
    """The planning/control brain for a UGV with bicycle dynamics. Runs its internal MPC
    in a dedicated, persistent worker process (see the sibling mpc module) so that
    multiple platforms' solves can overlap instead of serializing on one core -- this
    Frontseater never touches Hardware.state directly, only send_controls/read_state.
    set_active_capabilities() is the one entry point Backseater calls; it farms out to
    _start/_stop/_step per capability request, each a plain if/elif over the capabilities
    below -- a template for what implementing a new Frontseater looks like, not a
    general-purpose capability framework."""

    #===============# Construction #===============#

    def __init__(self, hardware: BicycleHardware, nav_horizon=DEFAULT_NAV_HORIZON, nav_dt=DEFAULT_NAV_DT,
                 debug: bool = False):
        """Registers the capabilities and starts this platform's MPC worker process."""
        #----------# Construction Parameters #----------#

        self.hardware = hardware
        self.nav_horizon = nav_horizon
        self.nav_dt = nav_dt   # s
        self.debug = debug



        #----------# Admin / Cascaded State #----------#

        self.backseater = None   # set by Backseater's constructor
        self._awaiting_response = False   # set in begin_update(), consumed in finish_update()



        #----------# MPC Target State #----------#

        # Single-target only: at most one move_to capability request's target/tolerance drives
        # the MPC solve at a time, regardless of how many capability requests are active.
        self._active_target = None      # Location (m, world frame), live-queried each step while a move_to is active
        self._active_tolerance = None   # float (m), live-queried each step while a move_to is active



        #----------# Capability Bookkeeping #----------#

        self._active_capability_requests = {}   # name -> {"capability", "inputs", "outputs"}, as given by Backseater
        self._request_runtime_state = {}        # name -> capability-specific state dict, owned by _start/_stop/_step

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
            Capability(
                ipl_type="sense_pose",
                description="Runs the pose sensor, publishing this platform's sensed pose every tick; "
                            "never completes.",
                inputs=(),
                outputs=(ParamSpec("pose", Pose, "This platform's sensed pose, updated every tick"),),
            ),
        ])



        #----------# MPC Worker Process #----------#

        # The worker holds the warm-start solution and avoid-region list resident for
        # this platform's lifetime (see run_mpc_worker). daemon=True so a forgotten
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





    #===============# Capability Discovery #===============#

    def capabilities(self) -> CapabilityRegistry:
        """move_to, avoid, stopwatch, and sense_pose."""
        return self._capability_registry

    def default_mission_graph(self) -> dict:
        """Boots this platform into an idle loiter -- runs the stopwatch, plus the pose
        sensor publishing to "<platform_id>/pose" so peers see where it is -- until a
        real mission is delegated."""
        pose_key = f"{self.platform_id}/pose"
        return {
            "knowledge": {
                "startup/elapsed_time": {"type": float, "value": 0.0},
                pose_key: {"type": Pose, "value": self._sense_pose()},
            },
            "nodes": {
                "startup": {"capabilities": {
                    "loiter": {"capability": "stopwatch", "inputs": {},
                               "outputs": {"elapsed_time": "startup/elapsed_time"}},
                    "pose": {"capability": "sense_pose", "inputs": {}, "outputs": {"pose": pose_key}},
                }},
            },
            "edges": {},
            "start": "startup",
        }





    #===============# Capability Lifecycle #===============#

    def set_active_capabilities(self, capability_requests: dict) -> None:
        """The one entry point Backseater calls. Diffs `capability_requests` against what's
        currently running, by name: a new name is started, a name no longer present is
        stopped, an unchanged name is left alone. Running itself happens per-tick in
        _step_active_capabilities(), called from begin_update()."""
        for name in list(self._active_capability_requests):
            if name not in capability_requests:
                self._stop(name)

        for name, capability_request in capability_requests.items():
            if name not in self._active_capability_requests:
                self._start(name, capability_request)

        self._active_capability_requests = dict(capability_requests)

    def _start(self, name: str, capability_request: dict) -> None:
        """Starts one capability request: reads its inputs and sets up its runtime state."""
        capability, inputs = capability_request["capability"], capability_request.get("inputs", {})

        if capability == "move_to":
            self._active_target = self.backseater.query("knowledge", inputs["target"])
            self._active_tolerance = self.backseater.query("knowledge", inputs["tolerance"])
            self._request_runtime_state[name] = {"arrived": False}

        elif capability == "avoid":
            point = self.backseater.query("knowledge", inputs["point"])
            radius = self.backseater.query("knowledge", inputs["radius"])
            self._request_queue.put({"type": "add_avoid_region", "point_x": point.x, "point_y": point.y, "radius": radius})
            self._request_runtime_state[name] = {}   # instantaneous, not a duration task

        elif capability == "stopwatch":
            self._request_runtime_state[name] = {"start_time": self.hardware.read_state().t}   # s, sim time

        elif capability == "sense_pose":
            self._request_runtime_state[name] = {}   # stateless: re-senses every tick

        else:
            raise ValueError(f"Unknown capability: {capability}")

        if self.debug:
            print(f"[Frontseater] '{name}' ({capability}) -> started")

    def _stop(self, name: str) -> None:
        """Stops one capability request and drops its runtime state."""
        capability = self._active_capability_requests[name]["capability"]

        if capability == "move_to":
            self._active_target = None
            self._active_tolerance = None

        del self._request_runtime_state[name]

        if self.debug:
            print(f"[Frontseater] '{name}' ({capability}) -> stopped")

    def _step_active_capabilities(self) -> None:
        """Runs one tick of every currently active capability request, querying/publishing
        through this platform's own Backseater. Called every tick from begin_update()."""
        for name, capability_request in self._active_capability_requests.items():
            capability, inputs = capability_request["capability"], capability_request.get("inputs", {})
            outputs = capability_request.get("outputs", {})
            state = self._request_runtime_state[name]

            if capability == "move_to":
                self._active_target = self.backseater.query("knowledge", inputs["target"])
                self._active_tolerance = self.backseater.query("knowledge", inputs["tolerance"])
                current_state = self.hardware.read_state()
                distance = np.hypot(current_state.x - self._active_target.x, current_state.y - self._active_target.y)   # m
                state["arrived"] = bool(distance <= self._active_tolerance)
                if "arrived" in outputs:
                    self.backseater.publish("knowledge", outputs["arrived"], state["arrived"])

            elif capability == "avoid":
                if "registered" in outputs:
                    self.backseater.publish("knowledge", outputs["registered"], True)

            elif capability == "stopwatch":
                elapsed_time = self.hardware.read_state().t - state["start_time"]   # s
                if "elapsed_time" in outputs:
                    self.backseater.publish("knowledge", outputs["elapsed_time"], elapsed_time)

            elif capability == "sense_pose":
                if "pose" in outputs:
                    self.backseater.publish("knowledge", outputs["pose"], self._sense_pose())

    def _sense_pose(self) -> Pose:
        """This platform's pose as its sensor reports it (read_state(), not ground truth)."""
        state = self.hardware.read_state()
        return Pose(float(state.x), float(state.y), float(state.theta))   # m, m, rad; world frame





    #===============# Status Introspection #===============#

    def describe_status(self) -> dict:
        """Purely for display -- see Frontseater.describe_status."""
        active_capability_requests = self._active_capability_requests
        overall = f"{len(active_capability_requests)} capability request(s) active" if active_capability_requests else "idle"

        request_lines = {}
        for name, capability_request in active_capability_requests.items():
            capability = capability_request["capability"]
            state = self._request_runtime_state[name]

            if capability == "move_to":
                request_lines[name] = "arrived" if state["arrived"] else "en route"
            elif capability == "avoid":
                request_lines[name] = "registered"
            elif capability == "stopwatch":
                request_lines[name] = f"{self.hardware.read_state().t - state['start_time']:.1f}s elapsed"
            elif capability == "sense_pose":
                request_lines[name] = "sensing"

        return {"overall": overall, "capabilities": request_lines}





    #===============# Controls (Internal MPC) #===============#

    def compute_controls(self, state: GroundPlaneState) -> dict:
        """Synchronous, single-process reference path: only ever idle here, since the
        real per-tick solve goes through begin_update()/finish_update() and the worker
        process instead (see World.step(), which calls those, not this). Kept so
        BicycleFrontseater still satisfies Frontseater's abstract interface directly."""
        if self._active_target is None:
            return dict(IDLE_CONTROLS)
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
        Also steps every active capability request (queries/publishes), since this is
        the same per-tick cadence controls are computed on. If there's no active target,
        there's nothing to solve -- skip the dispatch and let finish_update() send idle
        controls."""
        self._step_active_capabilities()

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
            self.hardware.send_controls(dict(IDLE_CONTROLS))
            return

        result = self._response_queue.get()
        self.hardware.send_controls({"vel": result["vel"], "steer": result["steer"]})





    #===============# Lifecycle #===============#

    def shutdown(self) -> None:
        """Stops this platform's worker process. Not called automatically by anything
        in World/Backseater -- a caller (e.g. main.py) that started this Frontseater is
        responsible for calling it before exit."""
        if not self._worker_process.is_alive():
            return
        self._request_queue.put({"type": "shutdown"})
        self._worker_process.join(timeout=WORKER_JOIN_TIMEOUT)

    def __del__(self):
        """Best-effort shutdown if a caller forgot; never raises during garbage collection."""
        try:
            self.shutdown()
        except Exception:
            pass
