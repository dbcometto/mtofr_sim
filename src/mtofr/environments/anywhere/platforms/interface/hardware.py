"""Defines hardware for the interface (mission-editor) platform."""
from mtofr.environments.anywhere.hardware import StationaryHardware


class ConsoleHardware(StationaryHardware):
    """The MCU/actuator-equivalent layer for a fixed operator console: a ground station
    that can be placed in any environment and never moves. Kept as its own class (no
    behavior beyond StationaryHardware's) so this platform type, like every other, has
    its own hardware.py."""
