"""Ground-plane sensors: core.sensor.Sensor subclasses that read a GroundPlaneState (none
yet; Hardware defaults to the environment-agnostic core.sensor.PerfectSensor), and
GroundMapSensor, which reads the environment's map."""
from .ground_map_sensor import GroundMapSensor
