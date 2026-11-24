"""The bicycle UGV's own capabilities, which drive its MPC through BicycleFrontseater."""
import numpy as np

from mtofr.core.capability import Capability, ParamSpec
from mtofr.core.hardware import Hardware
from mtofr.database import Location, Trajectory


def _distance_to(hardware: Hardware, x: float, y: float) -> float:
    """Distance (m) from `hardware`'s sensed position to (x, y) (m, world frame)."""
    state = hardware.read_state()
    return float(np.hypot(state.x - x, state.y - y))


class MoveTo(Capability):
    """Steers the MPC toward a target, re-read every tick, until within tolerance."""
    ipl_type = "move_to"
    description = "Navigate to a target location until within tolerance, using the internal MPC."
    inputs = (
        ParamSpec("target", Location, "Location to navigate to"),
        ParamSpec("tolerance", float, "Distance within which the target counts as reached, in meters"),
    )
    outputs = (ParamSpec("arrived", bool, "True once within tolerance of the current target"),)

    def start(self) -> None:
        """Not arrived yet."""
        self.arrived = False

    def tick(self) -> None:
        """Hands the MPC this tick's target and publishes whether it has been reached."""
        target, tolerance = self.read("target"), self.read("tolerance")   # Location, m
        # NOTE: single target: with two move_to requests running, the last one ticked wins.
        self.frontseater.navigation_target = target
        self.arrived = _distance_to(self.hardware, target.x, target.y) <= tolerance
        self.write("arrived", self.arrived)

    def stop(self) -> None:
        """Releases the MPC target, so the vehicle idles."""
        self.frontseater.navigation_target = None

    def status(self) -> str:
        """"arrived" or "en route"."""
        return "arrived" if self.arrived else "en route"


class FollowTrajectory(Capability):
    """Steers the MPC through a trajectory's waypoints in order, each until within tolerance,
    then stops at the last one (arrived) or, with `loop`, starts over from the first."""
    ipl_type = "follow_trajectory"
    description = ("Drive through a trajectory's waypoints in order, each until within tolerance, using the "
                   "internal MPC; then hold at the last one, or start over from the first if loop is true. "
                   "A changed trajectory restarts from its first waypoint.")
    inputs = (
        ParamSpec("trajectory", Trajectory, "Waypoints to drive through, in order"),
        ParamSpec("tolerance", float, "Distance within which a waypoint counts as reached, in meters"),
        ParamSpec("loop", bool, "If true, start over from the first waypoint after the last instead of stopping"),
    )
    outputs = (ParamSpec("arrived", bool, "True once the last waypoint is reached (never, while looping)"),)

    def start(self) -> None:
        """No trajectory read yet."""
        self.points = None   # the trajectory being followed, ((x, y), ...) m
        self.waypoint_index = 0
        self.arrived = False

    def tick(self) -> None:
        """Advances past a reached waypoint, hands the MPC the current one, and publishes arrived."""
        points = self.read("trajectory").points
        tolerance, loop = self.read("tolerance"), self.read("loop")   # m, bool
        if points != self.points:
            self.points, self.waypoint_index, self.arrived = points, 0, False


        # Advance (at most one waypoint per tick)
        if points and not self.arrived and _distance_to(self.hardware, *points[self.waypoint_index]) <= tolerance:
            if self.waypoint_index < len(points) - 1:
                self.waypoint_index += 1
            elif loop:
                self.waypoint_index = 0
            else:
                self.arrived = True


        # Steer (holding at the last waypoint once arrived)
        # NOTE: single target, shared with move_to: the last request ticked wins.
        self.frontseater.navigation_target = Location(*points[self.waypoint_index]) if points else None
        self.write("arrived", self.arrived)

    def stop(self) -> None:
        """Releases the MPC target, so the vehicle idles."""
        self.frontseater.navigation_target = None

    def status(self) -> str:
        """"no waypoints", "arrived", or "waypoint i/n"."""
        if not self.points:
            return "no waypoints"
        if self.arrived:
            return "arrived"
        return f"waypoint {self.waypoint_index + 1}/{len(self.points)}"


class Avoid(Capability):
    """Registers a persistent circular avoid-region with the MPC once, at start."""
    ipl_type = "avoid"
    description = "Add a persistent circular avoid-region; instantaneous, not a duration task."
    inputs = (
        ParamSpec("point", Location, "Center of the avoid-region"),
        ParamSpec("radius", float, "Avoid-region radius in meters"),
    )
    outputs = (ParamSpec("registered", bool, "True once the avoid-region has been registered"),)

    def start(self) -> None:
        """Registers the region (it outlives this request)."""
        self.frontseater.add_avoid_region(self.read("point"), self.read("radius"))

    def tick(self) -> None:
        """Reports the region as registered."""
        self.write("registered", True)

    def status(self) -> str:
        """Always "registered"."""
        return "registered"
