"""Tests for MissionDatabase and PlatformDatabase: the platform_id-keyed siblings to
KnowledgeDatabase, each locked to a single fixed value type, with timestamp and
origin_platform_id tracking per entry. The structural gate a Mission write must pass is
covered in test_mission_validation.py."""
import time
import unittest

from mtofr.core.capability import Capability, CapabilityRegistry
from mtofr.database import (
    KnowledgeDatabase,
    MissionDatabase,
    PlatformDatabase,
    PlatformRecord,
    PlatformStatus,
)
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater
from mtofr.platform.backseater import Backseater


class TestMissionDatabase(unittest.TestCase):
    def test_declare_and_get_returns_the_seeded_value(self):
        """get() returns the exact graph object passed to declare()."""
        database = MissionDatabase()
        graph = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        database.declare("ugv1", graph)
        self.assertIs(database.get("ugv1"), graph)

    def test_declare_rejects_wrong_type(self):
        """declare() raises ValueError for a value that isn't a mission-graph dict."""
        database = MissionDatabase()
        with self.assertRaises(ValueError):
            database.declare("ugv1", "not a dict")

    def test_set_updates_the_value(self):
        """set() replaces the stored graph for a declared platform_id."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        database.set("ugv1", {"start": "n2"})
        self.assertEqual(database.get("ugv1"), {"start": "n2"})

    def test_set_rejects_wrong_type(self):
        """set() raises ValueError for a value that isn't a mission-graph dict."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        with self.assertRaises(ValueError):
            database.set("ugv1", "not a dict")

    def test_set_rejects_undeclared_platform_id(self):
        """set() raises ValueError for a platform_id that was never declared."""
        database = MissionDatabase()
        with self.assertRaises(ValueError):
            database.set("ugv1", {"start": "n1"})

    def test_all_returns_every_entry(self):
        """all() includes every declared platform_id."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        database.declare("ugv2", {"start": "n2"})
        self.assertEqual(set(database.all()), {"ugv1", "ugv2"})

    def test_all_returns_a_copy_not_the_live_store(self):
        """Mutating the dict from all() leaves the database unchanged."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        entries = database.all()
        entries["ugv2"] = {"start": "n2"}
        self.assertNotIn("ugv2", database.all())


class TestPlatformDatabase(unittest.TestCase):
    def test_declare_and_get_returns_the_seeded_record(self):
        """get() returns the exact PlatformRecord passed to declare()."""
        database = PlatformDatabase()
        record = PlatformRecord(privilege_level=1)
        database.declare("ugv1", record)
        self.assertIs(database.get("ugv1"), record)

    def test_declare_rejects_wrong_type(self):
        """declare() raises ValueError for a value that isn't a PlatformRecord."""
        database = PlatformDatabase()
        with self.assertRaises(ValueError):
            database.declare("ugv1", "not a record")

    def test_platform_record_defaults_status_to_idle_and_capabilities_to_none(self):
        """A PlatformRecord built with only a privilege level is idle with no capabilities."""
        record = PlatformRecord(privilege_level=1)
        self.assertEqual(record.status, PlatformStatus("idle"))
        self.assertIsNone(record.capabilities)

    def test_platform_record_holds_a_status_and_capability_registry(self):
        """A PlatformRecord keeps the privilege level, status, and registry it was built with."""
        registry = CapabilityRegistry([Capability(ipl_type="move_to", description="moves")])
        status = PlatformStatus(status="ok", message="")
        record = PlatformRecord(privilege_level=2, status=status, capabilities=registry)
        self.assertEqual(record.privilege_level, 2)
        self.assertIs(record.status, status)
        self.assertIs(record.capabilities, registry)

    def test_platform_status_defaults_message_to_empty_string(self):
        """A PlatformStatus built without a message has an empty one."""
        status = PlatformStatus(status="ok")
        self.assertEqual(status.message, "")


class TestTimestampAndOriginTracking(unittest.TestCase):
    """Exercised once against MissionDatabase, since the behavior is identical
    across all three databases (shared PlatformKeyedDatabase base)."""

    def test_declare_defaults_timestamp_to_wall_clock_time(self):
        """declare() without a timestamp stamps the entry with the current wall-clock time."""
        database = MissionDatabase()
        before = time.time()
        database.declare("ugv1", {"start": "n1"})
        after = time.time()
        self.assertTrue(before <= database.timestamp_of("ugv1") <= after)

    def test_declare_accepts_an_explicit_timestamp(self):
        """declare() stores an explicitly given timestamp."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, timestamp=123.0)
        self.assertEqual(database.timestamp_of("ugv1"), 123.0)

    def test_set_updates_the_timestamp(self):
        """set() overwrites the entry's timestamp with the new one."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, timestamp=1.0)
        database.set("ugv1", {"start": "n2"}, timestamp=2.0)
        self.assertEqual(database.timestamp_of("ugv1"), 2.0)

    def test_timestamp_of_returns_none_for_undeclared_platform_id(self):
        """timestamp_of() returns None for a platform_id that was never declared."""
        database = MissionDatabase()
        self.assertIsNone(database.timestamp_of("ugv1"))

    def test_declare_defaults_origin_to_none(self):
        """declare() without an origin leaves origin_of() as None."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"})
        self.assertIsNone(database.origin_of("ugv1"))

    def test_declare_accepts_an_explicit_origin(self):
        """declare() stores an explicitly given origin_platform_id."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, origin_platform_id="ugv1")
        self.assertEqual(database.origin_of("ugv1"), "ugv1")

    def test_set_updates_the_origin(self):
        """set() overwrites the entry's origin_platform_id with the new one."""
        database = MissionDatabase()
        database.declare("ugv1", {"start": "n1"}, origin_platform_id="ugv1")
        database.set("ugv1", {"start": "n2"}, origin_platform_id="ugv2")
        self.assertEqual(database.origin_of("ugv1"), "ugv2")

    def test_origin_of_returns_none_for_undeclared_platform_id(self):
        """origin_of() returns None for a platform_id that was never declared."""
        database = MissionDatabase()
        self.assertIsNone(database.origin_of("ugv1"))


class TestBackseaterOwnsTheThreeDatabases(unittest.TestCase):
    def test_backseater_holds_mission_and_platform_databases(self):
        """A new Backseater owns a MissionDatabase (empty) and a PlatformDatabase."""
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

        self.assertIsInstance(backseater.mission_database, MissionDatabase)
        self.assertIsInstance(backseater.platform_database, PlatformDatabase)
        self.assertEqual(backseater.mission_database.all(), {})

    def test_backseater_self_declares_its_own_platform_record_at_construction(self):
        """A Backseater seeds its own PlatformRecord with its privilege level and an idle status."""
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(),
                                 platform_id="ugv1", privilege_level=3)

        record = backseater.platform_database.get("ugv1")
        self.assertEqual(record.privilege_level, 3)
        self.assertEqual(record.status, PlatformStatus("idle"))

    def test_backseater_defaults_privilege_level_to_one(self):
        """Without an explicit privilege level, the Backseater and its own record both use 1."""
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

        self.assertEqual(backseater.privilege_level, 1)
        self.assertEqual(backseater.platform_database.get("ugv1").privilege_level, 1)

    def test_backseater_without_a_platform_id_declares_no_platform_record(self):
        """A Backseater with no platform_id leaves its PlatformDatabase empty."""
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase())

        self.assertEqual(backseater.platform_database.all(), {})


if __name__ == "__main__":
    unittest.main()
