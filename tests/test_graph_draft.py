"""Tests for mtofr.world.interface.mission_editor.graph_draft: pure mutation helpers over a draft
mission-graph dict, independent of the Tk window that calls them. Each mutator
must return a *new* top-level dict object rather than mutating in place (see the
module docstring for why -- MissionGraphViewer's layout cache is keyed by identity)."""
import unittest

from mtofr.world.interface.mission_editor import graph_draft


class TestBlankAndLoad(unittest.TestCase):
    def test_blank_graph_has_one_empty_start_node(self):
        graph = graph_draft.blank_graph()
        self.assertEqual(graph["start"], "start")
        self.assertEqual(graph["nodes"], {"start": {"primitives": {}}})
        self.assertEqual(graph["edges"], {})

    def test_load_draft_is_independent_of_the_source(self):
        source = {"knowledge": {}, "nodes": {"n1": {"primitives": {}}}, "edges": {}, "start": "n1"}
        draft = graph_draft.load_draft(source)
        draft["nodes"]["n2"] = {"primitives": {}}
        self.assertNotIn("n2", source["nodes"])


class TestNodeMutations(unittest.TestCase):
    def setUp(self):
        self.draft = graph_draft.blank_graph()

    def test_add_node_creates_a_new_object(self):
        new_draft = graph_draft.add_node(self.draft, "n2")
        self.assertIn("n2", new_draft["nodes"])
        self.assertNotIn("n2", self.draft["nodes"])
        self.assertIsNot(new_draft, self.draft)

    def test_add_node_duplicate_raises(self):
        with self.assertRaises(ValueError):
            graph_draft.add_node(self.draft, "start")

    def test_remove_node_drops_edges_referencing_it(self):
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.remove_node(draft, "n2")
        self.assertNotIn("n2", draft["nodes"])
        self.assertNotIn("start", draft["edges"])

    def test_remove_node_that_was_start_falls_back_to_another_node(self):
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.remove_node(draft, "start")
        self.assertEqual(draft["start"], "n2")

    def test_rename_node_updates_edges_and_start(self):
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.rename_node(draft, "start", "renamed")
        self.assertIn("renamed", draft["nodes"])
        self.assertEqual(draft["start"], "renamed")
        self.assertIn("renamed", draft["edges"])
        self.assertEqual(draft["edges"]["renamed"][0]["to"], "n2")

    def test_rename_node_to_existing_id_raises(self):
        draft = graph_draft.add_node(self.draft, "n2")
        with self.assertRaises(ValueError):
            graph_draft.rename_node(draft, "start", "n2")

    def test_set_start_node(self):
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.set_start_node(draft, "n2")
        self.assertEqual(draft["start"], "n2")

    def test_set_start_node_unknown_raises(self):
        with self.assertRaises(ValueError):
            graph_draft.set_start_node(self.draft, "nope")


class TestPrimitiveMutations(unittest.TestCase):
    def setUp(self):
        self.draft = graph_draft.blank_graph()

    def test_add_primitive(self):
        draft = graph_draft.add_primitive(self.draft, "start", "nav", "move_to",
                                           {"target": "t", "tolerance": "tol"}, {"arrived": "a"})
        primitive = draft["nodes"]["start"]["primitives"]["nav"]
        self.assertEqual(primitive["capability"], "move_to")
        self.assertEqual(primitive["inputs"], {"target": "t", "tolerance": "tol"})

    def test_add_primitive_duplicate_name_raises(self):
        draft = graph_draft.add_primitive(self.draft, "start", "nav", "move_to", {}, {})
        with self.assertRaises(ValueError):
            graph_draft.add_primitive(draft, "start", "nav", "move_to", {}, {})

    def test_remove_primitive(self):
        draft = graph_draft.add_primitive(self.draft, "start", "nav", "move_to", {}, {})
        draft = graph_draft.remove_primitive(draft, "start", "nav")
        self.assertNotIn("nav", draft["nodes"]["start"]["primitives"])

    def test_edit_primitive_overwrites_capability_and_bindings(self):
        draft = graph_draft.add_primitive(self.draft, "start", "nav", "move_to", {"target": "t"}, {})
        draft = graph_draft.edit_primitive(draft, "start", "nav", "nav", "avoid", {"point": "p"}, {"registered": "r"})
        primitive = draft["nodes"]["start"]["primitives"]["nav"]
        self.assertEqual(primitive["capability"], "avoid")
        self.assertEqual(primitive["inputs"], {"point": "p"})

    def test_edit_primitive_can_rename(self):
        draft = graph_draft.add_primitive(self.draft, "start", "nav", "move_to", {}, {})
        draft = graph_draft.edit_primitive(draft, "start", "nav", "nav2", "move_to", {}, {})
        self.assertNotIn("nav", draft["nodes"]["start"]["primitives"])
        self.assertIn("nav2", draft["nodes"]["start"]["primitives"])

    def test_edit_primitive_rename_to_existing_name_raises(self):
        draft = graph_draft.add_primitive(self.draft, "start", "nav", "move_to", {}, {})
        draft = graph_draft.add_primitive(draft, "start", "other", "avoid", {}, {})
        with self.assertRaises(ValueError):
            graph_draft.edit_primitive(draft, "start", "nav", "other", "move_to", {}, {})


class TestEdgeMutations(unittest.TestCase):
    def setUp(self):
        self.draft = graph_draft.add_node(graph_draft.blank_graph(), "n2")

    def test_add_edge(self):
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        self.assertEqual(draft["edges"]["start"], [{"condition": ["a", "==", True], "to": "n2"}])

    def test_add_multiple_edges_from_same_source(self):
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "n2", ["b", "==", False])
        self.assertEqual(len(draft["edges"]["start"]), 2)

    def test_remove_edge_drops_source_entry_when_last_edge_removed(self):
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.remove_edge(draft, "start", 0)
        self.assertNotIn("start", draft["edges"])

    def test_remove_edge_keeps_other_edges_from_same_source(self):
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "n2", ["b", "==", False])
        draft = graph_draft.remove_edge(draft, "start", 0)
        self.assertEqual(draft["edges"]["start"], [{"condition": ["b", "==", False], "to": "n2"}])

    def test_edit_edge_updates_condition_in_place(self):
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.edit_edge(draft, "start", 0, "start", "n2", ["b", "==", False])
        self.assertEqual(draft["edges"]["start"], [{"condition": ["b", "==", False], "to": "n2"}])

    def test_edit_edge_can_change_source_and_target(self):
        draft = graph_draft.add_node(self.draft, "n3")
        draft = graph_draft.add_edge(draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.edit_edge(draft, "start", 0, "n2", "n3", ["b", "==", False])
        self.assertNotIn("start", draft["edges"])
        self.assertEqual(draft["edges"]["n2"], [{"condition": ["b", "==", False], "to": "n3"}])

    def test_edit_edge_preserves_other_edges_from_the_same_source(self):
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "n2", ["b", "==", False])
        draft = graph_draft.edit_edge(draft, "start", 0, "start", "n2", ["c", "==", True])
        self.assertEqual(len(draft["edges"]["start"]), 2)
        self.assertIn({"condition": ["c", "==", True], "to": "n2"}, draft["edges"]["start"])


class TestKnowledgeMutations(unittest.TestCase):
    def setUp(self):
        self.draft = graph_draft.blank_graph()

    def test_add_knowledge_key(self):
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        self.assertEqual(draft["knowledge"]["battery"], {"type": float, "value": 1.0})

    def test_add_knowledge_key_duplicate_raises(self):
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        with self.assertRaises(ValueError):
            graph_draft.add_knowledge_key(draft, "battery", float, 0.5)

    def test_remove_knowledge_key(self):
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        draft = graph_draft.remove_knowledge_key(draft, "battery")
        self.assertNotIn("battery", draft["knowledge"])

    def test_edit_knowledge_key_updates_value_and_type(self):
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        draft = graph_draft.edit_knowledge_key(draft, "battery", bool, True)
        self.assertEqual(draft["knowledge"]["battery"], {"type": bool, "value": True})

    def test_edit_knowledge_key_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            graph_draft.edit_knowledge_key(self.draft, "does_not_exist", float, 1.0)

    def test_rename_knowledge_key_moves_the_declaration(self):
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        draft = graph_draft.rename_knowledge_key(draft, "battery", "battery_level")
        self.assertNotIn("battery", draft["knowledge"])
        self.assertEqual(draft["knowledge"]["battery_level"], {"type": float, "value": 1.0})

    def test_rename_knowledge_key_updates_primitive_input_bindings(self):
        draft = graph_draft.add_knowledge_key(self.draft, "target", float, 1.0)
        draft = graph_draft.add_primitive(draft, "start", "nav", "move_to", {"target": "target"}, {})
        draft = graph_draft.rename_knowledge_key(draft, "target", "destination")
        self.assertEqual(draft["nodes"]["start"]["primitives"]["nav"]["inputs"], {"target": "destination"})

    def test_rename_knowledge_key_updates_primitive_output_bindings(self):
        draft = graph_draft.add_knowledge_key(self.draft, "arrived", bool, False)
        draft = graph_draft.add_primitive(draft, "start", "nav", "move_to", {}, {"arrived": "arrived"})
        draft = graph_draft.rename_knowledge_key(draft, "arrived", "has_arrived")
        self.assertEqual(draft["nodes"]["start"]["primitives"]["nav"]["outputs"], {"arrived": "has_arrived"})

    def test_rename_knowledge_key_updates_edge_condition_key_token(self):
        draft = graph_draft.add_knowledge_key(self.draft, "arrived", bool, False)
        draft = graph_draft.add_node(draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["arrived", "==", True])
        draft = graph_draft.rename_knowledge_key(draft, "arrived", "has_arrived")
        self.assertEqual(draft["edges"]["start"][0]["condition"], ["has_arrived", "==", True])

    def test_rename_knowledge_key_does_not_touch_a_coincidentally_matching_literal_value(self):
        # "arrived" appears here as the *value* being compared against, not as a
        # key reference (the key here is "status") -- renaming "arrived" must
        # leave this condition's literal value alone.
        draft = graph_draft.add_knowledge_key(self.draft, "arrived", str, "")
        draft = graph_draft.add_knowledge_key(draft, "status", str, "")
        draft = graph_draft.add_node(draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["status", "==", "arrived"])
        draft = graph_draft.rename_knowledge_key(draft, "arrived", "has_arrived")
        self.assertEqual(draft["edges"]["start"][0]["condition"], ["status", "==", "arrived"])

    def test_rename_knowledge_key_to_an_existing_key_raises(self):
        draft = graph_draft.add_knowledge_key(self.draft, "a", float, 1.0)
        draft = graph_draft.add_knowledge_key(draft, "b", float, 2.0)
        with self.assertRaises(ValueError):
            graph_draft.rename_knowledge_key(draft, "a", "b")

    def test_rename_knowledge_key_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            graph_draft.rename_knowledge_key(self.draft, "does_not_exist", "new_name")


if __name__ == "__main__":
    unittest.main()