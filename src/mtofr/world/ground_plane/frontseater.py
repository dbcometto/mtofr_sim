"""Defines frontseaters to be used with the ground_plane environment"""
import multiprocessing
import uuid
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
    Frontseater never touches Hardware.state directly, only send_controls/read_state,
    same as before; only the MPC solve itself moved off the main process."""
    def __init__(self, hardware: BicycleHardware, nav_horizon=10, nav_dt=0.1, debug=False):
        self.hardware = hardware
        self.debug = debug

        self.nav_horizon = nav_horizon
        self.nav_dt = nav_dt

        self.backseater = None   # set by Backseater's constructor
        self._active_handle = None
        self._active_target = None   # Location, live-queried each poll while a move_to is active
        self._active_tolerance = None   # float, live-queried each poll while a move_to is active
        self._task_status = {}     # handle -> status string
        self._task_capability = {}   # handle -> ipl_type, so poll_status knows which outputs to report
        self._task_output_keys = {}   # handle -> {output field name -> knowledge key}
        self._task_input_keys = {}    # handle -> {input field name -> knowledge key}
        self._arrived = {}         # handle -> bool, latest "arrived" output for a move_to task
        self._stopwatch_start_time = {}   # handle -> simulation time (WorldState.t) at start_capability

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
        self._awaiting_response = False   # set in begin_update(), consumed in finish_update()

    #=====# Capabilities #=====#
    def capabilities(self) -> CapabilityRegistry:
        return self._capability_registry

    def start_capability(self, capability: str, inputs: dict, outputs: dict) -> str:
        handle = str(uuid.uuid4())
        if self.debug:
            print(f"[Frontseater] start_capability('{capability}', {inputs}, {outputs}) -> handle {handle[:8]}")

        self._task_capability[handle] = capability
        self._task_input_keys[handle] = inputs
        self._task_output_keys[handle] = outputs

        if capability == "move_to":
            self._active_handle = handle
            self._active_target = self.backseater.query("knowledge", inputs["target"])
            self._active_tolerance = self.backseater.query("knowledge", inputs["tolerance"])
            self._task_status[handle] = "received"
            self._arrived[handle] = False

        elif capability == "avoid":
            point = self.backseater.query("knowledge", inputs["point"])
            radius = self.backseater.query("knowledge", inputs["radius"])
            self._request_queue.put({"type": "add_avoid_region", "point_x": point.x, "point_y": point.y, "radius": radius})
            self._task_status[handle] = "success"   # instantaneous, not a duration task

        elif capability == "stopwatch":
            self._stopwatch_start_time[handle] = self.hardware.read_state().t
            self._task_status[handle] = "in_progress"   # never completes on its own

        else:
            raise ValueError(f"Unknown capability: {capability}")

        return handle

    def poll_status(self, handle: str) -> dict:
        status = self._task_status.get(handle, "fail")
        output_keys = self._task_output_keys.get(handle, {})

        if handle == self._active_handle and status in ("received", "in_progress"):
            input_keys = self._task_input_keys[handle]
            self._active_target = self.backseater.query("knowledge", input_keys["target"])
            self._active_tolerance = self.backseater.query("knowledge", input_keys["tolerance"])
            current_state = self.hardware.read_state()
            distance = np.hypot(current_state.x - self._active_target.x,
                                 current_state.y - self._active_target.y)
            if distance <= self._active_tolerance:
                status = "success"
                self._arrived[handle] = True
                self._active_handle = None
                self._active_target = None
                self._active_tolerance = None
            else:
                status = "in_progress"
            self._task_status[handle] = status

        capability = self._task_capability.get(handle)
        if capability == "move_to":
            arrived = self._arrived[handle]
            if "arrived" in output_keys:
                self.backseater.publish("knowledge", output_keys["arrived"], arrived)
            return {"status": status, "outputs": {"arrived": arrived}}
        if capability == "avoid":
            registered = status == "success"
            if "registered" in output_keys:
                self.backseater.publish("knowledge", output_keys["registered"], registered)
            return {"status": status, "outputs": {"registered": registered}}
        if capability == "stopwatch":
            elapsed_time = self.hardware.read_state().t - self._stopwatch_start_time[handle]
            if "elapsed_time" in output_keys:
                self.backseater.publish("knowledge", output_keys["elapsed_time"], elapsed_time)
            return {"status": status, "outputs": {"elapsed_time": elapsed_time}}
        return {"status": status, "outputs": {}}

    def cancel(self, handle: str) -> None:
        if handle == self._active_handle:
            self._active_handle = None
            self._active_target = None
            self._active_tolerance = None
        self._task_status[handle] = "fail"

    #=====# Controls (internal MPC) #=====#
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
        if not self._awaiting_response:
            self.hardware.send_controls({"vel": 0.0, "steer": 0.0})
            return
        result = self._response_queue.get()
        self.hardware.send_controls({"vel": result["vel"], "steer": result["steer"]})

    #=====# Lifecycle #=====#
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