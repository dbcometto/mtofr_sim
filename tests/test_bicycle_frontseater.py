"""Tests for BicycleFrontseater's capability implementations (set_active_primitives/
_step_active_primitives/describe_status) exercised directly, independent of any
Backseater/mission-graph driving them. A capability calls query()/publish() on its own
Backseater, so these tests wire in a minimal fake backseater (a plain dict-backed
query/publish) instead of a full Backseater."""
import unittest

from mtofr.database import Location
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class _FakeBackseater:
    """Minimal query()/publish() stand-in over a plain dict — enough for a capability to
    read its bound inputs and write its outputs, without needing a real Backseater/Knowledge."""
    def __init__(self, knowledge: dict):
        self.knowledge = knowledge

    def query(self, database_name: str, key):
        assert database_name == "knowledge"
        return self.knowledge[key]

    def publish(self, database_name: str, key, value, timestamp=None) -> None:
        assert database_name == "knowledge"
        self.knowledge[key] = value


class TestBicycleFrontseaterCapabilities(unittest.TestCase):
    def setUp(self):
        self.hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=self.hardware)
        self.knowledge = {}
        self.frontseater.backseater = _FakeBackseater(self.knowledge)

    def tearDown(self):
        self.frontseater.shutdown()

    def _activate_move_to(self, target: Location, tolerance: float, with_output=True, name="nav"):
        self.knowledge["target"] = target
        self.knowledge["tolerance"] = tolerance
        outputs = {"arrived": "arrived"} if with_output else {}
        self.frontseater.set_active_primitives({
            name: {"capability": "move_to", "inputs": {"target": "target", "tolerance": "tolerance"}, "outputs": outputs}
        })

    def _activate_avoid(self, point: Location, radius: float, with_output=True, name="avoid"):
        self.knowledge["point"] = point
        self.knowledge["radius"] = radius
        outputs = {"registered": "registered"} if with_output else {}
        self.frontseater.set_active_primitives({
            name: {"capability": "avoid", "inputs": {"point": "point", "radius": "radius"}, "outputs": outputs}
        })

    def _activate_stopwatch(self, with_output=True, name="watch"):
        outputs = {"elapsed_time": "elapsed_time"} if with_output else {}
        self.frontseater.set_active_primitives({name: {"capability": "stopwatch", "inputs": {}, "outputs": outputs}})

    def test_capabilities_advertises_move_to_and_avoid(self):
        registry = self.frontseater.capabilities()
        self.assertIsNotNone(registry.get("move_to"))
        self.assertIsNotNone(registry.get("avoid"))

    def test_capabilities_advertises_stopwatch(self):
        self.assertIsNotNone(self.frontseater.capabilities().get("stopwatch"))

    def test_set_active_primitives_unknown_capability_raises(self):
        with self.assertRaises(ValueError):
            self.frontseater.set_active_primitives({"fly": {"capability": "fly", "inputs": {}, "outputs": {}}})

    #==========# move_to #==========#

    def test_move_to_starts_en_route_while_far_from_target(self):
        self._activate_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater._step_active_primitives()
        self.assertEqual(self.frontseater.describe_status()["primitives"]["nav"], "en route")

    def test_move_to_reports_arrived_false_while_far_from_target(self):
        self._activate_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater._step_active_primitives()
        self.assertEqual(self.knowledge["arrived"], False)

    def test_move_to_reports_arrived_once_within_tolerance(self):
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self._activate_move_to(Location(0.1, 0.0), 0.5)
        self.frontseater._step_active_primitives()
        self.assertEqual(self.frontseater.describe_status()["primitives"]["nav"], "arrived")

    def test_move_to_publishes_arrived_to_its_bound_knowledge_key(self):
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self._activate_move_to(Location(0.1, 0.0), 0.5)
        self.frontseater._step_active_primitives()
        self.assertTrue(self.knowledge["arrived"])

    def test_move_to_reads_a_retargeted_knowledge_key_on_the_next_step(self):
        self._activate_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater._step_active_primitives()
        self.knowledge["target"] = Location(0.0, 0.0)
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self.frontseater._step_active_primitives()
        self.assertEqual(self.frontseater.describe_status()["primitives"]["nav"], "arrived")

    def test_deactivating_a_move_to_clears_its_target(self):
        self._activate_move_to(Location(5.0, 0.0), 0.5)
        self.frontseater.set_active_primitives({})
        self.assertIsNone(self.frontseater._active_target)

    def test_compute_controls_is_idle_with_no_active_target(self):
        controls = self.frontseater.compute_controls(self.hardware.read_state())
        self.assertEqual(controls, {"vel": 0.0, "steer": 0.0})

    #==========# avoid #==========#

    def test_avoid_reports_registered(self):
        self._activate_avoid(Location(0.0, 0.0), 1.0)
        self.frontseater._step_active_primitives()
        self.assertEqual(self.frontseater.describe_status()["primitives"]["avoid"], "registered")

    def test_avoid_publishes_registered_to_its_bound_knowledge_key(self):
        self._activate_avoid(Location(0.0, 0.0), 1.0)
        self.frontseater._step_active_primitives()
        self.assertTrue(self.knowledge["registered"])

    #==========# stopwatch #==========#

    def test_stopwatch_reports_zero_elapsed_time_right_after_starting(self):
        self._activate_stopwatch()
        self.frontseater._step_active_primitives()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 0.0)

    def test_stopwatch_elapsed_time_advances_with_simulation_time(self):
        self._activate_stopwatch()
        self.hardware.state.t += 5.0
        self.frontseater._step_active_primitives()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 5.0)

    def test_stopwatch_publishes_elapsed_time_to_its_bound_knowledge_key(self):
        self._activate_stopwatch()
        self.hardware.state.t += 3.0
        self.frontseater._step_active_primitives()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 3.0)

    def test_restarting_the_stopwatch_resets_elapsed_time_to_zero(self):
        self._activate_stopwatch(name="watch")
        self.hardware.state.t += 10.0
        self.frontseater._step_active_primitives()

        self.frontseater.set_active_primitives({})   # stop it
        self._activate_stopwatch(name="watch")        # start a fresh instance
        self.frontseater._step_active_primitives()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 0.0)

    #==========# default mission graph #==========#

    def test_default_mission_graph_starts_on_a_stopwatch_only_startup_node(self):
        graph = self.frontseater.default_mission_graph()
        self.assertEqual(graph["start"], "startup")
        primitives = graph["nodes"]["startup"]["primitives"]
        self.assertEqual(len(primitives), 1)
        loiter = next(iter(primitives.values()))
        self.assertEqual(loiter["capability"], "stopwatch")

    def test_default_mission_graph_declares_its_own_output_knowledge_key(self):
        graph = self.frontseater.default_mission_graph()
        loiter = graph["nodes"]["startup"]["primitives"]["loiter"]
        output_key = loiter["outputs"]["elapsed_time"]
        self.assertIn(output_key, graph["knowledge"])
        self.assertEqual(graph["knowledge"][output_key]["type"], float)

    def test_default_mission_graph_has_no_edges(self):
        graph = self.frontseater.default_mission_graph()
        self.assertEqual(graph["edges"], {})


if __name__ == "__main__":
    unittest.main()