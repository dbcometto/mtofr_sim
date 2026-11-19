"""Tests for Backseater.query()/publish()/declare_knowledge_key(): the generalized
capability-facing data access methods, spanning all three of a Backseater's databases."""
import unittest

from mtofr.database import KnowledgeDatabase, PlatformRecord
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater
from mtofr.platform.backseater import Backseater


def _make_backseater(test_case: unittest.TestCase, platform_id: str = "ugv1", privilege_level: int = 1) -> Backseater:
    """Build a Backseater over a real BicycleFrontseater, registering the Frontseater's shutdown."""
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    test_case.addCleanup(frontseater.shutdown)
    return Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                       platform_id=platform_id, privilege_level=privilege_level)


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}


class TestFrontseaterBackseaterCascade(unittest.TestCase):
    def test_backseater_sets_itself_on_its_frontseater(self):
        """Constructing a Backseater sets frontseater.backseater to it."""
        backseater = _make_backseater(self)
        self.assertIs(backseater.frontseater.backseater, backseater)


class TestQueryKnowledge(unittest.TestCase):
    def test_query_returns_a_declared_knowledge_value(self):
        """query("knowledge", key) returns the declared value."""
        backseater = _make_backseater(self)
        backseater.knowledge_database.declare("battery", float, 0.8)
        self.assertEqual(backseater.query("knowledge", "battery"), 0.8)

    def test_query_unknown_database_raises(self):
        """query() on an unknown database name raises ValueError."""
        backseater = _make_backseater(self)
        with self.assertRaises(ValueError):
            backseater.query("bogus", "battery")


class TestPublishKnowledge(unittest.TestCase):
    def test_publish_writes_a_declared_knowledge_key(self):
        """publish("knowledge", ...) updates a declared key's value."""
        backseater = _make_backseater(self)
        backseater.knowledge_database.declare("battery", float, 0.8)
        backseater.publish("knowledge", "battery", 0.5)
        self.assertEqual(backseater.knowledge_database.get("battery"), 0.5)

    def test_publish_rejects_an_undeclared_knowledge_key(self):
        """publish("knowledge", ...) to an undeclared key raises ValueError."""
        backseater = _make_backseater(self)
        with self.assertRaises(ValueError):
            backseater.publish("knowledge", "battery", 0.5)

    def test_publish_rejects_a_mistyped_knowledge_value(self):
        """publish("knowledge", ...) with a value of the wrong type raises ValueError."""
        backseater = _make_backseater(self)
        backseater.knowledge_database.declare("battery", float, 0.8)
        with self.assertRaises(ValueError):
            backseater.publish("knowledge", "battery", "not-a-float")


class TestDeclareKnowledgeKey(unittest.TestCase):
    def test_declares_a_brand_new_knowledge_key(self):
        """declare_knowledge_key() makes a new key queryable with its initial value."""
        backseater = _make_backseater(self)
        backseater.declare_knowledge_key("target_found", bool, False)
        self.assertEqual(backseater.query("knowledge", "target_found"), False)

    def test_declared_key_records_this_platform_as_origin(self):
        """A key declared via declare_knowledge_key() records this platform as its origin."""
        backseater = _make_backseater(self)
        backseater.declare_knowledge_key("target_found", bool, False)
        self.assertEqual(backseater.knowledge_database.origin_of("target_found"), "ugv1")


class TestQueryPublishPlatform(unittest.TestCase):
    def test_query_returns_a_declared_platform_record(self):
        """query("platform", own_id) returns the record seeded at construction."""
        backseater = _make_backseater(self)
        self.assertEqual(backseater.query("platform", "ugv1").privilege_level, 1)

    def test_publish_updates_an_already_declared_platform_record(self):
        """publish("platform", ...) accepts a PlatformRecord for an existing entry."""
        backseater = _make_backseater(self)
        backseater.publish("platform", "ugv1", PlatformRecord(privilege_level=1))
        self.assertEqual(backseater.query("platform", "ugv1").privilege_level, 1)

    def test_publish_rejects_a_mistyped_platform_value(self):
        """publish("platform", ...) with a non-PlatformRecord value raises ValueError."""
        backseater = _make_backseater(self)
        with self.assertRaises(ValueError):
            backseater.publish("platform", "ugv1", "not-a-record")


class TestQueryPublishMission(unittest.TestCase):
    def test_publish_mission_self_write_lands_via_write_mission(self):
        """publish("mission", own_id, graph) stores the graph in this platform's Mission entry."""
        backseater = _make_backseater(self)
        backseater.publish("mission", "ugv1", _EMPTY_GRAPH)
        self.assertEqual(backseater.query("mission", "ugv1"), _EMPTY_GRAPH)

    def test_publish_mission_still_goes_through_the_privilege_gate(self):
        """publish("mission", ...) routes through write_mission, so a structurally bad graph is rejected."""
        # publish("mission", ...) is only ever a self-write (key is ignored, target is
        # always this platform's own entry via write_mission), so the privilege gate
        # never actually blocks it -- this asserts it really does route through
        # write_mission rather than bypassing it, by checking the structural-verify gate
        # (which write_mission also runs) rejects a bad graph the same way.
        from mtofr.mission.validation import MissionStructuralError
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