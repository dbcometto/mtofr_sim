"""Tests for ConsoleHardware, the interface platform's ground station: it never moves whatever
controls it's sent, and its GroundMapSensor reports the environment's map as of the last step."""
import unittest

from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps.ground_map import TraversabilityType
from mtofr.environments.ground_plane.platforms.interface.hardware import ConsoleHardware
from mtofr.environments.ground_plane.sensors import GroundMapSensor
from mtofr.environments.ground_plane.state import GroundPlaneState
from tests.test_ground_plane_env import uniform_ground_map


WALL = TraversabilityType(name="wall", blocking=True, speed_multiplier=1.0)


class TestConsoleHardware(unittest.TestCase):
    def setUp(self):
        """A console at a non-origin pose."""
        self.hardware = ConsoleHardware(initial_state=GroundPlaneState(x=1.0, y=-2.0, theta=0.3))

    def test_lives_on_the_ground_plane(self):
        """It declares GroundPlaneEnv, and defaults to a GroundPlaneState at the origin."""
        self.assertIs(ConsoleHardware.environment_type, GroundPlaneEnv)
        self.assertEqual(ConsoleHardware().read_state(), GroundPlaneState())

    def test_a_step_advances_time_and_keeps_the_pose(self):
        """With controls sent, even on a blocked cell, only time advances."""
        self.hardware.send_controls({"vel": 5.0, "steer": 0.2})
        self.hardware.step_dynamics(0.5, GroundPlaneEnv(uniform_ground_map(WALL)))
        state = self.hardware.read_state()
        self.assertEqual((state.x, state.y, state.theta, state.t), (1.0, -2.0, 0.3, 0.5))

    def test_the_map_is_sensed_at_the_first_step(self):
        """read_map() is None before any step, then the environment's own map."""
        ground_map = uniform_ground_map(WALL)
        self.assertIsNone(self.hardware.read_map())
        self.hardware.step_dynamics(0.1, GroundPlaneEnv(ground_map))
        self.assertIs(self.hardware.read_map(), ground_map)

    def test_a_mapless_plane_senses_no_map(self):
        """On a GroundPlaneEnv with no map, read_map() stays None."""
        self.hardware.step_dynamics(0.1, GroundPlaneEnv())
        self.assertIsNone(self.hardware.read_map())

    def test_the_map_comes_through_the_sensor(self):
        """A custom GroundMapSensor decides what map the hardware has."""
        class _BlindSensor(GroundMapSensor):
            """Never sees a map."""
            def read(self, environment):
                """No map, whatever the environment holds."""
                return None
        hardware = ConsoleHardware(map_sensor=_BlindSensor())
        hardware.step_dynamics(0.1, GroundPlaneEnv(uniform_ground_map(WALL)))
        self.assertIsNone(hardware.read_map())


if __name__ == "__main__":
    unittest.main()
