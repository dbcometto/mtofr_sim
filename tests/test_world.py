"""Tests for World's tick sequencing: backseater update -> frontseater update ->
environment dynamics, and state reporting."""
import unittest

from mtofr.world.world import World


class FakeFrontseater:
    def __init__(self, hardware):
        self.hardware = hardware
        self.update_called = False

    def update(self):
        self.update_called = True


class FakeBackseater:
    def __init__(self, frontseater):
        self.frontseater = frontseater
        self.update_called = False

    def update(self):
        self.update_called = True


class FakeHardware:
    def __init__(self):
        self.state = "initial_state"


class FakeEnvironment:
    def __init__(self):
        self.step_dynamics_all_called_with = None

    def step_dynamics_all(self, hardware, dt):
        self.step_dynamics_all_called_with = (dict(hardware), dt)


class TestWorld(unittest.TestCase):
    def setUp(self):
        self.hardware = FakeHardware()
        self.frontseater = FakeFrontseater(self.hardware)
        self.backseater = FakeBackseater(self.frontseater)
        self.environment = FakeEnvironment()
        self.world = World(self.environment, backseaters={"ugv1": self.backseater})

    def test_step_updates_backseater_then_frontseater(self):
        self.world.step(0.1)
        self.assertTrue(self.backseater.update_called)
        self.assertTrue(self.frontseater.update_called)

    def test_step_passes_every_hardware_instance_and_dt_to_environment(self):
        self.world.step(0.1)
        hardware_dict, dt = self.environment.step_dynamics_all_called_with
        self.assertEqual(hardware_dict, {"ugv1": self.hardware})
        self.assertEqual(dt, 0.1)

    def test_get_states_returns_each_hardware_state(self):
        self.assertEqual(self.world.get_states(), {"ugv1": "initial_state"})


if __name__ == "__main__":
    unittest.main()
