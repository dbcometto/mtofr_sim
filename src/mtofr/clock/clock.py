"""Defines a clock"""
import time


class Clock:
    """Wraps wall-clock time with an adjustable offset. The offset is the seam a
    future real clock-synchronization mechanism would drive; today only Relay's
    placeholder sync_clock() touches it, and it always resets to 0.0 (identity) —
    clock synchronization proper is an open design question, not solved here."""

    def __init__(self, offset: float = 0.0):
        self._offset = offset

    def now(self) -> float:
        """Current time, adjusted by this clock's offset."""
        return time.time() + self._offset

    def set_offset(self, offset: float) -> None:
        """Adjusts this clock relative to wall-clock time."""
        self._offset = offset