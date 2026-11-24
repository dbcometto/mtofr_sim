"""The bicycle UGV's own capabilities, which drive its MPC through BicycleFrontseater."""
import math

import numpy as np

from mtofr.core.capability import Capability, ParamSpec
from mtofr.core.hardware import Hardware
from mtofr.database import Location, Pose, Trajectory
from mtofr.environments.ground_plane.capabilities import sense_pose


#========================================#
# Config
#========================================#

STALE_POSE_TIMEOUT = 3.0   # s; an older leader pose stops a follower (a lost link, or a placeholder never written)
MIN_YAW_RATE = 1e-6        # rad/s; below this, extrapolation is a straight line (avoids dividing by ~0)







#========================================#
# Geometry
#========================================#

def _distance_to(hardware: Hardware, x: float, y: float) -> float:
    """Distance (m) from `hardware`'s sensed position to (x, y) (m, world frame)."""
    state = hardware.read_state()
    return float(np.hypot(state.x - x, state.y - y))


def wrap_angle(angle: float) -> float:
    """`angle` (rad) wrapped to [-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def offhook_target(leader: Pose, follower: Pose, following_distance: float) -> Pose:
    """The offhooked target pose (Ng et al.'s virtual trailer link, as in Cometto et al. sec. IV-H):
    back half the following distance (m) along the leader's heading, then half along the
    follower's.  Its heading is the follower's own, so the MPC never chases the leader's turn
    early; in a steady turn this keeps the follower on the leader's path.  World frame."""
    half_distance = following_distance / 2
    x = leader.x - half_distance * (math.cos(leader.theta) + math.cos(follower.theta))
    y = leader.y - half_distance * (math.sin(leader.theta) + math.sin(follower.theta))
    return Pose(x, y, follower.theta)


def extrapolate_pose(pose: Pose, speed: float, yaw_rate: float, dt: float) -> Pose:
    """`pose` advanced dt (s) at a constant speed (m/s) and yaw rate (rad/s): an arc, or a
    straight line when the yaw rate is ~0.  World frame."""
    if abs(yaw_rate) < MIN_YAW_RATE:
        return Pose(pose.x + speed * dt * math.cos(pose.theta), pose.y + speed * dt * math.sin(pose.theta), pose.theta)
    new_theta = pose.theta + yaw_rate * dt
    turn_radius = speed / yaw_rate   # m, signed (positive turns left)
    return Pose(pose.x + turn_radius * (math.sin(new_theta) - math.sin(pose.theta)),
                pose.y - turn_radius * (math.cos(new_theta) - math.cos(pose.theta)),
                new_theta)







#========================================#
# Capabilities
#========================================#


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


class Follow(Capability):
    """Convoy following (Cometto et al.): tracks the offhooked point behind a leader's pose with
    the MPC's pose-tracking cost.  The leader's pose arrives by sync, up to sync_interval old, so
    it is dead-reckoned forward by its age from a speed and yaw rate estimated across samples
    (the paper's EKF predict step, without measurement updates: the pose is known directly)."""
    ipl_type = "follow"
    description = ("Follow another vehicle convoy-style at a following distance: track the point behind it (half the "
                   "distance back along its heading, then half along this vehicle's) with the internal MPC, waiting "
                   f"while that point is behind this vehicle, and stopping if its pose is over {STALE_POSE_TIMEOUT} s "
                   "old. Never completes.")
    inputs = (
        ParamSpec("leader_pose", Pose, "Pose of the vehicle to follow, e.g. its sense_pose output <platform_id>/pose"),
        ParamSpec("following_distance", float, "Desired distance behind the leader, in meters"),
    )
    outputs = (ParamSpec("distance", float, "Current distance to the leader's predicted position, in meters"),)

    def start(self) -> None:
        """No leader sample yet, so the leader is assumed still."""
        self.previous_sample = None   # (Pose, write time s local clock) of the last distinct leader pose
        self.speed = 0.0              # m/s, the leader's estimated speed along its heading
        self.yaw_rate = 0.0           # rad/s, the leader's estimated yaw rate
        self.mode = "starting"

    def tick(self) -> None:
        """Re-estimates the leader's motion, predicts it to now, and steers toward the offhooked point."""
        leader, age = self.read("leader_pose"), self.age("leader_pose")   # Pose, s
        self._observe_leader(leader, self.written_at("leader_pose"))
        follower = sense_pose(self.hardware)


        # Predict the leader to now and place the target, unless its pose is too old to trust
        predicted_leader, target = leader, None
        if age > STALE_POSE_TIMEOUT:
            self.mode = "leader pose stale"
        else:
            predicted_leader = extrapolate_pose(leader, self.speed, self.yaw_rate, age)
            target = offhook_target(predicted_leader, follower, self.read("following_distance"))
            distance_ahead = ((target.x - follower.x) * math.cos(follower.theta)
                              + (target.y - follower.y) * math.sin(follower.theta))   # m, along the follower's heading
            # Paper sec. IV-I: with the target not in front, wait for it to move rather than reverse.
            if distance_ahead <= 0:
                self.mode, target = "waiting", None
            else:
                self.mode = "following"


        # Steer (None idles the vehicle)
        # NOTE: single target, shared with move_to/follow_trajectory: the last request ticked wins.
        self.frontseater.navigation_target = target
        self.write("distance", float(np.hypot(predicted_leader.x - follower.x, predicted_leader.y - follower.y)))

    def _observe_leader(self, leader: Pose, write_time: float) -> None:
        """Re-estimates the leader's speed and yaw rate from the previous sample when a newer one arrived."""
        if self.previous_sample is not None:
            previous, previous_time = self.previous_sample
            dt = write_time - previous_time   # s
            if dt <= 0:
                return
            self.speed = ((leader.x - previous.x) * math.cos(previous.theta)
                          + (leader.y - previous.y) * math.sin(previous.theta)) / dt
            self.yaw_rate = wrap_angle(leader.theta - previous.theta) / dt
        self.previous_sample = (leader, write_time)

    def stop(self) -> None:
        """Releases the MPC target, so the vehicle idles."""
        self.frontseater.navigation_target = None

    def status(self) -> str:
        """"starting", "following", "waiting", or "leader pose stale"."""
        return self.mode


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
