"""Smoke tests for MissionEditorWindow: real Tk widgets (Treeviews, Notebook,
matplotlib preview canvas) driven directly against a real World/Backseater. The
three modal dialog classes are patched with a trivial stand-in that returns a
canned result without opening a real Toplevel or blocking on wait_window(), so
each button handler's wiring (draft mutation, selection persistence) is exercised
without needing to drive real dialog widgets. Skips if this environment cannot
open a Tk window at all (e.g. a headless CI runner with no display)."""
import unittest
from unittest.mock import patch

import tkinter as tk

try:
    _probe = tk.Tk()
    _probe.destroy()
    TK_AVAILABLE = True
except tk.TclError:
    TK_AVAILABLE = False

from mtofr.backseater.backseater import Backseater
from mtofr.database import KnowledgeDatabase, Location, PlatformRecord, PlatformStatus
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater

if TK_AVAILABLE:
    from mtofr.mission_editor.window import MissionEditorWindow
    from mtofr.mission_editor import graph_draft


class _StubDialog:
    """A callable stand-in for a modal dialog class: constructing "it" (calling
    the patched class) just returns an object whose `.result` is the canned value
    given here, without creating any real Toplevel or blocking the caller."""
    def __init__(self, result):
        self._result = result

    def __call__(self, *args, **kwargs):
        stub = object.__new__(_StubDialog)
        stub.result = self._result
        return stub


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionEditorWindow(unittest.TestCase):
    def setUp(self):
        hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=hardware)
        mission_graph = {
            "knowledge": {
                "goal": {"type": Location, "value": Location(2.0, 0.0)},
                "tolerance": {"type": float, "value": 0.5},
            },
            "nodes": {"n1": {"primitives": {}}},
            "edges": {},
            "start": "n1",
        }
        self.target_backseater = Backseater(frontseater=self.frontseater, knowledge_database=KnowledgeDatabase(),
                                             mission_graph=mission_graph, platform_id="ugv1", privilege_level=1)
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": self.target_backseater})
        self.root = tk.Tk()
        self.window = MissionEditorWindow(self.root, self.world, own_platform_id="interface")

    def tearDown(self):
        self.window.close()
        self.root.destroy()
        self.frontseater.shutdown()

    #==========# Nodes #==========#

    def test_adding_a_node_adds_it_to_the_draft(self):
        with patch("mtofr.mission_editor.window._TextInputDialog", _StubDialog("n2")):
            self.window._on_add_node()
        self.assertIn("n2", self.window.draft["nodes"])

    def test_renaming_the_selected_node_keeps_it_selected(self):
        self.window.selected_node_id = "start"
        self.window._refresh_nodes_tree()
        with patch("mtofr.mission_editor.window._TextInputDialog", _StubDialog("renamed")):
            self.window._on_rename_node()
        self.assertEqual(self.window.selected_node_id, "renamed")
        self.assertIn("renamed", self.window.nodes_tree.selection())

    def test_removing_the_selected_node_clears_the_selection(self):
        self.window.selected_node_id = "start"
        self.window._on_remove_node()
        self.assertIsNone(self.window.selected_node_id)

    #==========# Primitives #==========#

    def test_adding_a_primitive_selects_it(self):
        self.window.selected_node_id = "start"
        self.window._refresh_nodes_tree()
        canned = ("nav", "move_to", {"target": "goal", "tolerance": "tolerance"}, {})
        with patch("mtofr.mission_editor.window._PrimitiveDialog", _StubDialog(canned)):
            self.window._on_add_primitive()
        self.assertIn("nav", self.window.draft["nodes"]["start"]["primitives"])
        self.assertEqual(self.window.selected_primitive_name, "nav")
        self.assertIn("nav", self.window.primitives_tree.selection())

    def test_editing_a_primitive_can_rename_it_and_keeps_it_selected(self):
        self.window.selected_node_id = "start"
        self.window._set_draft(graph_draft.add_primitive(
            self.window.draft, "start", "nav", "move_to", {"target": "goal", "tolerance": "tolerance"}, {}
        ))
        self.window.selected_primitive_name = "nav"
        self.window._refresh_primitives_tree()
        canned = ("nav_renamed", "move_to", {"target": "goal", "tolerance": "tolerance"}, {})
        with patch("mtofr.mission_editor.window._PrimitiveDialog", _StubDialog(canned)):
            self.window._on_edit_primitive()
        self.assertNotIn("nav", self.window.draft["nodes"]["start"]["primitives"])
        self.assertIn("nav_renamed", self.window.draft["nodes"]["start"]["primitives"])
        self.assertEqual(self.window.selected_primitive_name, "nav_renamed")

    #==========# Edges #==========#

    def test_adding_an_edge(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        with patch("mtofr.mission_editor.window._EdgeDialog", _StubDialog(("start", "n2", []))):
            self.window._on_add_edge()
        self.assertEqual(self.window.draft["edges"]["start"], [{"condition": [], "to": "n2"}])

    def test_editing_an_edge_updates_its_condition(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._set_draft(graph_draft.add_edge(self.window.draft, "start", "n2", []))
        row_id = next(iter(self.window.edges_tree.get_children()))
        self.window.edges_tree.selection_set(row_id)
        canned = ("start", "n2", ["goal", "is", "not", None])
        with patch("mtofr.mission_editor.window._EdgeDialog", _StubDialog(canned)):
            self.window._on_edit_edge()
        self.assertEqual(self.window.draft["edges"]["start"][0]["condition"], ["goal", "is", "not", None])

    #==========# Knowledge #==========#

    def test_adding_a_knowledge_key(self):
        with patch("mtofr.mission_editor.window._KnowledgeDialog", _StubDialog(("battery", float, 1.0))):
            self.window._on_add_knowledge_key()
        self.assertEqual(self.window.draft["knowledge"]["battery"], {"type": float, "value": 1.0})

    def test_editing_a_knowledge_key_changes_its_value(self):
        self.window._set_draft(graph_draft.add_knowledge_key(self.window.draft, "battery", float, 1.0))
        self.window.knowledge_tree.selection_set("battery")
        with patch("mtofr.mission_editor.window._KnowledgeDialog", _StubDialog(("battery", float, 0.5))):
            self.window._on_edit_knowledge_key()
        self.assertEqual(self.window.draft["knowledge"]["battery"]["value"], 0.5)

    def test_editing_a_knowledge_key_can_rename_it_and_cascades_to_bindings(self):
        draft = graph_draft.add_knowledge_key(self.window.draft, "battery", float, 1.0)
        draft = graph_draft.add_primitive(draft, "start", "nav", "move_to", {"tolerance": "battery"}, {})
        self.window._set_draft(draft)
        self.window.knowledge_tree.selection_set("battery")
        with patch("mtofr.mission_editor.window._KnowledgeDialog", _StubDialog(("battery_level", float, 1.0))):
            self.window._on_edit_knowledge_key()
        self.assertNotIn("battery", self.window.draft["knowledge"])
        self.assertEqual(self.window.draft["knowledge"]["battery_level"], {"type": float, "value": 1.0})
        self.assertEqual(self.window.draft["nodes"]["start"]["primitives"]["nav"]["inputs"]["tolerance"], "battery_level")

    #==========# Push #==========#

    def test_push_writes_the_draft_to_the_target_platforms_mission_database(self):
        # Privilege gate needs the target to already know "interface" outranks it
        # -- normally seeded by mesh sync, done directly here.
        self.target_backseater.platform_database.declare(
            "interface", PlatformRecord(privilege_level=0, status=PlatformStatus("idle"))
        )
        self.window.target_platform_id.set("ugv1")
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_push()
        self.assertIs(self.target_backseater.mission_database.get("ugv1"), self.window.draft)


if __name__ == "__main__":
    unittest.main()