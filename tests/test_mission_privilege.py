"""Tests for Backseater.write_mission(): the single gated write point for a
platform's Mission database entry. Covers the privilege check (skipped on self-write,
otherwise requiring a strictly higher-privilege writer, and rejecting an unknown writer)
and the structural-verify gate; type-check rejection is mainly covered by
MissionDatabase's own tests in test_database.py."""
import unittest

from mtofr.database import KnowledgeDatabase, PlatformRecord
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater
from mtofr.mission.validation import MissionStructuralError
from mtofr.platform.backseater import Backseater


def _make_backseater(test_case: unittest.TestCase, platform_id: str, privilege_level: int) -> Backseater:
    """Build a Backseater over a real BicycleFrontseater, registering the Frontseater's shutdown."""
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    test_case.addCleanup(frontseater.shutdown)
    return Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                       platform_id=platform_id, privilege_level=privilege_level)


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}


class TestWriteMissionSelfWrite(unittest.TestCase):
    def test_self_write_bypasses_the_privilege_check_entirely(self):
        """A platform may always write its own Mission entry, whatever its privilege level."""
        # ugv1 has no knowledge of any other platform's privilege, but writing its own
        # entry must still succeed since the privilege check is skipped for self-writes.
        backseater = _make_backseater(self, "ugv1", privilege_level=5)
        backseater.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv1")
        self.assertEqual(backseater.mission_database.get("ugv1"), _EMPTY_GRAPH)


class TestWriteMissionPrivilegeCheck(unittest.TestCase):
    def test_a_strictly_higher_privilege_writer_may_write(self):
        """A strictly higher-privilege writer's graph is stored, with the writer as its origin."""
        target = _make_backseater(self, "ugv1", privilege_level=2)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))

        target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

        self.assertEqual(target.mission_database.get("ugv1"), _EMPTY_GRAPH)
        self.assertEqual(target.mission_database.origin_of("ugv1"), "ugv2")

    def test_an_equal_privilege_writer_is_rejected(self):
        """A writer at the same privilege level gets PermissionError."""
        target = _make_backseater(self, "ugv1", privilege_level=1)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))

        with self.assertRaises(PermissionError):
            target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

    def test_a_lower_privilege_writer_is_rejected(self):
        """A lower-privilege writer gets PermissionError."""
        target = _make_backseater(self, "ugv1", privilege_level=1)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=2))

        with self.assertRaises(PermissionError):
            target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

    def test_an_unknown_writer_is_rejected(self):
        """A writer absent from the target's Platform database gets PermissionError."""
        target = _make_backseater(self, "ugv1", privilege_level=5)

        with self.assertRaises(PermissionError):
            target.write_mission(_EMPTY_GRAPH, writer_platform_id="ugv2")

    def test_rejected_write_does_not_change_the_stored_mission_graph(self):
        """A write rejected for privilege leaves the stored Mission entry unchanged."""
        target = _make_backseater(self, "ugv1", privilege_level=1)
        target.platform_database.declare("ugv2", PlatformRecord(privilege_level=1))
        original_graph = target.mission_database.all().get("ugv1")

        with self.assertRaises(PermissionError):
            target.write_mission({"knowledge": {}, "nodes": {}, "edges": {}, "start": "n1"},
                                 writer_platform_id="ugv2")

        self.assertEqual(target.mission_database.all().get("ugv1"), original_graph)


class TestWriteMissionStructuralVerify(unittest.TestCase):
    def test_rejects_a_graph_referencing_an_undeclared_knowledge_key(self):
        """A graph whose edge condition uses an undeclared key raises MissionStructuralError."""
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
        """A graph whose condition keys are all declared is stored."""
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
        """A non-dict mission graph raises ValueError."""
        target = _make_backseater(self, "ugv1", privilege_level=1)
        with self.assertRaises(ValueError):
            target.write_mission("not a dict", writer_platform_id="ugv1")


if __name__ == "__main__":
    unittest.main()