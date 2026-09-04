"""Tests for Backseater._detect_mission_change(): increment 3 of the peer-to-peer mesh
redesign's build order step 3. Covers the CLAUDE.md-specified behavior: when a
Backseater's own Mission database entry becomes a different object than the mission
graph currently driving update(), it re-declares the new graph's knowledge keys, hands
the new graph's start node's primitives to the Frontseater (which naturally drops
whatever was active under the old graph, since it's no longer in the new dict), jumps
the active node to the new graph's declared start node — all within the same update()
tick that detects the change. Detection is by object identity
(mission_database.get(platform_id) is not self.mission_graph), not deep equality."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import KnowledgeDatabase
from mtofr.world.base import Frontseater


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _RecordingFrontseater(Frontseater):
    """Fake Frontseater advertising one no-input, no-output capability ("idle"),
    recording every set_active_primitives() call so tests can assert on
    start/stop behavior without a real MPC/hardware stack."""
    def __init__(self):
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([
            Capability(ipl_type="idle", description="Does nothing."),
        ])
        self.active_primitive_names = set()   # what the last set_active_primitives() call contained
        self.stopped_names = []                # every name that has ever dropped out of that dict

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def set_active_primitives(self, primitives: dict) -> None:
        for name in self.active_primitive_names - primitives.keys():
            self.stopped_names.append(name)
        self.active_primitive_names = set(primitives)

    def describe_status(self) -> dict:
        return {"overall": "idle", "primitives": {}}


def _make_backseater(platform_id="ugv1"):
    frontseater = _RecordingFrontseater()
    old_graph = {
        "knowledge": {"counter": {"type": int, "value": 1}},
        "nodes": {"old_node": {"primitives": {"idle": {"capability": "idle", "inputs": {}}}}},
        "edges": {},
        "start": "old_node",
    }
    backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                             mission_graph=old_graph, platform_id=platform_id)
    return backseater, frontseater, old_graph


class TestMissionChangeNoOpsUntilFirstWrite(unittest.TestCase):
    def test_no_change_detected_before_any_mission_write(self):
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()
        self.assertIs(backseater.mission_graph, old_graph)
        self.assertEqual(backseater.active_node_id, "old_node")

    def test_no_change_detected_when_platform_id_is_none(self):
        frontseater = _RecordingFrontseater()
        old_graph = {"knowledge": {}, "nodes": {"n1": {"primitives": {}}}, "edges": {}, "start": "n1"}
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 mission_graph=old_graph)
        backseater.update()
        self.assertIs(backseater.mission_graph, old_graph)


class TestMissionChangeAppliesNewGraph(unittest.TestCase):
    def test_knowledge_keys_reset_to_new_graph_defaults(self):
        backseater, frontseater, old_graph = _make_backseater()
        backseater.knowledge_database.set("counter", 99)

        new_graph = {
            "knowledge": {"counter": {"type": int, "value": 1}},
            "nodes": {"new_node": {"primitives": {}}},
            "edges": {},
            "start": "new_node",
        }
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertEqual(backseater.knowledge_database.get("counter"), 1)

    def test_old_primitive_is_dropped_from_the_frontseaters_active_set(self):
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()  # starts "idle" under old_node
        self.assertIn("idle", frontseater.active_primitive_names)

        new_graph = {"knowledge": {}, "nodes": {"new_node": {"primitives": {}}}, "edges": {}, "start": "new_node"}
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertIn("idle", frontseater.stopped_names)
        self.assertNotIn("idle", frontseater.active_primitive_names)

    def test_active_node_jumps_to_new_graph_start_and_starts_primitives_same_tick(self):
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()

        new_graph = {
            "knowledge": {},
            "nodes": {"new_node": {"primitives": {"idle": {"capability": "idle", "inputs": {}}}}},
            "edges": {},
            "start": "new_node",
        }
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertEqual(backseater.active_node_id, "new_node")
        self.assertIn("idle", frontseater.active_primitive_names)

    def test_mission_change_unblocks_a_previously_blocked_mission(self):
        frontseater = _RecordingFrontseater()
        old_graph = {
            "knowledge": {},
            "nodes": {"n1": {"primitives": {"bad": {"capability": "does_not_exist", "inputs": {}}}}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 mission_graph=old_graph, platform_id="ugv1")
        backseater.update()
        self.assertTrue(backseater._blocked)

        new_graph = {"knowledge": {}, "nodes": {"new_node": {"primitives": {}}}, "edges": {}, "start": "new_node"}
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertFalse(backseater._blocked)
        self.assertEqual(backseater.active_node_id, "new_node")

    def test_no_change_detected_when_entry_is_the_same_object_again(self):
        backseater, frontseater, old_graph = _make_backseater()
        backseater.write_mission(old_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertIs(backseater.mission_graph, old_graph)
        self.assertEqual(backseater.active_node_id, "old_node")
        self.assertEqual(frontseater.stopped_names, [])


if __name__ == "__main__":
    unittest.main()