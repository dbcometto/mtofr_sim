"""Tests for MissionDatabase and PlatformDatabase: the platform_id-keyed siblings to
KnowledgeDatabase, each locked to a single fixed value type, with timestamp and
origin_platform_id tracking per entry. Also covers verify_mission_structure(), the
structural-verify gate a Mission write must pass."""
import time
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, CapabilityRegistry
from mtofr.database import (
    KnowledgeDatabase,
    MissionDatabase,
    MissionStructuralError,
    verify_mission_structure,
    PlatformDatabase,
    PlatformRecord,
    PlatformStatus,
)
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class TestMissionDatabase(unittest.TestCase):
    def test_declare_and_get_returns_the_seeded_value(self):
        database = MissionDatabase()
        graph = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        database.declare("ugv1", graph)
        self.assertIs(database.get("ugv1"), graph)

    def test_declare_rejects_wrong_type(self):
        database = MissionDatabase()
        with self.assertRaises(ValueError):
            database.declare("ugv1", "not a dict")

    def test_set_updates_the_value(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        database.set("ugv1", {"start": "n2"})
        self.assertEqual(database.get("ugv1"), {"start": "n2"})

    def test_set_rejects_wrong_type(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        with self.assertRaises(ValueError):
            database.set("ugv1", "not a dict")

    def test_set_rejects_undeclared_platform_id(self):
        database = MissionDatabase()
        with self.assertRaises(ValueError):
            database.set("ugv1", {"start": "n1"})

    def test_all_returns_every_entry(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        database.declare("ugv2", {"start": "n2"})
        self.assertEqual(set(database.all()), {"ugv1", "ugv2"})

    def test_all_returns_a_copy_not_the_live_store(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        entries = database.all()
        entries["ugv2"] = {"start": "n2"}
        self.assertNotIn("ugv2", database.all())


class TestPlatformDatabase(unittest.TestCase):
    def test_declare_and_get_returns_the_seeded_record(self):
        database = PlatformDatabase()
        record = PlatformRecord(privilege_level=1)
        database.declare("ugv1", record)
        self.assertIs(database.get("ugv1"), record)

    def test_declare_rejects_wrong_type(self):
        database = PlatformDatabase()
        with self.assertRaises(ValueError):
            database.declare("ugv1", "not a record")

    def test_platform_record_defaults_status_to_idle_and_capabilities_to_none(self):
        record = PlatformRecord(privilege_level=1)
        self.assertEqual(record.status, PlatformStatus("idle"))
        self.assertIsNone(record.capabilities)

    def test_platform_record_holds_a_status_and_capability_registry(self):
        registry = CapabilityRegistry([Capability(ipl_type="move_to", description="moves")])
        status = PlatformStatus(status="ok", message="")
        record = PlatformRecord(privilege_level=2, status=status, capabilities=registry)
        self.assertEqual(record.privilege_level, 2)
        self.assertIs(record.status, status)
        self.assertIs(record.capabilities, registry)

    def test_platform_status_defaults_message_to_empty_string(self):
        status = PlatformStatus(status="ok")
        self.assertEqual(status.message, "")


class TestVerifyMissionStructure(unittest.TestCase):
    def test_passes_when_every_referenced_key_is_declared(self):
        mission_graph = {
            "knowledge": {"ugv1/arrived": {"type": bool, "value": False}},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }
        verify_mission_structure(mission_graph)   # does not raise

    def test_raises_on_a_reference_to_an_undeclared_key(self):
        mission_graph = {
            "knowledge": {},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }
        with self.assertRaises(MissionStructuralError):
            verify_mission_structure(mission_graph)

    def test_passes_for_a_graph_with_no_edges(self):
        mission_graph = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        verify_mission_structure(mission_graph)   # does not raise

    def test_mission_structural_error_is_a_value_error(self):
        self.assertTrue(issubclass(MissionStructuralError, ValueError))


class TestTimestampAndOriginTracking(unittest.TestCase):
    """Exercised once against MissionDatabase, since the behavior is identical
    across all three databases (shared PlatformKeyedDatabase base)."""

    def test_declare_defaults_timestamp_to_wall_clock_time(self):
        database = MissionDatabase()
        before = time.time()
        database.declare("ugv1", {"start": "n1"})
        after = time.time()
        self.assertTrue(before <= database.timestamp_of("ugv1") <= after)

    def test_declare_accepts_an_explicit_timestamp(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, timestamp=123.0)
        self.assertEqual(database.timestamp_of("ugv1"), 123.0)

    def test_set_updates_the_timestamp(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, timestamp=1.0)
        database.set("ugv1", {"start": "n2"}, timestamp=2.0)
        self.assertEqual(database.timestamp_of("ugv1"), 2.0)

    def test_timestamp_of_returns_none_for_undeclared_platform_id(self):
        database = MissionDatabase()
        self.assertIsNone(database.timestamp_of("ugv1"))

    def test_declare_defaults_origin_to_none(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        self.assertIsNone(database.origin_of("ugv1"))

    def test_declare_accepts_an_explicit_origin(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, origin_platform_id="ugv1")
        self.assertEqual(database.origin_of("ugv1"), "ugv1")

    def test_set_updates_the_origin(self):
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, origin_platform_id="ugv1")
        database.set("ugv1", {"start": "n2"}, origin_platform_id="ugv2")
        self.assertEqual(database.origin_of("ugv1"), "ugv2")

    def test_origin_of_returns_none_for_undeclared_platform_id(self):
        database = MissionDatabase()
        self.assertIsNone(database.origin_of("ugv1"))


class TestBackseaterOwnsTheFourDatabases(unittest.TestCase):
    def test_backseater_holds_mission_and_platform_databases(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

        self.assertIsInstance(backseater.mission_database, MissionDatabase)
        self.assertIsInstance(backseater.platform_database, PlatformDatabase)
        self.assertEqual(backseater.mission_database.all(), {})

    def test_backseater_self_declares_its_own_platform_record_at_construction(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 platform_id="ugv1", privilege_level=3)

        record = backseater.platform_database.get("ugv1")
        self.assertEqual(record.privilege_level, 3)
        self.assertEqual(record.status, PlatformStatus("idle"))

    def test_backseater_defaults_privilege_level_to_one(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

        self.assertEqual(backseater.privilege_level, 1)
        self.assertEqual(backseater.platform_database.get("ugv1").privilege_level, 1)

    def test_backseater_without_a_platform_id_declares_no_platform_record(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase())

        self.assertEqual(backseater.platform_database.all(), {})


if __name__ == "__main__":
    unittest.main()