"""Tests for StationaryHardware (and ConsoleHardware, the interface platform's subclass of it):
never moves regardless of controls, and needs nothing from its environment -- which is
what lets it live in any environment."""
import unittest

from mtofr.world.base import WorldState
from mtofr.world.anywhere.hardware import StationaryHardware
from mtofr.world.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.maps.ground_map import TraversabilityType
from tests.test_ground_plane_env import uniform_ground_map


class TestStationaryHardware(unittest.TestCase):
    def setUp(self):
        """Build a StationaryHardware at a non-origin pose."""
        self.hardware = StationaryHardware(initial_state=WorldState(x=1.0, y=-2.0, theta=0.3))

    def test_lives_in_any_environment(self):
        """StationaryHardware declares no required environment type."""
        self.assertIsNone(StationaryHardware.environment_type)

    def test_position_and_heading_are_unchanged_after_stepping(self):
        """Stepping with nonzero controls leaves position and heading where they were."""
        self.hardware.send_controls({"vel": 5.0, "steer": 0.2})
        self.hardware.step_dynamics(0.1, environment=None)
        state = self.hardware.read_state()
        self.assertEqual((state.x, state.y, state.theta), (1.0, -2.0, 0.3))

    def test_time_advances_across_ticks(self):
        """Each step still advances the state's time by dt."""
        self.hardware.step_dynamics(0.1, environment=None)
        self.hardware.step_dynamics(0.1, environment=None)
        self.assertAlmostEqual(self.hardware.read_state().t, 0.2)

    def test_velocity_stays_zero_regardless_of_controls(self):
        """All velocity components stay zero even with large controls sent."""
        self.hardware.send_controls({"vel": 100.0, "steer": -0.4})
        self.hardware.step_dynamics(0.1, environment=None)
        state = self.hardware.read_state()
        self.assertEqual((state.vx, state.vy, state.vtheta), (0.0, 0.0, 0.0))

    def test_unaffected_by_terrain_even_on_a_blocked_cell(self):
        """On a blocking map cell it stays put and time still advances."""
        hardware = StationaryHardware(initial_state=WorldState(x=0.0, y=0.0))
        wall = TraversabilityType(name="wall", blocking=True, speed_multiplier=1.0)
        hardware.step_dynamics(0.5, GroundPlaneEnv(uniform_ground_map(wall)))
        self.assertEqual((hardware.state.x, hardware.state.y, hardware.state.t), (0.0, 0.0, 0.5))

    def test_default_initial_state_is_the_origin(self):
        """With no initial state given, it sits at the origin."""
        state = StationaryHardware().read_state()
        self.assertEqual((state.x, state.y), (0.0, 0.0))


class TestConsoleHardware(unittest.TestCase):
    def test_console_hardware_is_stationary_hardware(self):
        """ConsoleHardware is a StationaryHardware and inherits its any-environment declaration."""
        self.assertIsInstance(ConsoleHardware(), StationaryHardware)
        self.assertIsNone(ConsoleHardware.environment_type)


if __name__ == "__main__":
    unittest.main()
