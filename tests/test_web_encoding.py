"""Tests for web/encoding.py's condition_rows(): an edge condition as the graph editor's
condition builder shows it (all/any rows), or None when it needs the raw-token editor."""
import unittest

from mtofr.environments.ground_plane.platforms.interface.web.encoding import condition_rows


class TestConditionRows(unittest.TestCase):
    def test_a_single_comparison_is_one_row(self):
        """key == value becomes one "all" row, keeping the literal's real type."""
        self.assertEqual(condition_rows(["ugv1/arrived", "==", True]),
                         {"match": "all", "rows": [{"key": "ugv1/arrived", "operator": "==", "value": True, "negated": False}]})

    def test_and_and_or_become_all_and_any(self):
        """A flat and/or of checks becomes rows under match all/any."""
        both = condition_rows(["a", ">", 1, "and", "b", "<", 2])
        either = condition_rows(["a", ">", 1, "or", "b", "<", 2])
        self.assertEqual((both["match"], len(both["rows"])), ("all", 2))
        self.assertEqual((either["match"], len(either["rows"])), ("any", 2))

    def test_not_and_none_checks_are_rows(self):
        """A negated comparison and is/is not None checks each map to one row."""
        rows = condition_rows(["not", "a", "==", 1, "and", "b", "is", None, "and", "c", "is", "not", None])["rows"]
        self.assertEqual([(row["operator"], row["negated"]) for row in rows],
                         [("==", True), ("is None", False), ("is not None", False)])

    def test_nested_or_unparseable_conditions_need_raw_tokens(self):
        """A mixed and/or, parentheses, or a bad token list gives None."""
        self.assertIsNone(condition_rows(["a", "==", 1, "and", "(", "b", "==", 2, "or", "c", "==", 3, ")"]))
        self.assertIsNone(condition_rows(["a", "=="]))


if __name__ == "__main__":
    unittest.main()
