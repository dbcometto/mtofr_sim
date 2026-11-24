"""Defines the bicycle UGV platform's Frontseater (MPC navigation, for the ground_plane environment)"""
import multiprocessing

from mtofr.database import Location, Pose
from mtofr.environments.ground_plane.capabilities import SensePose, sense_pose
from mtofr.environments.ground_plane.platforms.bicycle_ugv.capabilities import Avoid, MoveTo
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.mpc import run_mpc_worker
from mtofr.platform.common_capabilities import Stopwatch
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
    Its capabilities steer the MPC through `navigation_target` and add_avoid_region()."""
    CAPABILITIES = (MoveTo, Avoid, Stopwatch, SensePose)

    #===============# Construction #===============#

    def __init__(self, hardware: BicycleHardware, nav_horizon=DEFAULT_NAV_HORIZON, nav_dt=DEFAULT_NAV_DT,
                 debug: bool = False):
        """Starts this platform's MPC worker process."""
        super().__init__(hardware, debug)
        self.nav_horizon = nav_horizon
        self.nav_dt = nav_dt   # s
        self.navigation_target: Location | None = None   # m, world frame; set by a running MoveTo
        self._awaiting_response = False   # set in begin_controls(), consumed in finish_controls()


        # MPC worker process
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

    def default_mission_graph(self) -> dict:
        """Boots this platform into an idle loiter -- runs the stopwatch, plus the pose
        sensor publishing to "<platform_id>/pose" so peers see where it is -- until a
        real mission is delegated."""
        pose_key = f"{self.platform_id}/pose"
        return {
            "knowledge": {
                "startup/elapsed_time": {"type": float, "value": 0.0},
                pose_key: {"type": Pose, "value": sense_pose(self.hardware)},
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





    #===============# MPC Interface (used by capabilities) #===============#

    def add_avoid_region(self, point: Location, radius: float) -> None:
        """Adds a persistent circular avoid-region (m, world frame) to the MPC."""
        self._request_queue.put({"type": "add_avoid_region", "point_x": point.x, "point_y": point.y, "radius": radius})





    #===============# Controls (Internal MPC) #===============#

    def begin_controls(self) -> None:
        """Dispatches this tick's MPC solve to the worker process without blocking on the
        result. World.step() calls begin_update() (capabilities, then this) for every
        platform first, then finish_update() for every platform, so every platform's
        request is already in-flight on its own worker process before any one of them is
        waited on -- letting independent platforms' solves overlap instead of serializing
        on one core. With no navigation target there's nothing to solve, and
        finish_controls() sends idle controls."""
        if self.navigation_target is None:
            self._awaiting_response = False
            return

        state = self.hardware.read_state()
        self._request_queue.put({
            "type": "compute",
            "state": (state.x, state.y, state.theta),
            "target": (self.navigation_target.x, self.navigation_target.y),
        })
        self._awaiting_response = True

    def finish_controls(self) -> None:
        """Collects the result begin_controls() dispatched and applies it to Hardware.
        Blocks on this platform's own response queue -- but only after every platform's
        begin_update() has already run, so the blocking wait here overlaps with every
        other platform's solve rather than each platform waiting in turn."""
        if not self._awaiting_response:
            self.hardware.send_controls(dict(self.hardware.idle_controls))
            return

        result = self._response_queue.get()
        self.hardware.send_controls({"vel": result["vel"], "steer": result["steer"]})





    #===============# Lifecycle #===============#

    def shutdown(self) -> None:
        """Stops every capability, then this platform's worker process. Not called
        automatically by anything in World/Backseater -- a caller (e.g. main.py) that
        started this Frontseater is responsible for calling it before exit."""
        super().shutdown()
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
