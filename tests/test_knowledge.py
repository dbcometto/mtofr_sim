"""Tests for Knowledge and KnowledgeEntry self-description."""
import unittest

from mtofr.knowledge.knowledge import Knowledge, Location, KnowledgeEntry


class TestKnowledge(unittest.TestCase):
    def test_add_and_get(self):
        knowledge = Knowledge()
        knowledge.add("loc_a", Location(1.0, 2.0))
        entry = knowledge.get("loc_a")
        self.assertEqual((entry.x, entry.y), (1.0, 2.0))

    def test_all_of_type(self):
        knowledge = Knowledge()
        knowledge.add("loc_a", Location(1.0, 2.0))
        knowledge.add("loc_b", Location(3.0, 4.0))
        self.assertEqual(set(knowledge.all_of_type(Location)), {"loc_a", "loc_b"})

    def test_all_returns_every_entry_regardless_of_type(self):
        knowledge = Knowledge()
        knowledge.add("loc_a", Location(1.0, 2.0))
        entries = knowledge.all()
        self.assertEqual(set(entries), {"loc_a"})
        self.assertIs(entries["loc_a"], knowledge.get("loc_a"))

    def test_all_returns_a_copy_not_the_live_store(self):
        knowledge = Knowledge()
        knowledge.add("loc_a", Location(1.0, 2.0))
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
