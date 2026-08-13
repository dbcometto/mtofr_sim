"""Tests for Knowledge (declare/set/get, type-locking) and KnowledgeEntry self-description."""
import unittest

from mtofr.knowledge.knowledge import Knowledge, Location, KnowledgeEntry


class TestKnowledge(unittest.TestCase):
    def test_declare_and_get_returns_the_seeded_value(self):
        knowledge = Knowledge()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        entry = knowledge.get("loc_a")
        self.assertEqual((entry.x, entry.y), (1.0, 2.0))

    def test_declare_works_for_plain_types_too(self):
        knowledge = Knowledge()
        knowledge.declare("ugv1/arrived", bool, False)
        self.assertEqual(knowledge.get("ugv1/arrived"), False)

    def test_set_updates_the_value(self):
        knowledge = Knowledge()
        knowledge.declare("ugv1/arrived", bool, False)
        knowledge.set("ugv1/arrived", True)
        self.assertEqual(knowledge.get("ugv1/arrived"), True)

    def test_set_rejects_wrong_type(self):
        knowledge = Knowledge()
        knowledge.declare("ugv1/arrived", bool, False)
        with self.assertRaises(ValueError):
            knowledge.set("ugv1/arrived", "not a bool")

    def test_set_rejects_undeclared_key(self):
        knowledge = Knowledge()
        with self.assertRaises(ValueError):
            knowledge.set("never_declared", True)

    def test_type_of_returns_the_declared_type(self):
        knowledge = Knowledge()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        self.assertIs(knowledge.type_of("loc_a"), Location)

    def test_type_of_returns_none_for_undeclared_key(self):
        knowledge = Knowledge()
        self.assertIsNone(knowledge.type_of("never_declared"))

    def test_all_of_type(self):
        knowledge = Knowledge()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        knowledge.declare("loc_b", Location, Location(3.0, 4.0))
        self.assertEqual(set(knowledge.all_of_type(Location)), {"loc_a", "loc_b"})

    def test_all_returns_every_entry_regardless_of_type(self):
        knowledge = Knowledge()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        entries = knowledge.all()
        self.assertEqual(set(entries), {"loc_a"})
        self.assertIs(entries["loc_a"], knowledge.get("loc_a"))

    def test_all_returns_a_copy_not_the_live_store(self):
        knowledge = Knowledge()
        knowledge.declare("loc_a", Location, Location(1.0, 2.0))
        entries = knowledge.all()
        entries["loc_b"] = Location(9.0, 9.0)
        self.assertNotIn("loc_b", knowledge.all())


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
