"""Defines Sensor, the seam between a Hardware's true State and what its Frontseater
sees, and PerfectSensor, the default.  Environment-specific sensors (noise, partial
observability) live in each environment's own sensors/ folder."""
from abc import ABC, abstractmethod

from mtofr.core.state import State


class Sensor(ABC):
    """Turns ground-truth state into what the platform perceives."""

    @abstractmethod
    def read(self, state: State) -> State:
        """The state as this sensor reports it."""


class PerfectSensor(Sensor):
    """Reports ground-truth state exactly, in any environment.  Placeholder until a
    noisy/partial-observability sensor exists, without changing Hardware's interface."""

    def read(self, state: State) -> State:
        """Returns `state` unchanged."""
        return state
