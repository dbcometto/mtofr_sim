"""Tests for Backseater.query()/publish()/declare_knowledge_key() (increment 4 of the
peer-to-peer mesh redesign's build order step 3) — the generalized capability-facing
data access methods, spanning all three of a Backseater's databases."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.database import KnowledgeDatabase, PlatformRecord
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


def _make_backseater(test_case: unittest.TestCase, platform_id: str = "ugv1", privilege_level: int = 1) -> Backseater:
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    test_case.addCleanup(frontseater.shutdown)
    return Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                       platform_id=platform_id, privilege_level=privilege_level)


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}


class TestFrontseaterBackseaterCascade(unittest.TestCase):
    def test_backseater_sets_itself_on_its_frontseater(self):
        backseater = _make_backseater(self)
        self.assertIs(backseater.frontseater.backseater, backseater)


class TestQueryKnowledge(unittest.TestCase):
    def test_query_returns_a_declared_knowledge_value(self):
        backseater = _make_backseater(self)
        backseater.knowledge_database.declare("battery", float, 0.8)
        self.assertEqual(backseater.query("knowledge", "battery"), 0.8)

    def test_query_unknown_database_raises(self):
        backseater = _make_backseater(self)
        with self.assertRaises(ValueError):
            backseater.query("bogus", "battery")


class TestPublishKnowledge(unittest.TestCase):
    def test_publish_writes_a_declared_knowledge_key(self):
        backseater = _make_backseater(self)
        backseater.knowledge_database.declare("battery", float, 0.8)
        backseater.publish("knowledge", "battery", 0.5)
        self.assertEqual(backseater.knowledge_database.get("battery"), 0.5)

    def test_publish_rejects_an_undeclared_knowledge_key(self):
        backseater = _make_backseater(self)
        with self.assertRaises(ValueError):
            backseater.publish("knowledge", "battery", 0.5)

    def test_publish_rejects_a_mistyped_knowledge_value(self):
        backseater = _make_backseater(self)
        backseater.knowledge_database.declare("battery", float, 0.8)
        with self.assertRaises(ValueError):
            backseater.publish("knowledge", "battery", "not-a-float")


class TestDeclareKnowledgeKey(unittest.TestCase):
    def test_declares_a_brand_new_knowledge_key(self):
        backseater = _make_backseater(self)
        backseater.declare_knowledge_key("target_found", bool, False)
        self.assertEqual(backseater.query("knowledge", "target_found"), False)

    def test_declared_key_records_this_platform_as_origin(self):
        backseater = _make_backseater(self)
        backseater.declare_knowledge_key("target_found", bool, False)
        self.assertEqual(backseater.knowledge_database.origin_of("target_found"), "ugv1")


class TestQueryPublishPlatform(unittest.TestCase):
    def test_query_returns_a_declared_platform_record(self):
        backseater = _make_backseater(self)
        self.assertEqual(backseater.query("platform", "ugv1").privilege_level, 1)

    def test_publish_updates_an_already_declared_platform_record(self):
        backseater = _make_backseater(self)
        backseater.publish("platform", "ugv1", PlatformRecord(privilege_level=1))
        self.assertEqual(backseater.query("platform", "ugv1").privilege_level, 1)

    def test_publish_rejects_a_mistyped_platform_value(self):
        backseater = _make_backseater(self)
        with self.assertRaises(ValueError):
            backseater.publish("platform", "ugv1", "not-a-record")


class TestQueryPublishMission(unittest.TestCase):
    def test_publish_mission_self_write_lands_via_write_mission(self):
        backseater = _make_backseater(self)
        backseater.publish("mission", "ugv1", _EMPTY_GRAPH)
        self.assertEqual(backseater.query("mission", "ugv1"), _EMPTY_GRAPH)

    def test_publish_mission_still_goes_through_the_privilege_gate(self):
        # publish("mission", ...) is only ever a self-write (key is ignored, target is
        # always this platform's own entry via write_mission), so the privilege gate
        # never actually blocks it -- this asserts it really does route through
        # write_mission rather than bypassing it, by checking the structural-verify gate
        # (which write_mission also runs) rejects a bad graph the same way.
        from mtofr.database import MissionStructuralError
        backseater = _make_backseater(self)
        bad_graph = {
            "knowledge": {},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }
        with self.assertRaises(MissionStructuralError):
            backseater.publish("mission", "ugv1", bad_graph)


if __name__ == "__main__":
    unittest.main()