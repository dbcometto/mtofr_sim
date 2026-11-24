"""Tests for the mesh-routed Mission write (Backseater.write_mission() with a
target_platform_id, reached via publish("mission", target_id, graph)) and the live
PlatformRecord each Backseater self-publishes and gossips: an operator platform writes a
peer's Mission entry into its *own* Mission database, every check done there, write-side,
against its own (gossiped) copies of both PlatformRecords, and mesh sync delivers it.
Backseaters over fake Frontseaters, synced directly; no World or MPC involved."""
import unittest

from mtofr.core.capability import Capability, CapabilityRegistry
from mtofr.database import KnowledgeDatabase, PlatformRecord
from mtofr.mission import MissionStructuralError
from mtofr.platform.backseater import Backseater
from mtofr.platform.frontseater import Frontseater


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _FakeFrontseater(Frontseater):
    """Fake Frontseater advertising one no-input, no-output capability, "idle", and
    reporting each active request as "running"."""
    def __init__(self):
        """Advertise the one "idle" capability, with nothing active yet."""
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([Capability(ipl_type="idle", description="Does nothing.")])
        self._active_names = []

    def compute_controls(self, state) -> dict:
        """Command nothing."""
        return {}

    def capabilities(self) -> CapabilityRegistry:
        """Return the one-capability ("idle") registry."""
        return self._registry

    def set_active_capabilities(self, capability_requests: dict) -> None:
        """Remember which request names are active, for describe_status()."""
        self._active_names = list(capability_requests)

    def describe_status(self) -> dict:
        """"running" per active request; overall "busy" or "idle"."""
        overall = "busy" if self._active_names else "idle"
        return {"overall": overall, "capabilities": {name: "running" for name in self._active_names}}


def _graph(node_id: str, capability: str = "idle") -> dict:
    """A one-node graph running one request of `capability`, with no knowledge or edges."""
    return {
        "knowledge": {},
        "nodes": {node_id: {"capabilities": {"work": {"capability": capability, "inputs": {}, "outputs": {}}}}},
        "edges": {},
        "start": node_id,
    }


def _make_backseater(platform_id: str, privilege_level: int = 1) -> Backseater:
    """Build a Backseater over a fake Frontseater, booting on a one-node "boot" graph."""
    return Backseater(frontseater=_FakeFrontseater(), knowledge_database=KnowledgeDatabase(),
                       mission_graph=_graph("boot"), platform_id=platform_id, privilege_level=privilege_level)


class TestLivePlatformRecord(unittest.TestCase):
    def test_update_publishes_the_live_status_into_the_own_record(self):
        """After update(), the own record carries the active node, blocked flag, and per-request statuses."""
        ugv1 = _make_backseater("ugv1")
        ugv1.update()
        status = ugv1.platform_database.get("ugv1").status
        self.assertEqual(status.status, "busy")
        self.assertEqual(status.active_node_id, "boot")
        self.assertFalse(status.blocked)
        self.assertEqual(status.capability_statuses["work"]["status"], "running")

    def test_an_unchanged_status_is_not_republished(self):
        """A second update() with nothing changed leaves the record's timestamp alone."""
        ugv1 = _make_backseater("ugv1")
        ugv1.update()
        first_timestamp = ugv1.platform_database.timestamp_of("ugv1")
        ugv1.update()
        self.assertEqual(ugv1.platform_database.timestamp_of("ugv1"), first_timestamp)

    def test_live_status_and_capabilities_are_gossiped_to_a_peer(self):
        """A peer's copy of the record, after sync, carries the live status and the capability registry."""
        ugv1 = _make_backseater("ugv1")
        observer = _make_backseater("observer")
        ugv1.update()
        observer.sync_with(ugv1)
        record = observer.platform_database.get("ugv1")
        self.assertEqual(record.status.active_node_id, "boot")
        self.assertIsNotNone(record.capabilities.get("idle"))

    def test_the_boot_mission_is_gossiped_to_a_peer(self):
        """A peer can read a platform's boot mission (never pushed) from its own Mission database."""
        ugv1 = _make_backseater("ugv1")
        observer = _make_backseater("observer")
        observer.sync_with(ugv1)
        self.assertIs(observer.mission_database.get("ugv1"), ugv1.mission_graph)


class TestMeshMissionPush(unittest.TestCase):
    def setUp(self):
        """Build an operator (privilege 0) and ugv1 (privilege 1) that already know each other via one sync."""
        self.operator = _make_backseater("operator", privilege_level=0)
        self.ugv1 = _make_backseater("ugv1", privilege_level=1)
        self.operator.sync_with(self.ugv1)

    def test_a_push_lands_in_the_writers_own_mission_database(self):
        """publish("mission", target, graph) writes the target's entry locally, with the writer as origin."""
        graph = _graph("patrol")
        self.operator.publish("mission", "ugv1", graph)
        self.assertIs(self.operator.mission_database.get("ugv1"), graph)
        self.assertEqual(self.operator.mission_database.origin_of("ugv1"), "operator")

    def test_the_target_adopts_a_pushed_mission_after_sync(self):
        """Once synced, the target's next update() switches to the pushed graph's start node."""
        graph = _graph("patrol")
        self.operator.publish("mission", "ugv1", graph)
        self.operator.sync_with(self.ugv1)
        self.ugv1.update()
        self.assertIs(self.ugv1.mission_graph, graph)
        self.assertEqual(self.ugv1.active_node_id, "patrol")

    def test_a_lower_privilege_writer_is_refused(self):
        """ugv1 (privilege 1) may not push the operator (privilege 0) a mission."""
        before = self.ugv1.mission_database.get("operator")
        with self.assertRaises(PermissionError):
            self.ugv1.publish("mission", "operator", _graph("patrol"))
        self.assertIs(self.ugv1.mission_database.get("operator"), before)

    def test_an_unknown_target_is_refused(self):
        """A push to a platform not yet in this platform's PlatformDatabase raises PermissionError."""
        with self.assertRaises(PermissionError):
            self.operator.publish("mission", "ugv9", _graph("patrol"))

    def test_a_target_with_unknown_capabilities_is_refused(self):
        """A target whose record advertises no capabilities can't be binding-checked, so the push is refused."""
        self.operator.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))
        with self.assertRaises(MissionStructuralError):
            self.operator.publish("mission", "ugv2", _graph("patrol"))

    def test_an_unbindable_graph_is_refused_against_the_targets_gossiped_capabilities(self):
        """A capability the target doesn't advertise is caught at the writer, before anything lands."""
        with self.assertRaises(MissionStructuralError):
            self.operator.publish("mission", "ugv1", _graph("patrol", capability="fly"))
        self.assertEqual(self.operator.mission_database.get("ugv1")["start"], "boot")


if __name__ == "__main__":
    unittest.main()
