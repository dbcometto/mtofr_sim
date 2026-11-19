"""Tests for World's tick sequencing: backseater update -> frontseater begin/finish_update ->
each hardware stepping itself against the environment -> mesh sync; per-platform fault
isolation; state reporting; and the construction-time checks that every platform's
hardware can live in the world's environment and is expressed in its state type."""
import contextlib
import io
import unittest

from mtofr.core.environment import Environment
from mtofr.core.state import State
from mtofr.environments.anywhere.hardware import StationaryHardware
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.state import GroundPlaneState
from mtofr.environments.world import World


class FakeFrontseater:
    def __init__(self, hardware):
        """Hold the hardware and start with no update calls recorded."""
        self.hardware = hardware
        self.begin_update_called = False
        self.finish_update_called = False

    def begin_update(self):
        """Record that begin_update() was called."""
        self.begin_update_called = True

    def finish_update(self):
        """Record that finish_update() was called."""
        self.finish_update_called = True


class FakeBackseater:
    def __init__(self, frontseater):
        """Hold the frontseater and start with no update or sync calls recorded."""
        self.frontseater = frontseater
        self.update_called = False
        self.sync_with_stale_peers_called_with = None

    def update(self):
        """Record that update() was called."""
        self.update_called = True

    def sync_with_stale_peers(self, peers):
        """Record the peers this backseater was asked to sync with."""
        self.sync_with_stale_peers_called_with = list(peers)


class FakeHardware:
    environment_type = None   # lives anywhere, so any fake environment hosts it

    def __init__(self):
        """Start with a sentinel state and no step recorded."""
        self.state = "initial_state"
        self.step_dynamics_called_with = None

    def step_dynamics(self, dt, environment):
        """Record the dt and environment this hardware was stepped with."""
        self.step_dynamics_called_with = (dt, environment)


class FakeEnvironment:
    """Hosts FakeHardware, whose sentinel state is a str."""
    state_type = str


class OtherEnvironment(Environment):
    """An environment no ground-plane vehicle can live in, expressed in bare States."""
    state_type = State


class FakePlatform:
    """Duck-types Platform's three layer attributes, which is all World reads."""
    def __init__(self, backseater):
        """Expose the backseater and the frontseater and hardware beneath it."""
        self.backseater = backseater
        self.frontseater = backseater.frontseater
        self.hardware = backseater.frontseater.hardware


class _HardwarePlatform:
    """Just enough of a Platform for World's construction-time check: a hardware attribute."""
    def __init__(self, hardware):
        """Expose the given hardware."""
        self.hardware = hardware


def _fake_platform() -> FakePlatform:
    """A FakePlatform with a fresh fake stack."""
    return FakePlatform(FakeBackseater(FakeFrontseater(FakeHardware())))


class TestWorld(unittest.TestCase):
    def setUp(self):
        """Build a World holding one fake platform in a fake environment."""
        self.hardware = FakeHardware()
        self.frontseater = FakeFrontseater(self.hardware)
        self.backseater = FakeBackseater(self.frontseater)
        self.environment = FakeEnvironment()
        self.world = World(self.environment, platforms={"ugv1": FakePlatform(self.backseater)})

    def test_step_updates_backseater_then_frontseater(self):
        """step() runs the backseater update and both frontseater update phases."""
        self.world.step(0.1)
        self.assertTrue(self.backseater.update_called)
        self.assertTrue(self.frontseater.begin_update_called)
        self.assertTrue(self.frontseater.finish_update_called)

    def test_step_steps_each_hardware_against_the_environment(self):
        """step() passes dt and the world's environment to each hardware's step_dynamics()."""
        self.world.step(0.1)
        self.assertEqual(self.hardware.step_dynamics_called_with, (0.1, self.environment))

    def test_get_states_returns_each_hardware_state(self):
        """get_states() maps each platform_id to its hardware's state."""
        self.assertEqual(self.world.get_states(), {"ugv1": "initial_state"})

    def test_step_syncs_with_no_peers_when_only_one_backseater(self):
        """A lone backseater is asked to sync with an empty peer list."""
        self.world.step(0.1)   # must not raise with no peers to sync against
        self.assertEqual(self.backseater.sync_with_stale_peers_called_with, [])


class TestWorldMeshSync(unittest.TestCase):
    def test_step_syncs_each_backseater_against_every_other_backseater(self):
        """With full connectivity, each backseater syncs with every other backseater but not itself."""
        platform_a, platform_b, platform_c = _fake_platform(), _fake_platform(), _fake_platform()
        world = World(FakeEnvironment(), platforms={"ugv1": platform_a, "ugv2": platform_b, "ugv3": platform_c})
        backseater_a, backseater_b, backseater_c = platform_a.backseater, platform_b.backseater, platform_c.backseater

        world.step(0.1)

        self.assertCountEqual(backseater_a.sync_with_stale_peers_called_with, [backseater_b, backseater_c])
        self.assertCountEqual(backseater_b.sync_with_stale_peers_called_with, [backseater_a, backseater_c])
        self.assertCountEqual(backseater_c.sync_with_stale_peers_called_with, [backseater_a, backseater_b])


class TestWorldFaultIsolation(unittest.TestCase):
    def _raise(self, *arguments):
        """Stand in for any layer method and fail with a simulated fault."""
        raise RuntimeError("simulated fault")

    def _quiet_step(self, world):
        """Steps world with its "[World] ... failed" prints swallowed."""
        with contextlib.redirect_stdout(io.StringIO()):
            world.step(0.1)

    def test_a_failing_backseater_update_skips_only_that_platforms_frontseater(self):
        """A backseater fault skips its own frontseater's updates while the other platform runs normally."""
        broken, healthy = _fake_platform(), _fake_platform()
        broken.backseater.update = self._raise
        world = World(FakeEnvironment(), platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertFalse(broken.frontseater.begin_update_called)
        self.assertTrue(healthy.frontseater.begin_update_called)
        self.assertTrue(healthy.frontseater.finish_update_called)

    def test_a_failing_begin_update_skips_only_that_platforms_finish_update(self):
        """A begin_update() fault skips that platform's finish_update() but not the other's."""
        broken, healthy = _fake_platform(), _fake_platform()
        broken.frontseater.begin_update = self._raise
        world = World(FakeEnvironment(), platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertFalse(broken.frontseater.finish_update_called)
        self.assertTrue(healthy.frontseater.finish_update_called)

    def test_a_brain_fault_still_steps_that_platforms_hardware_and_syncs_it(self):
        """A frontseater fault still steps that platform's hardware and includes it in mesh sync."""
        environment = FakeEnvironment()
        broken, healthy = _fake_platform(), _fake_platform()
        broken.frontseater.finish_update = self._raise
        world = World(environment, platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertEqual(broken.hardware.step_dynamics_called_with, (0.1, environment))
        self.assertEqual(healthy.hardware.step_dynamics_called_with, (0.1, environment))
        self.assertEqual(broken.backseater.sync_with_stale_peers_called_with, [healthy.backseater])

    def test_a_failing_hardware_step_does_not_stop_the_others(self):
        """A step_dynamics() fault on one platform still steps and syncs the other."""
        broken, healthy = _fake_platform(), _fake_platform()
        broken.hardware.step_dynamics = self._raise
        world = World(FakeEnvironment(), platforms={"broken": broken, "healthy": healthy})
        self._quiet_step(world)
        self.assertIsNotNone(healthy.hardware.step_dynamics_called_with)
        self.assertEqual(healthy.backseater.sync_with_stale_peers_called_with, [broken.backseater])


class TestWorldHostingCheck(unittest.TestCase):
    def test_ground_plane_hardware_is_hosted_by_a_ground_plane(self):
        """A World accepts ground-plane hardware in a GroundPlaneEnv."""
        World(GroundPlaneEnv(), platforms={"ugv1": _HardwarePlatform(BicycleHardware())})   # must not raise

    def test_ground_plane_hardware_is_refused_by_another_environment(self):
        """A World raises TypeError for ground-plane hardware in another environment, naming all parties."""
        with self.assertRaises(TypeError) as raised:
            World(OtherEnvironment(), platforms={"ugv1": _HardwarePlatform(BicycleHardware())})
        message = str(raised.exception)
        for expected in ("ugv1", "BicycleHardware", "GroundPlaneEnv", "OtherEnvironment"):
            self.assertIn(expected, message)

    def test_stationary_hardware_is_hosted_by_any_environment(self):
        """StationaryHardware (environment_type None) is accepted in any environment, placed in its state type."""
        for environment in (GroundPlaneEnv(), OtherEnvironment()):
            hardware = StationaryHardware(initial_state=environment.state_type())
            World(environment, platforms={"console": _HardwarePlatform(hardware)})   # must not raise

    def test_state_of_the_wrong_type_is_refused(self):
        """A platform whose state isn't the environment's state_type is rejected, naming both types."""
        with self.assertRaises(TypeError) as raised:
            World(GroundPlaneEnv(), platforms={"console": _HardwarePlatform(StationaryHardware(State()))})
        message = str(raised.exception)
        for expected in ("console", "StationaryHardware", "State", "GroundPlaneState"):
            self.assertIn(expected, message)

    def test_environment_without_state_type_is_refused(self):
        """An environment that doesn't declare state_type is rejected with a TypeError naming the attribute."""
        class UndeclaredEnvironment(Environment):
            """Forgets state_type."""

        with self.assertRaises(TypeError) as raised:
            World(UndeclaredEnvironment(), platforms={"console": _HardwarePlatform(StationaryHardware())})
        self.assertIn("state_type", str(raised.exception))

    def test_ground_plane_states_are_reported_as_given(self):
        """A GroundPlaneEnv World reports each platform's GroundPlaneState unchanged."""
        hardware = BicycleHardware(initial_state=GroundPlaneState(x=2.0, y=3.0))
        world = World(GroundPlaneEnv(), platforms={"ugv1": _HardwarePlatform(hardware)})
        self.assertIs(world.get_states()["ugv1"], hardware.state)

    def test_hardware_without_environment_type_is_refused(self):
        """Hardware that doesn't declare environment_type is rejected with a TypeError naming the attribute."""
        class UndeclaredHardware:
            state = None

        with self.assertRaises(TypeError) as raised:
            World(GroundPlaneEnv(), platforms={"mystery": _HardwarePlatform(UndeclaredHardware())})
        self.assertIn("environment_type", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
