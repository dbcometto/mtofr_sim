"""Tests for Knowledge type auto-registration: every concrete KnowledgeEntry subclass joins
KNOWLEDGE_TYPES_BY_NAME (and its reverse) under its class name when it is defined."""
import unittest

from mtofr.database import KNOWLEDGE_TYPE_NAMES, KNOWLEDGE_TYPES_BY_NAME, KnowledgeEntry, Location, Pose
from mtofr.mission import serialization


class TestKnowledgeTypeRegistration(unittest.TestCase):
    def _forget(self, entry_type: type) -> None:
        """Removes `entry_type` from both registries, so a test-local type doesn't leak into other tests."""
        KNOWLEDGE_TYPES_BY_NAME.pop(entry_type.__name__, None)
        KNOWLEDGE_TYPE_NAMES.pop(entry_type, None)

    def test_built_in_types_and_scalars_are_registered(self):
        """The scalars and every built-in entry type are registered under their names."""
        for name, entry_type in {"bool": bool, "float": float, "int": int, "str": str,
                                 "Location": Location, "Pose": Pose}.items():
            self.assertIs(KNOWLEDGE_TYPES_BY_NAME[name], entry_type)
            self.assertEqual(KNOWLEDGE_TYPE_NAMES[entry_type], name)

    def test_serialization_shares_the_live_registry(self):
        """mission.serialization re-exports the same registry objects, not copies."""
        self.assertIs(serialization.KNOWLEDGE_TYPES_BY_NAME, KNOWLEDGE_TYPES_BY_NAME)
        self.assertIs(serialization.KNOWLEDGE_TYPE_NAMES, KNOWLEDGE_TYPE_NAMES)

    def test_a_new_subclass_registers_itself(self):
        """Defining a concrete KnowledgeEntry subclass registers it with no other step."""
        class Waypoint(KnowledgeEntry):
            """A test-local entry type."""
            def __init__(self, x: float):
                """A waypoint at x (m)."""
                self.x = x

            @classmethod
            def describe(cls) -> str:
                """Plaintext description."""
                return "Waypoint(x)"
        self.addCleanup(self._forget, Waypoint)
        self.assertIs(KNOWLEDGE_TYPES_BY_NAME["Waypoint"], Waypoint)
        self.assertEqual(KNOWLEDGE_TYPE_NAMES[Waypoint], "Waypoint")

    def test_an_abstract_subclass_is_not_registered(self):
        """A subclass that doesn't implement describe() is skipped."""
        class Unfinished(KnowledgeEntry):
            """Never implements describe()."""
        self.assertNotIn("Unfinished", KNOWLEDGE_TYPES_BY_NAME)

    def test_a_taken_name_raises(self):
        """A second, different class with an already-registered name raises ValueError."""
        with self.assertRaises(ValueError):
            class Location(KnowledgeEntry):   # deliberately collides with the built-in
                """Collides with the built-in Location."""
                @classmethod
                def describe(cls) -> str:
                    """Plaintext description."""
                    return "a second Location"


if __name__ == "__main__":
    unittest.main()
