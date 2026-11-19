"""Tests for World's tick sequencing: backseater update -> frontseater begin/finish_update ->
each hardware stepping itself against the environment -> mesh sync; per-platform fault
isolation; state reporting; and the construction-time check that every platform's
hardware can live in the world's environment."""
import contextlib
import io
import unittest

from mtofr.world.world import World
from mtofr.world.base import Environment
from mtofr.world.anywhere.hardware import StationaryHardware
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware


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
    environment_type = None   # lives anywhere, so any fake environment hosts it

    def __init__(self):
        self.state = "initial_state"
        self.step_dynamics_called_with = None

    def step_dynamics(self, dt, environment):
        self.step_dynamics_called_with = (dt, environment)


class FakeEnvironment:
    pass


class OtherEnvironment(Environment):
    """An environment no ground-plane vehicle can live in."""


class FakePlatform:
    """Duck-types Platform's three layer attributes, which is all World reads."""
    def __init__(self, backseater):
        self.backseater = backseater
        self.frontseater = backseater.frontseater
        self.hardware = backseater.frontseater.hardware


class _HardwarePlatform:
    """Just enough of a Platform for World's construction-time check: a hardware attribute."""
    def __init__(self, hardware):
        self.hardware = hardware


def _fake_platform() -> FakePlatform:
    """A FakePlatform with a fresh fake stack."""
    return FakePlatform(FakeBackseater(FakeFrontseater(FakeHardware())))


class TestWorld(unittest.TestCase):
    def setUp(self):
        self.hardware = FakeHardware()
        self.frontseater = FakeFrontseater(self.hardware)
        self.backseater = FakeBackseater(self.frontseater)
        self.environment = FakeEnvironment()
        self.world = World(self.environment, platforms={"ugv1": FakePlatform(self.backseater)})

    def test_step_updates_backseater_then_frontseater(self):
        self.world.step(0.1)
        self.assertTrue(self.backseater.update_called)
        self.assertTrue(self.frontseater.begin_update_called)
        self.assertTrue(self.frontseater.finish_update_called)

    def test_step_steps_each_hardware_against_the_environment(self):
        self.world.step(0.1)
        self.assertEqual(self.hardware.step_dynamics_called_with, (0.1, self.environment))

    def test_get_states_returns_each_hardware_state(self):
        self.assertEqual(self.world.get_states(), {"ugv1": "initial_state"})

    def test_step_syncs_with_no_peers_when_only_one_backseater(self):
        self.world.step(0.1)   # must not raise with no peers to sync against
        self.assertEqual(self.backseater.sync_with_stale_peers_called_with, [])


class TestWorldMeshSync(unittest.TestCase):
    def test_step_syncs_each_backseater_against_every_other_backseater(self):
        platform_a, platform_b, platform_c = _fake_platform(), _fake_platform(), _fake_platform()
        world = World(FakeEnvironment(), platforms={"ugv1": platform_a, "ugv2": platform_b, "ugv3": platform_c})
        backseater_a, backseater_b, backseater_c = platform_a.backseater, platform_b.backseater, platform_c.backseater

        world.step(0.1)

        self.assertCountEqual(backseater_a.sync_with_stale_peers_called_with, [backseater_b, backseater_c])
        self.assertCountEqual(backseater_b.sync_with_stale_peers_called_with, [backseater_a, backseater_c])
        self.assertCountEqual(backseater_c.sync_with_stale_peers_called_with, [backseater_a, backseater_b])


class TestWorldFaultIsolation(unittest.TestCase):
    def _raise(self, *arguments):
        raise RuntimeError("simulated fault")

    def _quiet_step(self, world):
        """Steps world with its "[World] ... failed" prints swallowed."""
        with contextlib.redirect_stdout(io.StringIO()):
            world.step(0.1)

    def test_a_failing_backseater_update_skips_only_that_platforms_frontseater(self):
        broken, healthy = _fake_platform(), _fake_platform()
        broken.backseater.update = self._raise
        world = World(FakeEnvironment(), platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertFalse(broken.frontseater.begin_update_called)
        self.assertTrue(healthy.frontseater.begin_update_called)
        self.assertTrue(healthy.frontseater.finish_update_called)

    def test_a_failing_begin_update_skips_only_that_platforms_finish_update(self):
        broken, healthy = _fake_platform(), _fake_platform()
        broken.frontseater.begin_update = self._raise
        world = World(FakeEnvironment(), platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertFalse(broken.frontseater.finish_update_called)
        self.assertTrue(healthy.frontseater.finish_update_called)

    def test_a_brain_fault_still_steps_that_platforms_hardware_and_syncs_it(self):
        environment = FakeEnvironment()
        broken, healthy = _fake_platform(), _fake_platform()
        broken.frontseater.finish_update = self._raise
        world = World(environment, platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertEqual(broken.hardware.step_dynamics_called_with, (0.1, environment))
        self.assertEqual(healthy.hardware.step_dynamics_called_with, (0.1, environment))
        self.assertEqual(broken.backseater.sync_with_stale_peers_called_with, [healthy.backseater])

    def test_a_failing_hardware_step_does_not_stop_the_others(self):
        broken, healthy = _fake_platform(), _fake_platform()
        broken.hardware.step_dynamics = self._raise
        world = World(FakeEnvironment(), platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertIsNotNone(healthy.hardware.step_dynamics_called_with)
        self.assertEqual(healthy.backseater.sync_with_stale_peers_called_with, [broken.backseater])


class TestWorldHostingCheck(unittest.TestCase):
    def test_ground_plane_hardware_is_hosted_by_a_ground_plane(self):
        World(GroundPlaneEnv(), platforms={"ugv1": _HardwarePlatform(BicycleHardware())})   # must not raise

    def test_ground_plane_hardware_is_refused_by_another_environment(self):
        with self.assertRaises(TypeError) as raised:
            World(OtherEnvironment(), platforms={"ugv1": _HardwarePlatform(BicycleHardware())})
        message = str(raised.exception)
        for expected in ("ugv1", "BicycleHardware", "GroundPlaneEnv", "OtherEnvironment"):
            self.assertIn(expected, message)

    def test_stationary_hardware_is_hosted_by_any_environment(self):
        for environment in (GroundPlaneEnv(), OtherEnvironment()):
            World(environment, platforms={"console": _HardwarePlatform(StationaryHardware())})   # must not raise

    def test_hardware_without_environment_type_is_refused(self):
        class UndeclaredHardware:
            state = None

        with self.assertRaises(TypeError) as raised:
            World(GroundPlaneEnv(), platforms={"mystery": _HardwarePlatform(UndeclaredHardware())})
        self.assertIn("environment_type", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
