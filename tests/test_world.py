"""Tests for World's tick sequencing: backseater update -> frontseater begin/finish_update ->
environment dynamics, and state reporting."""
import unittest

from mtofr.world.world import World


class FakeFrontseater:
    def __init__(self, hardware):
        self.hardware = hardware
        self.begin_update_called = False
        self.finish_update_called = False

    def begin_update(self):
        self.begin_update_called = True

    def finish_update(self):
        self.finish_update_called = True


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


class FakeRelay:
    def __init__(self):
        self.sync_called_with = None

    def sync(self, backseaters):
        self.sync_called_with = dict(backseaters)


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
        self.assertTrue(self.frontseater.begin_update_called)
        self.assertTrue(self.frontseater.finish_update_called)

    def test_step_passes_every_hardware_instance_and_dt_to_environment(self):
        self.world.step(0.1)
        hardware_dict, dt = self.environment.step_dynamics_all_called_with
        self.assertEqual(hardware_dict, {"ugv1": self.hardware})
        self.assertEqual(dt, 0.1)

    def test_get_states_returns_each_hardware_state(self):
        self.assertEqual(self.world.get_states(), {"ugv1": "initial_state"})

    def test_relay_defaults_to_none_and_step_does_not_require_one(self):
        self.assertIsNone(self.world.relay)
        self.world.step(0.1)   # must not raise with no relay attached


class TestWorldWithRelay(unittest.TestCase):
    def test_step_syncs_the_relay_after_stepping_dynamics(self):
        hardware = FakeHardware()
        frontseater = FakeFrontseater(hardware)
        backseater = FakeBackseater(frontseater)
        relay = FakeRelay()
        world = World(FakeEnvironment(), backseaters={"ugv1": backseater}, relay=relay)

        world.step(0.1)

        self.assertEqual(relay.sync_called_with, {"ugv1": backseater})


if __name__ == "__main__":
    unittest.main()
