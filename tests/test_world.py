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
        self.sync_with_stale_peers_called_with = None

    def update(self):
        self.update_called = True

    def sync_with_stale_peers(self, peers):
        self.sync_with_stale_peers_called_with = list(peers)


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
        self.assertTrue(self.frontseater.begin_update_called)
        self.assertTrue(self.frontseater.finish_update_called)

    def test_step_passes_every_hardware_instance_and_dt_to_environment(self):
        self.world.step(0.1)
        hardware_dict, dt = self.environment.step_dynamics_all_called_with
        self.assertEqual(hardware_dict, {"ugv1": self.hardware})
        self.assertEqual(dt, 0.1)

    def test_get_states_returns_each_hardware_state(self):
        self.assertEqual(self.world.get_states(), {"ugv1": "initial_state"})

    def test_step_syncs_with_no_peers_when_only_one_backseater(self):
        self.world.step(0.1)   # must not raise with no peers to sync against
        self.assertEqual(self.backseater.sync_with_stale_peers_called_with, [])


class TestWorldMeshSync(unittest.TestCase):
    def test_step_syncs_each_backseater_against_every_other_backseater(self):
        backseater_a = FakeBackseater(FakeFrontseater(FakeHardware()))
        backseater_b = FakeBackseater(FakeFrontseater(FakeHardware()))
        backseater_c = FakeBackseater(FakeFrontseater(FakeHardware()))
        world = World(FakeEnvironment(), backseaters={
            "ugv1": backseater_a, "ugv2": backseater_b, "ugv3": backseater_c,
        })

        world.step(0.1)

        self.assertCountEqual(backseater_a.sync_with_stale_peers_called_with, [backseater_b, backseater_c])
        self.assertCountEqual(backseater_b.sync_with_stale_peers_called_with, [backseater_a, backseater_c])
        self.assertCountEqual(backseater_c.sync_with_stale_peers_called_with, [backseater_a, backseater_b])


if __name__ == "__main__":
    unittest.main()
