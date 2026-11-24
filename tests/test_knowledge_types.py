"""Tests for Knowledge type auto-registration: every concrete KnowledgeEntry subclass joins
KNOWLEDGE_TYPES_BY_NAME (and its reverse) under its class name when it is defined."""
import unittest

from mtofr.database import KNOWLEDGE_TYPE_NAMES, KNOWLEDGE_TYPES_BY_NAME, KnowledgeEntry, Location, Pose, Trajectory
from mtofr.environments.ground_plane.platforms.interface.mission_editor.assistant_tools import as_knowledge_value
from mtofr.mission import serialization


class TestKnowledgeTypeRegistration(unittest.TestCase):
    def _forget(self, entry_type: type) -> None:
        """Removes `entry_type` from both registries, so a test-local type doesn't leak into other tests."""
        KNOWLEDGE_TYPES_BY_NAME.pop(entry_type.__name__, None)
        KNOWLEDGE_TYPE_NAMES.pop(entry_type, None)

    def test_built_in_types_and_scalars_are_registered(self):
        """The scalars and every built-in entry type are registered under their names."""
        for name, entry_type in {"bool": bool, "float": float, "int": int, "str": str,
                                 "Location": Location, "Pose": Pose, "Trajectory": Trajectory}.items():
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


class TestTrajectory(unittest.TestCase):
    def test_parses_waypoint_text_into_points(self):
        """JSON [x, y] pairs (ints or floats) become float (x, y) tuples, and the text is kept as given."""
        trajectory = Trajectory("[[0, 0], [10.5, -3]]")
        self.assertEqual(trajectory.points, ((0.0, 0.0), (10.5, -3.0)))
        self.assertEqual(trajectory.waypoints, "[[0, 0], [10.5, -3]]")

    def test_empty_text_and_an_empty_list_are_no_waypoints(self):
        """"", whitespace, and "[]" all give an empty trajectory."""
        for text in ("", "  ", "[]"):
            self.assertEqual(Trajectory(text).points, (), repr(text))

    def test_malformed_text_raises_value_error(self):
        """Bad JSON, a non-list, a non-pair, and a non-number (including a bool) each raise ValueError."""
        for text in ("[[0, 0", '{"x": 1}', "[[1, 2, 3]]", "[1, 2]", '[["a", 1]]', "[[true, 1]]"):
            with self.assertRaises(ValueError, msg=text):
                Trajectory(text)

    def test_default_knowledge_value_is_an_empty_trajectory(self):
        """The editors' neutral placeholder value parses (as no waypoints)."""
        self.assertEqual(serialization.default_knowledge_value(Trajectory).points, ())

    def test_the_web_form_field_dict_builds_a_trajectory(self):
        """A web form's field-text dict casts to a Trajectory, and bad text is a ValueError the editors report."""
        trajectory = as_knowledge_value(Trajectory, {"waypoints": "[[1, 2], [3, 4]]"})
        self.assertEqual(trajectory.points, ((1.0, 2.0), (3.0, 4.0)))
        with self.assertRaises(ValueError):
            as_knowledge_value(Trajectory, {"waypoints": "not json"})


if __name__ == "__main__":
    unittest.main()
