"""Tests for step 5: a platform's default mission graph — what a Backseater falls back
to when constructed with mission_graph=None, so a platform boots into a safe idle
behavior before a real mission is delegated to it (see CLAUDE.md's remaining build
order, step 5)."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, CapabilityRegistry
from mtofr.database import KnowledgeDatabase
from mtofr.world.base import Frontseater
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _BareFrontseater(Frontseater):
    """A Frontseater that doesn't override default_mission_graph() — exercises the base
    Frontseater implementation directly."""
    def __init__(self):
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([Capability(ipl_type="idle", description="Does nothing.")])

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def set_active_primitives(self, primitives: dict) -> None:
        pass

    def describe_status(self) -> dict:
        return {"overall": "idle", "primitives": {}}


class TestBaseFrontseaterDefaultMissionGraph(unittest.TestCase):
    def test_base_default_mission_graph_is_an_inert_placeholder(self):
        graph = _BareFrontseater().default_mission_graph()
        self.assertEqual(graph["start"], "startup")
        self.assertEqual(graph["nodes"], {"startup": {"primitives": {}}})
        self.assertEqual(graph["edges"], {})


class TestBackseaterFallsBackToFrontseaterDefault(unittest.TestCase):
    def test_backseater_with_no_mission_graph_uses_the_frontseaters_default(self):
        frontseater = _BareFrontseater()
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")
        self.assertEqual(backseater.mission_graph, frontseater.default_mission_graph())
        self.assertEqual(backseater.active_node_id, "startup")

    def test_backseater_with_an_explicit_mission_graph_does_not_use_the_default(self):
        frontseater = _BareFrontseater()
        explicit_graph = {"knowledge": {}, "nodes": {"n1": {"primitives": {}}}, "edges": {}, "start": "n1"}
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 mission_graph=explicit_graph, platform_id="ugv1")
        self.assertEqual(backseater.active_node_id, "n1")


class TestBicycleFrontseaterDefaultMissionEndToEnd(unittest.TestCase):
    def setUp(self):
        self.hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=self.hardware)
        self.addCleanup(self.frontseater.shutdown)
        self.backseater = Backseater(frontseater=self.frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

    def test_boots_onto_the_startup_node_running_the_stopwatch(self):
        self.assertEqual(self.backseater.active_node_id, "startup")
        self.backseater.update()
        self.assertIn("loiter", self.frontseater.describe_status()["primitives"])

    def test_elapsed_time_advances_as_the_default_mission_runs(self):
        # Backseater only hands the primitive set to the Frontseater; actually running
        # it (and publishing elapsed_time) happens in the Frontseater's own update(),
        # driven independently every tick (see World.step()).
        self.backseater.update()
        self.frontseater.update()
        self.hardware.state.t += 5.0
        self.backseater.update()
        self.frontseater.update()
        self.assertAlmostEqual(self.backseater.knowledge_database.get("startup/elapsed_time"), 5.0)


if __name__ == "__main__":
    unittest.main()