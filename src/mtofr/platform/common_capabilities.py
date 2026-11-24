"""Capabilities any platform can list in its Frontseater's CAPABILITIES: they need nothing
but a Hardware's read_state(), so they are platform- and environment-agnostic."""
from mtofr.core.capability import Capability, ParamSpec


class Stopwatch(Capability):
    """Publishes the sim time elapsed since it started; never completes."""
    ipl_type = "stopwatch"
    description = ("Reports simulation time (seconds) elapsed since this capability instance "
                   "was (re)started; resets to zero every time it is started again.")
    outputs = (ParamSpec("elapsed_time", float, "Seconds since this stopwatch instance started"),)

    def start(self) -> None:
        """Records the start time."""
        self.start_time = self.hardware.read_state().t   # s, sim time

    def elapsed_time(self) -> float:
        """Sim seconds since start()."""
        return self.hardware.read_state().t - self.start_time

    def tick(self) -> None:
        """Publishes the elapsed time."""
        self.write("elapsed_time", self.elapsed_time())

    def status(self) -> str:
        """E.g. "12.3s elapsed"."""
        return f"{self.elapsed_time():.1f}s elapsed"
