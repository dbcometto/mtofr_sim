"""Defines GroundMapSensor: what a ground-plane platform knows of the map it is on."""
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps import GroundMap


class GroundMapSensor:
    """Turns the environment's ground-truth map into the map the platform has, the way
    core.sensor.Sensor does for State (which is why it is not a Sensor: it reads the
    Environment, not a State).  This one is perfect: it reports the environment's own
    GroundMap, or None on a mapless plane.  A partial or out-of-date map would be a
    subclass overriding read()."""

    def read(self, environment: GroundPlaneEnv) -> GroundMap | None:
        """The map as this sensor reports it."""
        return environment.ground_map
