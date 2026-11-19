"""Tests for Platform/PlatformSpec and the per-type spec factories that build them."""
import unittest

from mtofr.core.capability import CapabilityRegistry
from mtofr.core.clock import Clock
from mtofr.environments.anywhere.platforms.interface.spec import interface
from mtofr.environments.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.environments.anywhere.platforms.interface.frontseater import MissionEditorFrontseater
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater
from mtofr.environments.ground_plane.state import GroundPlaneState
from mtofr.platform.frontseater import Frontseater
from mtofr.platform.platform import Platform, PlatformSpec


def _build_platform(test_case: unittest.TestCase, spec: PlatformSpec) -> Platform:
    """Builds a Platform and registers its shutdown, since a bicycle UGV owns an MPC worker process."""
    platform = Platform(spec)
    test_case.addCleanup(platform.shutdown)
    return platform


class _RecordingFrontseater(Frontseater):
    """Minimal Frontseater that records attach()/shutdown() calls, so forwarding can be checked."""
    def __init__(self):
        """Own a ConsoleHardware and start with no attach or shutdown calls recorded."""
        self.hardware = ConsoleHardware()
        self.attach_calls = []
        self.shutdown_calls = 0

    def compute_controls(self, state):
        """Command nothing."""
        return {}

    def capabilities(self):
        """Advertise no capabilities."""
        return CapabilityRegistry([])

    def set_active_capabilities(self, capability_requests):
        """Ignore capability request changes."""
        pass

    def describe_status(self):
        """Always report idle with no capability requests."""
        return {"overall": "idle", "capabilities": {}}

    def attach(self, world, window_root=None):
        """Record the world and window root this frontseater was attached with."""
        self.attach_calls.append((world, window_root))

    def shutdown(self):
        """Count shutdown() calls."""
        self.shutdown_calls += 1


class TestPlatform(unittest.TestCase):
    def test_exposes_every_layer_of_the_stack(self):
        """A Platform's layer attributes are the same objects the layers hold of each other."""
        platform = _build_platform(self, bicycle_ugv("ugv1", 0.0, 0.0))
        self.assertIs(platform.backseater.frontseater, platform.frontseater)
        self.assertIs(platform.frontseater.hardware, platform.hardware)
        self.assertIs(platform.backseater.knowledge_database, platform.knowledge_database)

    def test_platform_id_cascades_through_every_layer(self):
        """The spec's platform_id reaches the Platform, Backseater, Frontseater, and Hardware."""
        platform = _build_platform(self, bicycle_ugv("ugv1", 0.0, 0.0))
        self.assertEqual(platform.platform_id, "ugv1")
        self.assertEqual(platform.backseater.platform_id, "ugv1")
        self.assertEqual(platform.frontseater.platform_id, "ugv1")
        self.assertEqual(platform.hardware.platform_id, "ugv1")

    def test_no_mission_graph_falls_back_to_the_frontseater_default(self):
        """A spec without a mission graph boots the frontseater's default graph."""
        platform = _build_platform(self, bicycle_ugv("ugv1", 0.0, 0.0))
        default_start = platform.frontseater.default_mission_graph()["start"]
        self.assertEqual(platform.backseater.active_node_id, default_start)

    def test_given_mission_graph_is_used(self):
        """A spec's mission graph is loaded and its start node made active."""
        mission_graph = {"knowledge": {}, "nodes": {"only": {"capabilities": {}}}, "edges": {}, "start": "only"}
        platform = _build_platform(self, bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_graph))
        self.assertEqual(platform.backseater.active_node_id, "only")

    def test_privilege_level_is_seeded_into_the_platform_database(self):
        """The spec's privilege level appears in the platform's own PlatformRecord."""
        platform = _build_platform(self, bicycle_ugv("ugv1", 0.0, 0.0, privilege_level=3))
        self.assertEqual(platform.backseater.platform_database.get("ugv1").privilege_level, 3)

    def test_clock_and_sync_interval_reach_the_backseater(self):
        """The spec's clock and sync_interval are handed to the Backseater."""
        clock = Clock(offset=5.0)
        spec = PlatformSpec("console", build_frontseater=lambda debug: _RecordingFrontseater(),
                            clock=clock, sync_interval=2.5)
        platform = _build_platform(self, spec)
        self.assertIs(platform.backseater.clock, clock)
        self.assertEqual(platform.backseater.sync_interval, 2.5)

    def test_attach_and_shutdown_forward_to_the_frontseater(self):
        """Platform.attach() and shutdown() each call through to the frontseater once."""
        platform = Platform(PlatformSpec("console", build_frontseater=lambda debug: _RecordingFrontseater()))
        world = object()
        platform.attach(world, "root")
        platform.shutdown()
        self.assertEqual(platform.frontseater.attach_calls, [(world, "root")])
        self.assertEqual(platform.frontseater.shutdown_calls, 1)

    def test_base_frontseater_attach_is_a_no_op(self):
        """A frontseater that doesn't override attach() accepts any world without error."""
        frontseater = BicycleFrontseater(hardware=BicycleHardware())
        self.addCleanup(frontseater.shutdown)
        frontseater.attach(object(), None)   # must not raise


class TestSpecFactories(unittest.TestCase):
    def test_bicycle_ugv_builds_bicycle_hardware_at_its_start_position(self):
        """bicycle_ugv() builds a bicycle stack placed at the given start position."""
        platform = _build_platform(self, bicycle_ugv("ugv1", 3.0, -4.0))
        self.assertIsInstance(platform.hardware, BicycleHardware)
        self.assertIsInstance(platform.frontseater, BicycleFrontseater)
        self.assertEqual((platform.hardware.state.x, platform.hardware.state.y), (3.0, -4.0))

    def test_bicycle_ugv_defaults_to_privilege_one(self):
        """bicycle_ugv() defaults to privilege level 1."""
        self.assertEqual(bicycle_ugv("ugv1", 0.0, 0.0).privilege_level, 1)

    def test_interface_builds_console_hardware_at_its_initial_state(self):
        """interface() builds a mission-editor stack on ConsoleHardware placed at the given state."""
        platform = _build_platform(self, interface("interface", GroundPlaneState(x=1.0, y=2.0)))
        self.assertIsInstance(platform.hardware, ConsoleHardware)
        self.assertIsInstance(platform.frontseater, MissionEditorFrontseater)
        self.assertEqual((platform.hardware.state.x, platform.hardware.state.y), (1.0, 2.0))

    def test_interface_defaults_to_outranking_an_ordinary_platform(self):
        """interface() defaults to a higher privilege (lower level) than a default bicycle UGV."""
        self.assertLess(interface("interface", GroundPlaneState()).privilege_level,
                        bicycle_ugv("ugv1", 0.0, 0.0).privilege_level)

    def test_spec_builds_nothing_until_a_platform_is_constructed(self):
        """A PlatformSpec defers building its frontseater until Platform(), which passes its debug flag."""
        built = []
        spec = PlatformSpec("console", build_frontseater=lambda debug: built.append(debug) or _RecordingFrontseater())
        self.assertEqual(built, [])
        Platform(spec, debug=True)
        self.assertEqual(built, [True])


if __name__ == "__main__":
    unittest.main()
