"""Tests for KnowledgeDatabase (declare/set/get, type-locking, origin tracking) and
KnowledgeEntry self-description."""
import time
import unittest

from mtofr.database import KnowledgeDatabase, Location, KnowledgeEntry


class TestKnowledgeDatabase(unittest.TestCase):
    def test_declare_and_get_returns_the_seeded_value(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        entry = knowledge.get("loc_a")
        self.assertEqual((entry.x, entry.y), (1.0, 2.0))

    def test_declare_works_for_plain_types_too(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        self.assertEqual(knowledge.get("ugv1/arrived"), False)

    def test_set_updates_the_value(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        knowledge.set("ugv1/arrived", True)
        self.assertEqual(knowledge.get("ugv1/arrived"), True)

    def test_set_rejects_wrong_type(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        with self.assertRaises(ValueError):
            knowledge.set("ugv1/arrived", "not a bool")

    def test_set_rejects_undeclared_key(self):
        knowledge = KnowledgeDatabase()
        with self.assertRaises(ValueError):
            knowledge.set("never_declared", True)

    def test_type_of_returns_the_declared_type(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        self.assertIs(knowledge.type_of("loc_a"), Location)

    def test_type_of_returns_none_for_undeclared_key(self):
        knowledge = KnowledgeDatabase()
        self.assertIsNone(knowledge.type_of("never_declared"))

    def test_all_of_type(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        knowledge.declare("loc_b", Location, Location(3.0, 4.0))
        self.assertEqual(set(knowledge.all_of_type(Location)), {"loc_a", "loc_b"})

    def test_all_returns_every_entry_regardless_of_type(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        entries = knowledge.all()
        self.assertEqual(set(entries), {"loc_a"})
        self.assertIs(entries["loc_a"], knowledge.get("loc_a"))

    def test_all_returns_a_copy_not_the_live_store(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        entries = knowledge.all()
        entries["loc_b"] = Location(9.0, 9.0)
        self.assertNotIn("loc_b", knowledge.all())

    def test_declare_defaults_timestamp_to_wall_clock_time(self):
        knowledge = KnowledgeDatabase()
        before = time.time()
        knowledge.declare("ugv1/arrived", bool, False)
        after = time.time()
        self.assertTrue(before <= knowledge.timestamp_of("ugv1/arrived") <= after)

    def test_declare_accepts_an_explicit_timestamp(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False, timestamp=123.0)
        self.assertEqual(knowledge.timestamp_of("ugv1/arrived"), 123.0)

    def test_set_updates_the_timestamp(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False, timestamp=1.0)
        knowledge.set("ugv1/arrived", True, timestamp=2.0)
        self.assertEqual(knowledge.timestamp_of("ugv1/arrived"), 2.0)

    def test_set_defaults_timestamp_to_wall_clock_time_when_omitted(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False, timestamp=1.0)
        before = time.time()
        knowledge.set("ugv1/arrived", True)
        after = time.time()
        self.assertTrue(before <= knowledge.timestamp_of("ugv1/arrived") <= after)

    def test_timestamp_of_returns_none_for_undeclared_key(self):
        knowledge = KnowledgeDatabase()
        self.assertIsNone(knowledge.timestamp_of("never_declared"))

    def test_set_or_declare_behaves_like_set_for_a_declared_key(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        knowledge.set_or_declare("ugv1/arrived", True, timestamp=5.0)
        self.assertEqual(knowledge.get("ugv1/arrived"), True)
        self.assertEqual(knowledge.timestamp_of("ugv1/arrived"), 5.0)

    def test_set_or_declare_rejects_wrong_type_for_a_declared_key(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        with self.assertRaises(ValueError):
            knowledge.set_or_declare("ugv1/arrived", "not a bool")

    def test_set_or_declare_auto_declares_an_undeclared_key(self):
        knowledge = KnowledgeDatabase()
        knowledge.set_or_declare("ugv1/new_fact", True, timestamp=5.0)
        self.assertEqual(knowledge.get("ugv1/new_fact"), True)
        self.assertIs(knowledge.type_of("ugv1/new_fact"), bool)
        self.assertEqual(knowledge.timestamp_of("ugv1/new_fact"), 5.0)

    def test_declare_defaults_origin_to_none(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        self.assertIsNone(knowledge.origin_of("ugv1/arrived"))

    def test_declare_accepts_an_explicit_origin(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False, origin_platform_id="ugv1")
        self.assertEqual(knowledge.origin_of("ugv1/arrived"), "ugv1")

    def test_set_updates_the_origin(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False, origin_platform_id="ugv1")
        knowledge.set("ugv1/arrived", True, origin_platform_id="ugv2")
        self.assertEqual(knowledge.origin_of("ugv1/arrived"), "ugv2")

    def test_set_defaults_origin_to_none_when_omitted(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False, origin_platform_id="ugv1")
        knowledge.set("ugv1/arrived", True)
        self.assertIsNone(knowledge.origin_of("ugv1/arrived"))

    def test_origin_of_returns_none_for_undeclared_key(self):
        knowledge = KnowledgeDatabase()
        self.assertIsNone(knowledge.origin_of("never_declared"))

    def test_set_or_declare_preserves_origin_for_a_declared_key(self):
        knowledge = KnowledgeDatabase()
        knowledge.declare("ugv1/arrived", bool, False)
        knowledge.set_or_declare("ugv1/arrived", True, origin_platform_id="ugv2")
        self.assertEqual(knowledge.origin_of("ugv1/arrived"), "ugv2")

    def test_set_or_declare_sets_origin_when_auto_declaring(self):
        knowledge = KnowledgeDatabase()
        knowledge.set_or_declare("ugv1/new_fact", True, origin_platform_id="ugv1")
        self.assertEqual(knowledge.origin_of("ugv1/new_fact"), "ugv1")


class TestLocationDescribe(unittest.TestCase):
    def test_location_is_a_knowledge_entry(self):
        self.assertTrue(issubclass(Location, KnowledgeEntry))

    def test_describe_is_plaintext(self):
        description = Location.describe()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 0)

    def test_custom_knowledge_entry_must_implement_describe(self):
        with self.assertRaises(TypeError):
            class IncompleteEntry(KnowledgeEntry):
                pass
            IncompleteEntry()


if __name__ == "__main__":
    unittest.main()