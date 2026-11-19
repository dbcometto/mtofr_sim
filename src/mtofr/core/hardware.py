"""Defines Hardware, the MCU-equivalent layer that owns physical state."""
from abc import ABC, abstractmethod

from mtofr.core.environment import Environment
from mtofr.core.sensor import PerfectSensor, Sensor
from mtofr.core.state import State


class Hardware(ABC):
    """Owns physical state and executes low-level controls each tick: the
    MCU/actuator-equivalent layer, including its own dynamics. step_dynamics() queries
    the (passive) Environment for whatever it needs, since how the world affects a
    vehicle is that vehicle's business. Knows nothing about capabilities or missions.
    Every subclass must set `environment_type` (the Environment class it can live in,
    or None for any), which World checks at construction."""
    # NOTE: environment_type deliberately has no default here, so forgetting it is an
    # error rather than a silent "lives anywhere".
    state: State
    environment_type: type | None

    def __init__(self, sensor: Sensor | None = None):
        """Sets up the sensor (PerfectSensor by default) and empty pending controls; the subclass sets `state`."""
        self._sensor = sensor or PerfectSensor()
        self._pending_controls: dict = {}
        self.platform_id: str | None = None

    @abstractmethod
    def step_dynamics(self, dt: float, environment: Environment) -> None:
        """Advances self.state by dt (s) under the last controls sent, in this environment."""

    def send_controls(self, controls: dict) -> None:
        """Stores `controls` for the next step_dynamics()."""
        self._pending_controls = controls

    def read_state(self) -> State:
        """The state as seen through this hardware's sensor."""
        return self._sensor.read(self.state)
