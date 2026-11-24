"""Defines hardware for the interface (mission-editor) platform."""
from dataclasses import replace

from mtofr.core.hardware import Hardware
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps import GroundMap
from mtofr.environments.ground_plane.sensors import GroundMapSensor
from mtofr.environments.ground_plane.state import GroundPlaneState


class ConsoleHardware(Hardware):
    """The MCU/actuator-equivalent layer for a fixed operator console: a ground station on
    the ground plane that never moves, whatever controls it's sent.  It carries a
    GroundMapSensor, so the operator's UI can show the map (read_map()).  Takes no controls."""
    environment_type = GroundPlaneEnv
    state: GroundPlaneState

    def __init__(self, initial_state: GroundPlaneState | None = None, map_sensor: GroundMapSensor | None = None):
        """Placed at `initial_state` (the origin by default); no map until the first step."""
        super().__init__()
        self.state = initial_state or GroundPlaneState()
        self.map_sensor = map_sensor or GroundMapSensor()
        self._sensed_map: GroundMap | None = None

    def step_dynamics(self, dt: float, environment: GroundPlaneEnv) -> None:
        """Advances time only, and refreshes the sensed map (the one place Hardware sees the Environment)."""
        self.state = replace(self.state, t=self.state.t + dt)
        self._sensed_map = self.map_sensor.read(environment)

    def read_map(self) -> GroundMap | None:
        """The map as of the last step, through the map sensor; None before the first step or on a mapless plane."""
        return self._sensed_map
