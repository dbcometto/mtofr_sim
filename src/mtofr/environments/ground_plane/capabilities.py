"""Capabilities any ground_plane platform can list in its Frontseater's CAPABILITIES."""
from mtofr.core.capability import Capability, ParamSpec
from mtofr.core.hardware import Hardware
from mtofr.database import Pose


def sense_pose(hardware: Hardware) -> Pose:
    """`hardware`'s pose as its sensor reports it (read_state(), not ground truth)."""
    state = hardware.read_state()
    return Pose(float(state.x), float(state.y), float(state.theta))   # m, m, rad; world frame


class SensePose(Capability):
    """Publishes this platform's sensed pose every tick; never completes."""
    ipl_type = "sense_pose"
    description = "Runs the pose sensor, publishing this platform's sensed pose every tick; never completes."
    outputs = (ParamSpec("pose", Pose, "This platform's sensed pose, updated every tick"),)

    def tick(self) -> None:
        """Publishes the sensed pose."""
        self.write("pose", sense_pose(self.hardware))

    def status(self) -> str:
        """Always "sensing"."""
        return "sensing"
