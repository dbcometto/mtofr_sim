"""Tests for Backseater.write_mission(): the single gated write point for a
platform's Mission database entry (increment 2 of the peer-to-peer mesh redesign's
build order step 3). Covers the privilege check (skipped on self-write, otherwise
requiring a strictly higher-privilege writer, and rejecting an unknown writer) and the
structural-verify gate; type-check rejection is already covered by MissionDatabase's
own tests in test_database.py."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.database import KnowledgeDatabase, MissionStructuralError, PlatformRecord
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


def _make_backseater(test_case: unittest.TestCase, platform_id: str, privilege_level: int) -> Backseater:
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    test_case.addCleanup(frontseater.shutdown)
    return Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                       platform_id=platform_id, privilege_level=privilege_level)


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}


class TestWriteMissionSelfWrite(unittest.TestCase):
    def test_self_write_bypasses_the_privilege_check_entirely(self):
        # ugv1 has no knowledge of any other platform's privilege, but writing its own
        # entry must still succeed since the privilege check is skipped for self-writes.
        backseater = _make_backseater(self, "ugv1", privilege_level=5)
        backseater.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv1")
        self.assertEqual(backseater.mission_database.get("ugv1"), _EMPTY_GRAPH)


class TestWriteMissionPrivilegeCheck(unittest.TestCase):
    def test_a_strictly_higher_privilege_writer_may_write(self):
        target = _make_backseater(self, "ugv1", privilege_level=2)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))

        target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

        self.assertEqual(target.mission_database.get("ugv1"), _EMPTY_GRAPH)
        self.assertEqual(target.mission_database.origin_of("ugv1"), "ugv2")

    def test_an_equal_privilege_writer_is_rejected(self):
        target = _make_backseater(self, "ugv1", privilege_level=1)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))

        with self.assertRaises(PermissionError):
            target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

    def test_a_lower_privilege_writer_is_rejected(self):
        target = _make_backseater(self, "ugv1", privilege_level=1)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=2))

        with self.assertRaises(PermissionError):
            target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

    def test_an_unknown_writer_is_rejected(self):
        target = _make_backseater(self, "ugv1", privilege_level=5)

        with self.assertRaises(PermissionError):
            target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

    def test_rejected_write_does_not_change_the_stored_mission_graph(self):
        target = _make_backseater(self, "ugv1", privilege_level=1)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))
        original_graph = target.mission_database.all().get("ugv1")

        with self.assertRaises(PermissionError):
            target.write_mission({"knowledge": {}, "nodes": {}, "edges": {}, "start": "n1"},
                                 writer_platform_id="ugv2")

        self.assertEqual(target.mission_database.all().get("ugv1"), original_graph)


class TestWriteMissionStructuralVerify(unittest.TestCase):
    def test_rejects_a_graph_referencing_an_undeclared_knowledge_key(self):
        target = _make_backseater(self, "ugv1", privilege_level=1)
        bad_graph = {
            "knowledge": {},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }

        with self.assertRaises(MissionStructuralError):
            target.write_mission(bad_graph, writer_platform_id="ugv1")

    def test_accepts_a_graph_whose_referenced_keys_are_all_declared(self):
        target = _make_backseater(self, "ugv1", privilege_level=1)
        good_graph = {
            "knowledge": {"ugv1/arrived": {"type": bool, "value": False}},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }

        target.write_mission(good_graph, writer_platform_id="ugv1")

        self.assertEqual(target.mission_database.get("ugv1"), good_graph)


class TestWriteMissionTypeCheck(unittest.TestCase):
    def test_rejects_a_non_dict_mission_graph(self):
        target = _make_backseater(self, "ugv1", privilege_level=1)
        with self.assertRaises(ValueError):
            target.write_mission("not a dict", writer_platform_id="ugv1")


if __name__ == "__main__":
    unittest.main()