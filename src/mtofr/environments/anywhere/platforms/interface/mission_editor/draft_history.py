"""Defines DraftHistory: the one draft a mission editor holds, plus its undo/redo
history. UI-free, so the Tk window and the web editor panel share it."""


#========================================#
# Config
#========================================#

# Caps memory use for the undo history; unlikely to matter for a hand-edited
# mission graph, but an unbounded stack is needless for a session that could
# run for a long time.
UNDO_HISTORY_LIMIT = 50







#========================================#
# Draft History
#========================================#

class DraftHistory:
    """The current draft plus undo/redo stacks. set() is the single choke point every
    draft mutation (including Load Live/New Blank/Load File, treated as ordinary
    undoable actions) goes through. Every mutation helper in graph_draft.py returns a
    brand-new top-level dict rather than mutating in place, so recording the *old*
    draft object -- no copying needed -- is enough for a full undo history; a fresh
    action always invalidates whatever was available to redo."""

    def __init__(self, draft: dict, limit: int = UNDO_HISTORY_LIMIT):
        """Starts on `draft` with empty history, keeping at most `limit` undo entries."""
        self.draft = draft
        self.limit = limit
        self.undo_stack = []   # past drafts, most recent last
        self.redo_stack = []   # drafts undone away from, most recent last
        self._group_open = False       # True while a group is open: all its edits share one undo entry
        self._group_recorded = False   # whether the open group has already pushed its entry

    @property
    def can_undo(self) -> bool:
        """Whether there's a past draft to go back to."""
        return bool(self.undo_stack)

    @property
    def can_redo(self) -> bool:
        """Whether there's an undone draft to go forward to."""
        return bool(self.redo_stack)

    def set(self, new_draft: dict) -> None:
        """Makes `new_draft` current as one undoable step (or part of the open group's step)."""
        if not (self._group_open and self._group_recorded):
            self.undo_stack.append(self.draft)
            del self.undo_stack[:-self.limit]
        self._group_recorded = self._group_open
        self.redo_stack.clear()
        self.draft = new_draft

    def undo(self) -> bool:
        """Restores the previous draft; False (and no change) if there is none."""
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.draft)
        self.draft = self.undo_stack.pop()
        return True

    def redo(self) -> bool:
        """Re-applies the last undone draft; False (and no change) if there is none."""
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.draft)
        self.draft = self.redo_stack.pop()
        return True

    def begin_group(self) -> None:
        """Until end_group(), every set() shares one undo entry (one undo for the whole group)."""
        self._group_open = True
        self._group_recorded = False

    def end_group(self) -> None:
        """Closes the group begin_group() opened."""
        self._group_open = False
        self._group_recorded = False
