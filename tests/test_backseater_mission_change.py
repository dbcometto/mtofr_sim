"""Tests for Backseater._detect_mission_change(): increment 3 of the peer-to-peer mesh
redesign's build order step 3. Covers the CLAUDE.md-specified behavior: when a
Backseater's own Mission database entry becomes a different object than the mission
graph currently driving update(), it re-declares the new graph's knowledge keys,
cancels every currently-running capability from the old graph, jumps the active node
to the new graph's declared start node, and starts that node's primitives — all within
the same update() tick that detects the change. Detection is by object identity
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
    recording every start_capability()/cancel() call so tests can assert on
    cancellation/restart behavior without a real MPC/hardware stack."""
    def __init__(self):
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([
            Capability(ipl_type="idle", description="Does nothing."),
        ])
        self.started = []
        self.cancelled = []
        self._next_handle = 0

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def start_capability(self, capability: str, inputs: dict, outputs: dict) -> str:
        self._next_handle += 1
        handle = f"handle-{self._next_handle}"
        self.started.append(handle)
        return handle

    def poll_status(self, handle: str) -> dict:
        return {"status": "in_progress", "outputs": {}}

    def cancel(self, handle: str) -> None:
        self.cancelled.append(handle)


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

    def test_old_capability_handles_are_cancelled(self):
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()  # starts "idle" under old_node
        self.assertEqual(len(frontseater.started), 1)
        old_handle = frontseater.started[0]

        new_graph = {"knowledge": {}, "nodes": {"new_node": {"primitives": {}}}, "edges": {}, "start": "new_node"}
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertIn(old_handle, frontseater.cancelled)

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
        self.assertIn("idle", backseater._statuses)

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
        self.assertEqual(frontseater.cancelled, [])


if __name__ == "__main__":
    unittest.main()