"""Tests for mtofr.environments.ground_plane.platforms.interface.mission_editor.graph_draft: pure mutation helpers over a draft
mission-graph dict, independent of the Tk window that calls them. Each mutator
must return a *new* top-level dict object rather than mutating in place (see the
module docstring for why -- MissionGraphViewer's layout cache is keyed by identity)."""
import unittest

from mtofr.environments.ground_plane.platforms.interface.mission_editor import graph_draft


class TestBlankAndLoad(unittest.TestCase):
    def test_blank_graph_has_one_empty_start_node(self):
        """blank_graph() has a single "start" node with no capability requests, and no edges."""
        graph = graph_draft.blank_graph()
        self.assertEqual(graph["start"], "start")
        self.assertEqual(graph["nodes"], {"start": {"capabilities": {}}})
        self.assertEqual(graph["edges"], {})

    def test_load_draft_is_independent_of_the_source(self):
        """Mutating a loaded draft leaves the source graph untouched."""
        source = {"knowledge": {}, "nodes": {"n1": {"capabilities": {}}}, "edges": {}, "start": "n1"}
        draft = graph_draft.load_draft(source)
        draft["nodes"]["n2"] = {"capabilities": {}}
        self.assertNotIn("n2", source["nodes"])


class TestNodeMutations(unittest.TestCase):
    def setUp(self):
        """Start each test from a blank graph."""
        self.draft = graph_draft.blank_graph()

    def test_add_node_creates_a_new_object(self):
        """add_node() returns a new dict containing the node and leaves the input unchanged."""
        new_draft = graph_draft.add_node(self.draft, "n2")
        self.assertIn("n2", new_draft["nodes"])
        self.assertNotIn("n2", self.draft["nodes"])
        self.assertIsNot(new_draft, self.draft)

    def test_add_node_duplicate_raises(self):
        """add_node() rejects an id that already exists."""
        with self.assertRaises(ValueError):
            graph_draft.add_node(self.draft, "start")

    def test_remove_node_drops_edges_referencing_it(self):
        """remove_node() also removes edges pointing at the removed node."""
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.remove_node(draft, "n2")
        self.assertNotIn("n2", draft["nodes"])
        self.assertNotIn("start", draft["edges"])

    def test_remove_node_that_was_start_falls_back_to_another_node(self):
        """Removing the start node makes a remaining node the start."""
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.remove_node(draft, "start")
        self.assertEqual(draft["start"], "n2")

    def test_rename_node_updates_edges_and_start(self):
        """rename_node() carries the new id into the start field and outgoing edges."""
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.rename_node(draft, "start", "renamed")
        self.assertIn("renamed", draft["nodes"])
        self.assertEqual(draft["start"], "renamed")
        self.assertIn("renamed", draft["edges"])
        self.assertEqual(draft["edges"]["renamed"][0]["to"], "n2")

    def test_rename_node_to_existing_id_raises(self):
        """rename_node() rejects a new id that is already taken."""
        draft = graph_draft.add_node(self.draft, "n2")
        with self.assertRaises(ValueError):
            graph_draft.rename_node(draft, "start", "n2")

    def test_set_start_node(self):
        """set_start_node() changes the start to an existing node."""
        draft = graph_draft.add_node(self.draft, "n2")
        draft = graph_draft.set_start_node(draft, "n2")
        self.assertEqual(draft["start"], "n2")

    def test_set_start_node_unknown_raises(self):
        """set_start_node() rejects a node id not in the graph."""
        with self.assertRaises(ValueError):
            graph_draft.set_start_node(self.draft, "nope")


class TestMissionName(unittest.TestCase):
    def test_set_mission_name_sets_a_stripped_name(self):
        """set_mission_name() stores the name (trimmed) and leaves the input unchanged."""
        draft = graph_draft.blank_graph()
        named = graph_draft.set_mission_name(draft, "  patrol east ")
        self.assertEqual(named["name"], "patrol east")
        self.assertNotIn("name", draft)

    def test_an_empty_name_removes_it(self):
        """set_mission_name() with an empty or blank name drops the "name" entry."""
        named = graph_draft.set_mission_name(graph_draft.blank_graph(), "patrol")
        self.assertNotIn("name", graph_draft.set_mission_name(named, "   "))


class TestCapabilityRequestMutations(unittest.TestCase):
    def setUp(self):
        """Start each test from a blank graph."""
        self.draft = graph_draft.blank_graph()

    def test_add_capability(self):
        """add_capability() stores the capability and input bindings on the node."""
        draft = graph_draft.add_capability(self.draft, "start", "nav", "move_to",
                                            {"target": "t", "tolerance": "tol"}, {"arrived": "a"})
        capability_request = draft["nodes"]["start"]["capabilities"]["nav"]
        self.assertEqual(capability_request["capability"], "move_to")
        self.assertEqual(capability_request["inputs"], {"target": "t", "tolerance": "tol"})

    def test_add_capability_duplicate_name_raises(self):
        """add_capability() rejects a name already used on the node."""
        draft = graph_draft.add_capability(self.draft, "start", "nav", "move_to", {}, {})
        with self.assertRaises(ValueError):
            graph_draft.add_capability(draft, "start", "nav", "move_to", {}, {})

    def test_remove_capability(self):
        """remove_capability() deletes the named capability request from the node."""
        draft = graph_draft.add_capability(self.draft, "start", "nav", "move_to", {}, {})
        draft = graph_draft.remove_capability(draft, "start", "nav")
        self.assertNotIn("nav", draft["nodes"]["start"]["capabilities"])

    def test_edit_capability_overwrites_capability_and_bindings(self):
        """edit_capability() replaces the capability and bindings."""
        draft = graph_draft.add_capability(self.draft, "start", "nav", "move_to", {"target": "t"}, {})
        draft = graph_draft.edit_capability(draft, "start", "nav", "nav", "avoid", {"point": "p"}, {"registered": "r"})
        capability_request = draft["nodes"]["start"]["capabilities"]["nav"]
        self.assertEqual(capability_request["capability"], "avoid")
        self.assertEqual(capability_request["inputs"], {"point": "p"})

    def test_edit_capability_can_rename(self):
        """edit_capability() with a new name moves the capability request to that name."""
        draft = graph_draft.add_capability(self.draft, "start", "nav", "move_to", {}, {})
        draft = graph_draft.edit_capability(draft, "start", "nav", "nav2", "move_to", {}, {})
        self.assertNotIn("nav", draft["nodes"]["start"]["capabilities"])
        self.assertIn("nav2", draft["nodes"]["start"]["capabilities"])

    def test_edit_capability_rename_to_existing_name_raises(self):
        """edit_capability() rejects renaming onto another capability request's name."""
        draft = graph_draft.add_capability(self.draft, "start", "nav", "move_to", {}, {})
        draft = graph_draft.add_capability(draft, "start", "other", "avoid", {}, {})
        with self.assertRaises(ValueError):
            graph_draft.edit_capability(draft, "start", "nav", "other", "move_to", {}, {})


class TestEdgeMutations(unittest.TestCase):
    def setUp(self):
        """Start each test from a blank graph plus a second node "n2"."""
        self.draft = graph_draft.add_node(graph_draft.blank_graph(), "n2")

    def test_add_edge(self):
        """add_edge() appends a condition/target entry under the source node."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        self.assertEqual(draft["edges"]["start"], [{"condition": ["a", "==", True], "to": "n2"}])

    def test_add_multiple_edges_from_same_source(self):
        """Several edges can leave the same source node."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "n2", ["b", "==", False])
        self.assertEqual(len(draft["edges"]["start"]), 2)

    def test_remove_edge_drops_source_entry_when_last_edge_removed(self):
        """Removing a source's last edge removes its entry from "edges"."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.remove_edge(draft, "start", 0)
        self.assertNotIn("start", draft["edges"])

    def test_remove_edge_keeps_other_edges_from_same_source(self):
        """remove_edge() removes only the edge at the given index."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "n2", ["b", "==", False])
        draft = graph_draft.remove_edge(draft, "start", 0)
        self.assertEqual(draft["edges"]["start"], [{"condition": ["b", "==", False], "to": "n2"}])

    def test_edit_edge_updates_condition_in_place(self):
        """edit_edge() with the same endpoints replaces only the condition."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.edit_edge(draft, "start", 0, "start", "n2", ["b", "==", False])
        self.assertEqual(draft["edges"]["start"], [{"condition": ["b", "==", False], "to": "n2"}])

    def test_edit_edge_can_change_source_and_target(self):
        """edit_edge() can move an edge to a different source and target."""
        draft = graph_draft.add_node(self.draft, "n3")
        draft = graph_draft.add_edge(draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.edit_edge(draft, "start", 0, "n2", "n3", ["b", "==", False])
        self.assertNotIn("start", draft["edges"])
        self.assertEqual(draft["edges"]["n2"], [{"condition": ["b", "==", False], "to": "n3"}])

    def test_edit_edge_preserves_other_edges_from_the_same_source(self):
        """edit_edge() leaves the source's other edges in place."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "n2", ["b", "==", False])
        draft = graph_draft.edit_edge(draft, "start", 0, "start", "n2", ["c", "==", True])
        self.assertEqual(len(draft["edges"]["start"]), 2)
        self.assertIn({"condition": ["c", "==", True], "to": "n2"}, draft["edges"]["start"])

    def test_edit_edge_with_the_same_source_keeps_its_priority(self):
        """Editing the first of two edges leaves it first (it isn't moved to the end of the list)."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "start", ["b", "==", True])
        draft = graph_draft.edit_edge(draft, "start", 0, "start", "n2", ["c", "==", True])
        self.assertEqual(draft["edges"]["start"][0], {"condition": ["c", "==", True], "to": "n2"})

    def test_move_edge_reorders_a_sources_edges(self):
        """move_edge() moves an edge to a new index, shifting the rest."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        draft = graph_draft.add_edge(draft, "start", "start", ["b", "==", True])
        draft = graph_draft.move_edge(draft, "start", 1, 0)
        self.assertEqual([edge["to"] for edge in draft["edges"]["start"]], ["start", "n2"])

    def test_move_edge_out_of_range_raises(self):
        """move_edge() raises IndexError for an index that doesn't exist."""
        draft = graph_draft.add_edge(self.draft, "start", "n2", ["a", "==", True])
        with self.assertRaises(IndexError):
            graph_draft.move_edge(draft, "start", 0, 1)


class TestKnowledgeMutations(unittest.TestCase):
    def setUp(self):
        """Start each test from a blank graph."""
        self.draft = graph_draft.blank_graph()

    def test_add_knowledge_key(self):
        """add_knowledge_key() declares the key with its type and default value."""
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        self.assertEqual(draft["knowledge"]["battery"], {"type": float, "value": 1.0})

    def test_add_knowledge_key_duplicate_raises(self):
        """add_knowledge_key() rejects a key that is already declared."""
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        with self.assertRaises(ValueError):
            graph_draft.add_knowledge_key(draft, "battery", float, 0.5)

    def test_remove_knowledge_key(self):
        """remove_knowledge_key() deletes the declaration."""
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        draft = graph_draft.remove_knowledge_key(draft, "battery")
        self.assertNotIn("battery", draft["knowledge"])

    def test_edit_knowledge_key_updates_value_and_type(self):
        """edit_knowledge_key() replaces both the type and the default value."""
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        draft = graph_draft.edit_knowledge_key(draft, "battery", bool, True)
        self.assertEqual(draft["knowledge"]["battery"], {"type": bool, "value": True})

    def test_edit_knowledge_key_unknown_key_raises(self):
        """edit_knowledge_key() rejects an undeclared key."""
        with self.assertRaises(ValueError):
            graph_draft.edit_knowledge_key(self.draft, "does_not_exist", float, 1.0)

    def test_rename_knowledge_key_moves_the_declaration(self):
        """rename_knowledge_key() moves the type and value to the new name."""
        draft = graph_draft.add_knowledge_key(self.draft, "battery", float, 1.0)
        draft = graph_draft.rename_knowledge_key(draft, "battery", "battery_level")
        self.assertNotIn("battery", draft["knowledge"])
        self.assertEqual(draft["knowledge"]["battery_level"], {"type": float, "value": 1.0})

    def test_rename_knowledge_key_updates_capability_request_input_bindings(self):
        """rename_knowledge_key() rewrites capability request input bindings to the new name."""
        draft = graph_draft.add_knowledge_key(self.draft, "target", float, 1.0)
        draft = graph_draft.add_capability(draft, "start", "nav", "move_to", {"target": "target"}, {})
        draft = graph_draft.rename_knowledge_key(draft, "target", "destination")
        self.assertEqual(draft["nodes"]["start"]["capabilities"]["nav"]["inputs"], {"target": "destination"})

    def test_rename_knowledge_key_updates_capability_request_output_bindings(self):
        """rename_knowledge_key() rewrites capability request output bindings to the new name."""
        draft = graph_draft.add_knowledge_key(self.draft, "arrived", bool, False)
        draft = graph_draft.add_capability(draft, "start", "nav", "move_to", {}, {"arrived": "arrived"})
        draft = graph_draft.rename_knowledge_key(draft, "arrived", "has_arrived")
        self.assertEqual(draft["nodes"]["start"]["capabilities"]["nav"]["outputs"], {"arrived": "has_arrived"})

    def test_rename_knowledge_key_updates_edge_condition_key_token(self):
        """rename_knowledge_key() rewrites the key token in edge conditions."""
        draft = graph_draft.add_knowledge_key(self.draft, "arrived", bool, False)
        draft = graph_draft.add_node(draft, "n2")
        draft = graph_draft.add_edge(draft, "start", "n2", ["arrived", "==", True])
        draft = graph_draft.rename_knowledge_key(draft, "arrived", "has_arrived")
        self.assertEqual(draft["edges"]["start"][0]["condition"], ["has_arrived", "==", True])

    def test_rename_knowledge_key_does_not_touch_a_coincidentally_matching_literal_value(self):
        """rename_knowledge_key() leaves a literal condition value equal to the old name alone."""
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
        """rename_knowledge_key() rejects a new name that is already declared."""
        draft = graph_draft.add_knowledge_key(self.draft, "a", float, 1.0)
        draft = graph_draft.add_knowledge_key(draft, "b", float, 2.0)
        with self.assertRaises(ValueError):
            graph_draft.rename_knowledge_key(draft, "a", "b")

    def test_rename_knowledge_key_unknown_key_raises(self):
        """rename_knowledge_key() rejects an undeclared key."""
        with self.assertRaises(ValueError):
            graph_draft.rename_knowledge_key(self.draft, "does_not_exist", "new_name")


if __name__ == "__main__":
    unittest.main()
