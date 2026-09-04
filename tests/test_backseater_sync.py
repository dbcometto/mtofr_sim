"""Tests for Backseater.sync_with()/sync_with_stale_peers() (increment 5 of the
peer-to-peer mesh redesign's build order step 3): pairwise last-write-wins
reconciliation across all three databases (Knowledge/Mission/Platform), the
per-peer clock handshake, the checksum short-circuit that skips a full reconcile
when nothing changed since the last sync with a given peer, and the staleness
gate that decides when a sync is due. No World involved — sync_with()/
sync_with_stale_peers() are called directly against manually constructed
Backseaters, per CLAUDE.md's "Tested with two Backseaters directly, no World
involved."."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, CapabilityRegistry
from mtofr.database import KnowledgeDatabase, PlatformRecord, PlatformStatus
from mtofr.world.base import Frontseater


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _FakeFrontseater(Frontseater):
    """Fake Frontseater advertising one no-input, no-output capability, just enough
    for Backseater construction — no real MPC/hardware stack needed for sync tests."""
    def __init__(self):
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([
            Capability(ipl_type="idle", description="Does nothing."),
        ])

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def set_active_primitives(self, primitives: dict) -> None:
        pass

    def describe_status(self) -> dict:
        return {"overall": "idle", "primitives": {}}


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}


def _make_backseater(platform_id: str, privilege_level: int = 1, sync_interval: float = 1.0) -> Backseater:
    return Backseater(frontseater=_FakeFrontseater(), knowledge_database=KnowledgeDatabase(),
                       mission_graph=dict(_EMPTY_GRAPH), platform_id=platform_id,
                       privilege_level=privilege_level, sync_interval=sync_interval)


class TestClockHandshake(unittest.TestCase):
    def test_sync_with_records_a_peer_offset_on_both_sides(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.sync_with(ugv2)

        # No simulated latency yet, so each side's offset to the other should be
        # ~0 (same wall-clock instant), but the entry must exist (not just default).
        self.assertIn("ugv2", ugv1.clock._peer_offsets)
        self.assertIn("ugv1", ugv2.clock._peer_offsets)


class TestKnowledgeSync(unittest.TestCase):
    def test_pulls_a_peer_only_key_bidirectionally(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.knowledge_database.declare("ugv1_only", float, 1.0, timestamp=100.0)
        ugv2.knowledge_database.declare("ugv2_only", int, 5, timestamp=100.0)

        ugv1.sync_with(ugv2)

        self.assertEqual(ugv2.knowledge_database.get("ugv1_only"), 1.0)
        self.assertEqual(ugv1.knowledge_database.get("ugv2_only"), 5)

    def test_newer_value_wins_on_both_sides(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.knowledge_database.declare("battery", float, 0.9, timestamp=100.0)
        ugv2.knowledge_database.declare("battery", float, 0.5, timestamp=200.0)

        ugv1.sync_with(ugv2)

        self.assertEqual(ugv1.knowledge_database.get("battery"), 0.5)
        self.assertEqual(ugv2.knowledge_database.get("battery"), 0.5)

    def test_older_incoming_value_does_not_overwrite_a_fresher_local_one(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.knowledge_database.declare("battery", float, 0.9, timestamp=200.0)
        ugv2.knowledge_database.declare("battery", float, 0.5, timestamp=100.0)

        ugv1.sync_with(ugv2)

        self.assertEqual(ugv1.knowledge_database.get("battery"), 0.9)
        self.assertEqual(ugv2.knowledge_database.get("battery"), 0.9)


class TestMissionSync(unittest.TestCase):
    def test_a_platforms_own_mission_graph_is_gossiped_to_a_peer(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        graph = {"knowledge": {}, "nodes": {"n1": {"primitives": {}}}, "edges": {}, "start": "n1"}
        ugv1.write_mission(graph, writer_platform_id="ugv1")

        ugv1.sync_with(ugv2)

        self.assertIs(ugv2.mission_database.get("ugv1"), graph)

    def test_mission_sync_bypasses_the_privilege_gate(self):
        # ugv2 has lower privilege than ugv1 (higher number = lower privilege), so
        # ugv2 could never call ugv1.write_mission() itself -- but a sync carrying
        # ugv2's own already-published graph must still land, since the gate was
        # already satisfied at ugv2's own originating publish() call.
        ugv1 = _make_backseater("ugv1", privilege_level=0)
        ugv2 = _make_backseater("ugv2", privilege_level=5)
        graph = {"knowledge": {}, "nodes": {"n1": {"primitives": {}}}, "edges": {}, "start": "n1"}
        ugv2.write_mission(graph, writer_platform_id="ugv2")

        ugv1.sync_with(ugv2)

        self.assertIs(ugv1.mission_database.get("ugv2"), graph)


class TestPlatformSync(unittest.TestCase):
    def test_platform_records_are_gossiped_bidirectionally(self):
        ugv1 = _make_backseater("ugv1", privilege_level=2)
        ugv2 = _make_backseater("ugv2", privilege_level=3)

        ugv1.sync_with(ugv2)

        self.assertEqual(ugv1.platform_database.get("ugv2").privilege_level, 3)
        self.assertEqual(ugv2.platform_database.get("ugv1").privilege_level, 2)

    def test_a_self_record_is_reconciled_the_same_as_any_other(self):
        # ugv2 holds a stale copy of ugv1's own record (as if echoed back from an
        # earlier sync); ugv1 has since self-published a fresher one. Last-write-wins
        # naturally keeps ugv1's own fresher record with no self-record special-casing.
        ugv1 = _make_backseater("ugv1", privilege_level=1)
        ugv2 = _make_backseater("ugv2", privilege_level=1)
        ugv2.platform_database.declare("ugv1", PlatformRecord(privilege_level=1, status=PlatformStatus("stale")),
                                        timestamp=100.0, origin_platform_id="ugv1")
        ugv1.platform_database.set("ugv1", PlatformRecord(privilege_level=1, status=PlatformStatus("fresh")),
                                    timestamp=200.0, origin_platform_id="ugv1")

        ugv1.sync_with(ugv2)

        self.assertEqual(ugv1.platform_database.get("ugv1").status, PlatformStatus("fresh"))
        self.assertEqual(ugv2.platform_database.get("ugv1").status, PlatformStatus("fresh"))


class TestSyncIsSymmetricAndIdempotent(unittest.TestCase):
    def test_both_sides_converge_to_the_same_state(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.knowledge_database.declare("battery", float, 0.9, timestamp=100.0)
        ugv2.knowledge_database.declare("battery", float, 0.5, timestamp=200.0)

        ugv1.sync_with(ugv2)

        # Values converge exactly; raw timestamps need not match exactly, since each
        # side converts an incoming fact into its own local clock frame, which can
        # differ from the peer's frame by a (tiny) per-peer offset.
        self.assertEqual(ugv1.knowledge_database.get("battery"), ugv2.knowledge_database.get("battery"))
        self.assertAlmostEqual(ugv1.knowledge_database.timestamp_of("battery"),
                                ugv2.knowledge_database.timestamp_of("battery"), places=3)

    def test_a_second_consecutive_sync_skips_the_handshake_via_the_checksum_short_circuit(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.sync_with(ugv2)

        # Corrupt the recorded peer offset directly; if the checksum short-circuit
        # correctly skips re-handshaking (nothing changed since the last sync), this
        # sentinel value survives a second sync_with() call untouched.
        ugv1.clock.set_peer_offset("ugv2", -12345.0)
        ugv1.sync_with(ugv2)

        self.assertEqual(ugv1.clock.peer_offset("ugv2"), -12345.0)

    def test_a_change_after_the_first_sync_is_still_picked_up_by_a_later_sync(self):
        ugv1 = _make_backseater("ugv1")
        ugv2 = _make_backseater("ugv2")
        ugv1.sync_with(ugv2)

        ugv2.knowledge_database.declare("new_key", int, 7, timestamp=ugv2.clock.now())
        ugv1.clock.set_peer_offset("ugv2", -12345.0)   # would prove a real re-handshake happened
        ugv1.sync_with(ugv2)

        self.assertEqual(ugv1.knowledge_database.get("new_key"), 7)
        self.assertNotEqual(ugv1.clock.peer_offset("ugv2"), -12345.0)


class TestSyncWithStalePeers(unittest.TestCase):
    def test_a_never_synced_peer_is_synced_immediately(self):
        ugv1 = _make_backseater("ugv1", sync_interval=100.0)
        ugv2 = _make_backseater("ugv2", sync_interval=100.0)
        ugv2.knowledge_database.declare("ugv2_only", int, 5, timestamp=100.0)

        ugv1.sync_with_stale_peers([ugv2])

        self.assertEqual(ugv1.knowledge_database.get("ugv2_only"), 5)

    def test_a_recently_synced_peer_within_the_interval_is_skipped(self):
        ugv1 = _make_backseater("ugv1", sync_interval=100.0)
        ugv2 = _make_backseater("ugv2", sync_interval=100.0)
        ugv1.sync_with_stale_peers([ugv2])

        ugv2.knowledge_database.declare("new_key", int, 7, timestamp=ugv2.clock.now())
        ugv1.sync_with_stale_peers([ugv2])

        self.assertNotIn("new_key", ugv1.knowledge_database.all())

    def test_a_peer_past_the_interval_is_synced_again(self):
        ugv1 = _make_backseater("ugv1", sync_interval=100.0)
        ugv2 = _make_backseater("ugv2", sync_interval=100.0)
        ugv1.sync_with_stale_peers([ugv2])

        ugv2.knowledge_database.declare("new_key", int, 7, timestamp=ugv2.clock.now())
        ugv1._last_sync_time["ugv2"] = ugv1.clock.now() - 1000.0
        ugv1.sync_with_stale_peers([ugv2])

        self.assertEqual(ugv1.knowledge_database.get("new_key"), 7)


if __name__ == "__main__":
    unittest.main()