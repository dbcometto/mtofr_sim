"""Tests for Memory and MemoryEntry self-description."""
import unittest

from mtofr.memory.memory import Memory, Location, MemoryEntry


class TestMemory(unittest.TestCase):
    def test_add_and_get(self):
        memory = Memory()
        memory.add("loc_a", Location(1.0, 2.0))
        entry = memory.get("loc_a")
        self.assertEqual((entry.x, entry.y), (1.0, 2.0))

    def test_all_of_type(self):
        memory = Memory()
        memory.add("loc_a", Location(1.0, 2.0))
        memory.add("loc_b", Location(3.0, 4.0))
        self.assertEqual(set(memory.all_of_type(Location)), {"loc_a", "loc_b"})


class TestLocationDescribe(unittest.TestCase):
    def test_location_is_a_memory_entry(self):
        self.assertTrue(issubclass(Location, MemoryEntry))

    def test_describe_is_plaintext(self):
        description = Location.describe()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 0)

    def test_custom_memory_entry_must_implement_describe(self):
        with self.assertRaises(TypeError):
            class IncompleteEntry(MemoryEntry):
                pass
            IncompleteEntry()


if __name__ == "__main__":
    unittest.main()
