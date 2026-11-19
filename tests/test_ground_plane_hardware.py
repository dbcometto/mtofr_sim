"""Tests for GroundPlaneHardware's default terrain response, through BicycleHardware: the
vehicle steps itself against a passive GroundPlaneEnv, slowed by the terrain's speed
multiplier and stopped dead at blocking (or off-map) cells."""
import unittest

from mtofr.world.base import WorldState
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import GroundPlaneHardware
from mtofr.world.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.maps.ground_map import TraversabilityType
from tests.test_ground_plane_env import uniform_ground_map

SLOW = TraversabilityType(name="slow", blocking=False, speed_multiplier=0.5)
WALL = TraversabilityType(name="wall", blocking=True, speed_multiplier=1.0)
CLEAR = TraversabilityType(name="clear", blocking=False, speed_multiplier=1.0)


def _hardware_at(x: float = 0.0, y: float = 0.0, t: float = 0.0, controls: dict = None) -> BicycleHardware:
    """A BicycleHardware at (x, y) facing +x, with controls already sent."""
    hardware = BicycleHardware()
    hardware.state = WorldState(t=t, x=x, y=y, theta=0.0)
    hardware.send_controls(controls or {"vel": 1.0, "steer": 0.0})
    return hardware


class TestGroundPlaneHardware(unittest.TestCase):
    def test_bicycle_hardware_lives_in_the_ground_plane(self):
        """BicycleHardware is a GroundPlaneHardware requiring a GroundPlaneEnv."""
        self.assertIsInstance(BicycleHardware(), GroundPlaneHardware)
        self.assertIs(BicycleHardware.environment_type, GroundPlaneEnv)

    def test_mapless_step_matches_pure_dynamics(self):
        """Without a map, step_dynamics() gives the same pose as calculate_dynamics()."""
        hardware = _hardware_at(controls={"vel": 2.0, "steer": 0.1})
        expected = hardware.calculate_dynamics(hardware.state, {"vel": 2.0, "steer": 0.1}, 0.1)
        hardware.step_dynamics(0.1, GroundPlaneEnv())
        self.assertAlmostEqual(hardware.state.x, expected.x)
        self.assertAlmostEqual(hardware.state.y, expected.y)
        self.assertAlmostEqual(hardware.state.theta, expected.theta)

    def test_speed_multiplier_scales_max_speed(self):
        """On slow terrain, a saturated step covers max_speed times the terrain's multiplier."""
        hardware = _hardware_at(controls={"vel": 999.0, "steer": 0.0})
        hardware.step_dynamics(1.0, GroundPlaneEnv(uniform_ground_map(SLOW)))
        self.assertAlmostEqual(hardware.state.x, hardware.max_speed * 0.5)

    def test_blocking_terrain_stops_the_vehicle_at_its_previous_position(self):
        """A step into blocking terrain is rejected: position held and velocity zeroed."""
        hardware = _hardware_at()
        hardware.step_dynamics(1.0, GroundPlaneEnv(uniform_ground_map(WALL)))
        self.assertAlmostEqual(hardware.state.x, 0.0)
        self.assertAlmostEqual(hardware.state.y, 0.0)
        self.assertAlmostEqual(hardware.state.vx, 0.0)

    def test_blocking_terrain_still_advances_time(self):
        """A rejected step into blocking terrain still advances time by dt."""
        hardware = _hardware_at(t=1.0)
        hardware.step_dynamics(0.5, GroundPlaneEnv(uniform_ground_map(WALL)))
        self.assertAlmostEqual(hardware.state.t, 1.5)

    def test_off_map_position_is_blocked(self):
        """A vehicle already off the map cannot move, even over clear terrain types."""
        hardware = _hardware_at(x=100.0, y=100.0)   # already off the 20x20m map
        hardware.step_dynamics(1.0, GroundPlaneEnv(uniform_ground_map(CLEAR)))
        self.assertAlmostEqual(hardware.state.x, 100.0)
        self.assertAlmostEqual(hardware.state.vx, 0.0)


if __name__ == "__main__":
    unittest.main()
