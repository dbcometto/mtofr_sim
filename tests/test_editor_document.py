"""Tests for EditorDocument (interface/mission_editor/editor_document.py): the web editor's
own data about a draft (node layout, unset and following-Target key flags) kept beside the
mission graph, never in it."""
import unittest

from mtofr.environments.anywhere.platforms.interface.mission_editor import editor_document, graph_draft
from mtofr.environments.anywhere.platforms.interface.mission_editor.editor_document import EditorDocument


def _document() -> EditorDocument:
    """A draft with nodes start and n2 (both placed) and keys ugv1/goal (unset, following) and other/flag."""
    graph = graph_draft.add_node(graph_draft.blank_graph(), "n2")
    graph = graph_draft.add_knowledge_key(graph, "ugv1/goal", float, 0.0)
    graph = graph_draft.add_knowledge_key(graph, "other/flag", bool, False)
    return EditorDocument(graph, layout={"start": (0.0, 0.0), "n2": (1.0, 2.0)},
                          unset_keys=frozenset({"ugv1/goal"}), following_keys=frozenset({"ugv1/goal"}))


class TestKeysAndNamespaces(unittest.TestCase):
    def test_split_and_join_use_the_last_slash(self):
        """A key splits at its last "/", and an empty namespace joins to just the name."""
        self.assertEqual(editor_document.split_key("a/b/c"), ("a/b", "c"))
        self.assertEqual(editor_document.split_key("plain"), ("", "plain"))
        self.assertEqual(editor_document.join_key("ugv1", "goal"), "ugv1/goal")
        self.assertEqual(editor_document.join_key("", "goal"), "goal")


class TestWithGraph(unittest.TestCase):
    def test_a_node_rename_carries_its_position(self):
        """rename_node moves the node's position to its new id."""
        document = _document()
        new_graph = graph_draft.rename_node(document.graph, "n2", "home")
        renamed = editor_document.with_graph(document, new_graph, "rename_node", {"old_id": "n2", "new_id": "home"})
        self.assertEqual(renamed.layout, {"start": (0.0, 0.0), "home": (1.0, 2.0)})

    def test_a_node_removal_drops_its_position(self):
        """Removing a node drops its position."""
        document = _document()
        new_graph = graph_draft.remove_node(document.graph, "n2")
        self.assertEqual(editor_document.with_graph(document, new_graph, "remove_node", {"node_id": "n2"}).layout,
                         {"start": (0.0, 0.0)})

    def test_a_key_rename_carries_its_flags(self):
        """rename_knowledge_key moves both flags to the new key."""
        document = _document()
        new_graph = graph_draft.rename_knowledge_key(document.graph, "ugv1/goal", "ugv1/aim")
        renamed = editor_document.with_graph(document, new_graph, "rename_knowledge_key",
                                             {"old_key": "ugv1/goal", "new_key": "ugv1/aim"})
        self.assertEqual((renamed.unset_keys, renamed.following_keys), ({"ugv1/aim"}, {"ugv1/aim"}))

    def test_a_key_removal_drops_its_flags(self):
        """Removing a key drops its flags."""
        document = _document()
        new_graph = graph_draft.remove_knowledge_key(document.graph, "ugv1/goal")
        removed = editor_document.with_graph(document, new_graph, "remove_knowledge_key", {"key": "ugv1/goal"})
        self.assertEqual((removed.unset_keys, removed.following_keys), (frozenset(), frozenset()))

    def test_editing_a_keys_value_clears_unset_but_keeps_following(self):
        """edit_knowledge_key means the operator set a value: unset clears, following stays."""
        document = _document()
        new_graph = graph_draft.edit_knowledge_key(document.graph, "ugv1/goal", float, 3.0)
        edited = editor_document.with_graph(document, new_graph, "edit_knowledge_key", {"key": "ugv1/goal"})
        self.assertEqual((edited.unset_keys, edited.following_keys), (frozenset(), {"ugv1/goal"}))


class TestEditorSteps(unittest.TestCase):
    def test_move_nodes_places_only_known_nodes(self):
        """move_nodes sets positions as float pairs, and refuses a node that doesn't exist."""
        moved = editor_document.move_nodes(_document(), {"n2": [3, 4]})
        self.assertEqual(moved.layout["n2"], (3.0, 4.0))
        with self.assertRaises(ValueError):
            editor_document.move_nodes(_document(), {"ghost": (0, 0)})

    def test_declare_key_sets_the_requested_flags(self):
        """declare_key adds the key and flags it as asked."""
        declared = editor_document.declare_key(_document(), "ugv1/new", int, 0, unset=True, follows_target=False)
        self.assertIn("ugv1/new", declared.graph["knowledge"])
        self.assertIn("ugv1/new", declared.unset_keys)
        self.assertNotIn("ugv1/new", declared.following_keys)

    def test_set_key_flags_sets_clears_and_leaves(self):
        """None leaves a flag alone; True and False set and clear it; an unknown key raises."""
        changed = editor_document.set_key_flags(_document(), "ugv1/goal", unset=False)
        self.assertEqual((changed.unset_keys, changed.following_keys), (frozenset(), {"ugv1/goal"}))
        with self.assertRaises(ValueError):
            editor_document.set_key_flags(_document(), "ghost", unset=True)

    def test_retarget_moves_following_keys_and_skips_collisions(self):
        """Following keys in the old namespace move to the new one; a taken name is skipped and reported."""
        document = editor_document.declare_key(_document(), "ugv1/spot", float, 0.0, follows_target=True)
        document = editor_document.declare_key(document, "ugv2/spot", float, 0.0)
        retargeted, skipped = editor_document.retarget(document, "ugv1", "ugv2")
        self.assertIn("ugv2/goal", retargeted.graph["knowledge"])
        self.assertIn("ugv2/goal", retargeted.unset_keys)   # flags travel with the rename
        self.assertIn("other/flag", retargeted.graph["knowledge"])   # not following: untouched
        self.assertEqual(skipped, ["ugv1/spot"])

    def test_namespace_to_retarget_is_the_most_common_following_namespace(self):
        """The prompt namespace is the one most following keys share, or None with none following."""
        self.assertEqual(_document().namespace_to_retarget(), "ugv1")
        self.assertIsNone(EditorDocument(graph_draft.blank_graph()).namespace_to_retarget())


class TestJson(unittest.TestCase):
    def test_the_sidecar_round_trips_and_ignores_stale_entries(self):
        """sidecar_to_json/document_from_json round trip, and entries for missing nodes or keys are dropped."""
        document = _document()
        data = editor_document.sidecar_to_json(document)
        restored = editor_document.document_from_json(document.graph, data)
        self.assertEqual((restored.layout, restored.unset_keys, restored.following_keys),
                         (document.layout, document.unset_keys, document.following_keys))
        stale = {"layout": {"ghost": [0, 0]}, "unset_keys": ["ghost/key"], "following_keys": []}
        self.assertEqual(editor_document.document_from_json(document.graph, stale).layout, {})


if __name__ == "__main__":
    unittest.main()
