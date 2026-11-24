"""The bicycle UGV's own capabilities, which drive its MPC through BicycleFrontseater."""
import numpy as np

from mtofr.core.capability import Capability, ParamSpec
from mtofr.database import Location


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
        state = self.hardware.read_state()
        distance = np.hypot(state.x - target.x, state.y - target.y)   # m
        self.arrived = bool(distance <= tolerance)
        self.write("arrived", self.arrived)

    def stop(self) -> None:
        """Releases the MPC target, so the vehicle idles."""
        self.frontseater.navigation_target = None

    def status(self) -> str:
        """"arrived" or "en route"."""
        return "arrived" if self.arrived else "en route"


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
