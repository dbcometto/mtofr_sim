"""Tests for GroundPlaneEnv: steps dynamics for every hardware instance it's given."""
import unittest

from mtofr.world.ground_plane.env import GroundPlaneEnv


class FakeHardware:
    def __init__(self):
        self.step_dynamics_called_with = None

    def step_dynamics(self, dt):
        self.step_dynamics_called_with = dt


class TestGroundPlaneEnv(unittest.TestCase):
    def test_step_dynamics_all_steps_every_hardware_instance(self):
        hardware_a, hardware_b = FakeHardware(), FakeHardware()
        GroundPlaneEnv().step_dynamics_all({"a": hardware_a, "b": hardware_b}, dt=0.1)
        self.assertEqual(hardware_a.step_dynamics_called_with, 0.1)
        self.assertEqual(hardware_b.step_dynamics_called_with, 0.1)

    def test_step_dynamics_all_with_no_hardware_does_not_raise(self):
        GroundPlaneEnv().step_dynamics_all({}, dt=0.1)


if __name__ == "__main__":
    unittest.main()
