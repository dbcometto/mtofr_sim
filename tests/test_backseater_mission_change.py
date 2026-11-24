"""Tests for Backseater._detect_mission_change(): when a Backseater's own Mission
database entry becomes a different object than the mission graph currently driving
update(), it re-declares the new graph's knowledge keys, hands the new graph's start
node's capability requests to the Frontseater (which naturally drops whatever was active under
the old graph, since it's no longer in the new dict), jumps the active node to the new
graph's declared start node — all within the same update() tick that detects the
change. Detection is by object identity (mission_database.get(platform_id) is not
self.mission_graph), not deep equality."""
import unittest

from mtofr.core.capability import Capability, CapabilityRegistry
from mtofr.database import KnowledgeDatabase
from mtofr.platform.backseater import Backseater
from mtofr.platform.frontseater import Frontseater


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _Idle(Capability):
    """A capability that does nothing."""
    ipl_type = "idle"
    description = "Does nothing."


class _RecordingFrontseater(Frontseater):
    """Fake Frontseater advertising one no-input, no-output capability ("idle"),
    recording every set_active_capabilities() call so tests can assert on
    start/stop behavior without a real MPC/hardware stack."""
    def __init__(self):
        """Start with no active capability requests and nothing stopped."""
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([_Idle])
        self.active_request_names = set()   # what the last set_active_capabilities() call contained
        self.stopped_names = []                # every name that has ever dropped out of that dict

    def compute_controls(self, state) -> dict:
        """Command nothing."""
        return {}

    def capabilities(self) -> CapabilityRegistry:
        """Return the one-capability ("idle") registry."""
        return self._registry

    def set_active_capabilities(self, capability_requests: dict) -> None:
        """Record names that dropped out since the last call, then remember the new set."""
        for name in self.active_request_names - capability_requests.keys():
            self.stopped_names.append(name)
        self.active_request_names = set(capability_requests)

    def describe_status(self) -> dict:
        """Report a fixed idle status."""
        return {"overall": "idle", "capabilities": {}}


def _make_backseater(platform_id="ugv1"):
    """Build a Backseater over a recording Frontseater, running an "old" graph whose start node runs "idle"."""
    frontseater = _RecordingFrontseater()
    old_graph = {
        "knowledge": {"counter": {"type": int, "value": 1}},
        "nodes": {"old_node": {"capabilities": {"idle": {"capability": "idle", "inputs": {}}}}},
        "edges": {},
        "start": "old_node",
    }
    backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                             mission_graph=old_graph, platform_id=platform_id)
    return backseater, frontseater, old_graph


class TestMissionChangeNoOpsUntilFirstWrite(unittest.TestCase):
    def test_no_change_detected_before_any_mission_write(self):
        """With no Mission write yet, update() keeps the constructor's graph and start node."""
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()
        self.assertIs(backseater.mission_graph, old_graph)
        self.assertEqual(backseater.active_node_id, "old_node")

    def test_no_change_detected_when_platform_id_is_none(self):
        """A Backseater with no platform_id keeps its constructor's graph across update()."""
        frontseater = _RecordingFrontseater()
        old_graph = {"knowledge": {}, "nodes": {"n1": {"capabilities": {}}}, "edges": {}, "start": "n1"}
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 mission_graph=old_graph)
        backseater.update()
        self.assertIs(backseater.mission_graph, old_graph)


class TestMissionChangeAppliesNewGraph(unittest.TestCase):
    def test_knowledge_keys_reset_to_new_graph_defaults(self):
        """After a mission change, the new graph's keys are reset to their declared defaults."""
        backseater, frontseater, old_graph = _make_backseater()
        backseater.knowledge_database.set("counter", 99)

        new_graph = {
            "knowledge": {"counter": {"type": int, "value": 1}},
            "nodes": {"new_node": {"capabilities": {}}},
            "edges": {},
            "start": "new_node",
        }
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertEqual(backseater.knowledge_database.get("counter"), 1)

    def test_old_capability_request_is_dropped_from_the_frontseaters_active_set(self):
        """A mission change stops the old graph's running capability request."""
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()  # starts "idle" under old_node
        self.assertIn("idle", frontseater.active_request_names)

        new_graph = {"knowledge": {}, "nodes": {"new_node": {"capabilities": {}}}, "edges": {}, "start": "new_node"}
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertIn("idle", frontseater.stopped_names)
        self.assertNotIn("idle", frontseater.active_request_names)

    def test_active_node_jumps_to_new_graph_start_and_starts_capability_requests_same_tick(self):
        """In the tick that detects the change, the new start node becomes active and its capability requests start."""
        backseater, frontseater, old_graph = _make_backseater()
        backseater.update()

        new_graph = {
            "knowledge": {},
            "nodes": {"new_node": {"capabilities": {"idle": {"capability": "idle", "inputs": {}}}}},
            "edges": {},
            "start": "new_node",
        }
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertEqual(backseater.active_node_id, "new_node")
        self.assertIn("idle", frontseater.active_request_names)

    def test_mission_change_unblocks_a_previously_blocked_mission(self):
        """A mission blocked by an unknown capability is unblocked when a new graph is written."""
        frontseater = _RecordingFrontseater()
        old_graph = {
            "knowledge": {},
            "nodes": {"n1": {"capabilities": {"bad": {"capability": "does_not_exist", "inputs": {}}}}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 mission_graph=old_graph, platform_id="ugv1")
        backseater.update()
        self.assertTrue(backseater._blocked)

        new_graph = {"knowledge": {}, "nodes": {"new_node": {"capabilities": {}}}, "edges": {}, "start": "new_node"}
        backseater.write_mission(new_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertFalse(backseater._blocked)
        self.assertEqual(backseater.active_node_id, "new_node")

    def test_no_change_detected_when_entry_is_the_same_object_again(self):
        """Rewriting the same graph object is not a change: same node, nothing stopped."""
        backseater, frontseater, old_graph = _make_backseater()
        backseater.write_mission(old_graph, writer_platform_id="ugv1")
        backseater.update()

        self.assertIs(backseater.mission_graph, old_graph)
        self.assertEqual(backseater.active_node_id, "old_node")
        self.assertEqual(frontseater.stopped_names, [])


if __name__ == "__main__":
    unittest.main()