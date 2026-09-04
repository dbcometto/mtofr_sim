"""Tests for ConsoleHardware: the mission-editor "interface" platform's stationary
Hardware -- confirms it satisfies the same Hardware interface as BicycleHardware
while never actually moving, regardless of controls sent to it."""
import unittest

from mtofr.world.base import WorldState
from mtofr.world.interface.hardware import ConsoleHardware


class TestConsoleHardware(unittest.TestCase):
    def setUp(self):
        self.hardware = ConsoleHardware(initial_state=WorldState(x=1.0, y=-2.0, theta=0.3))

    def test_position_and_heading_are_unchanged_after_stepping(self):
        self.hardware.send_controls({"vel": 5.0, "steer": 0.2})
        self.hardware.step_dynamics(dt=0.1)
        state = self.hardware.read_state()
        self.assertEqual((state.x, state.y, state.theta), (1.0, -2.0, 0.3))

    def test_time_advances_across_ticks(self):
        self.hardware.step_dynamics(dt=0.1)
        self.hardware.step_dynamics(dt=0.1)
        self.assertAlmostEqual(self.hardware.read_state().t, 0.2)

    def test_velocity_stays_zero_regardless_of_controls(self):
        self.hardware.send_controls({"vel": 100.0, "steer": -0.4})
        self.hardware.step_dynamics(dt=0.1)
        state = self.hardware.read_state()
        self.assertEqual((state.vx, state.vy, state.vtheta), (0.0, 0.0, 0.0))

    def test_default_initial_state_is_the_origin(self):
        hardware = ConsoleHardware()
        state = hardware.read_state()
        self.assertEqual((state.x, state.y), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()