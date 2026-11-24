"""Tests for DraftHistory, the UI-free draft-plus-undo/redo holder shared by the Tk
mission editor and the web editor panel."""
import unittest

from mtofr.environments.ground_plane.platforms.interface.mission_editor.draft_history import DraftHistory


class TestDraftHistory(unittest.TestCase):
    def test_starts_on_the_given_draft_with_nothing_to_undo_or_redo(self):
        """A fresh history holds the given draft and has empty stacks."""
        start = {"name": "start"}
        history = DraftHistory(start)
        self.assertIs(history.draft, start)
        self.assertFalse(history.can_undo)
        self.assertFalse(history.can_redo)

    def test_undo_and_redo_walk_back_and_forth_through_set_drafts(self):
        """set() records the old draft; undo() restores it and redo() re-applies the newer one."""
        first, second = {"name": "first"}, {"name": "second"}
        history = DraftHistory(first)
        history.set(second)
        self.assertTrue(history.undo())
        self.assertIs(history.draft, first)
        self.assertTrue(history.redo())
        self.assertIs(history.draft, second)

    def test_undo_and_redo_report_false_when_there_is_nothing_to_do(self):
        """With empty stacks, undo()/redo() return False and leave the draft alone."""
        start = {"name": "start"}
        history = DraftHistory(start)
        self.assertFalse(history.undo())
        self.assertFalse(history.redo())
        self.assertIs(history.draft, start)

    def test_a_new_set_clears_the_redo_stack(self):
        """After an undo, a fresh set() makes the undone draft unreachable."""
        history = DraftHistory({"name": "first"})
        history.set({"name": "second"})
        history.undo()
        history.set({"name": "third"})
        self.assertFalse(history.can_redo)

    def test_history_is_capped_at_its_limit(self):
        """Only the most recent `limit` past drafts are kept."""
        history = DraftHistory({"index": 0}, limit=3)
        for index in range(1, 6):
            history.set({"index": index})
        self.assertEqual([draft["index"] for draft in history.undo_stack], [2, 3, 4])

    def test_a_group_of_sets_is_one_undo_step(self):
        """Every set() between begin_group() and end_group() undoes together, back to the pre-group draft."""
        before = {"name": "before"}
        history = DraftHistory(before)
        history.begin_group()
        history.set({"name": "a"})
        history.set({"name": "b"})
        history.end_group()
        self.assertEqual(len(history.undo_stack), 1)
        history.undo()
        self.assertIs(history.draft, before)


if __name__ == "__main__":
    unittest.main()
