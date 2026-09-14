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
        self.frontseater = BicycleFrontseater(hardware=BicycleHardware())
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

        # A second platform, only used by the draft-source-mismatch tests below.
        self.other_frontseater = BicycleFrontseater(hardware=BicycleHardware())
        self.other_backseater = Backseater(frontseater=self.other_frontseater, knowledge_database=KnowledgeDatabase(),
                                            mission_graph=dict(mission_graph), platform_id="ugv2", privilege_level=1)

        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": self.target_backseater, "ugv2": self.other_backseater})
        self.root = tk.Tk()
        self.window = MissionEditorWindow(self.root, self.world, own_platform_id="interface")

    def tearDown(self):
        self.window.close()
        self.root.destroy()
        self.frontseater.shutdown()
        self.other_frontseater.shutdown()

    #==========# Live Control tab #==========#

    def test_live_control_is_the_first_and_selected_tab(self):
        self.assertEqual(self.window.notebook.tab(0, "text"), "Live Control")
        self.assertEqual(self.window.notebook.index(self.window.notebook.select()), 0)

    def test_live_knowledge_tree_reflects_the_target_platforms_knowledge(self):
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.assertIn("goal", self.window.live_knowledge_tree.get_children())
        self.assertIn("tolerance", self.window.live_knowledge_tree.get_children())

    def test_live_knowledge_tree_shows_key_type_and_value_columns(self):
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        row = self.window.live_knowledge_tree.item("tolerance")
        self.assertEqual(row["values"], ["tolerance", "float", "0.5"])

    def test_editing_a_live_value_writes_through_to_the_target_platform(self):
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        # selection_set() alone doesn't fire <<TreeviewSelect>> without a real
        # event loop pump -- call the handler directly, same as a real click would.
        self.window.live_knowledge_tree.selection_set("tolerance")
        self.window._on_live_knowledge_selected()
        with patch("mtofr.mission_editor.window._LiveValueDialog", _StubDialog(1.5)):
            self.window._on_edit_live_knowledge_value()
        self.assertEqual(self.target_backseater.knowledge_database.get("tolerance"), 1.5)

    def test_editing_a_live_location_value_writes_through_to_the_target_platform(self):
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.window.live_knowledge_tree.selection_set("goal")
        self.window._on_live_knowledge_selected()
        with patch("mtofr.mission_editor.window._LiveValueDialog", _StubDialog(Location(9.0, -1.0))):
            self.window._on_edit_live_knowledge_value()
        new_goal = self.target_backseater.knowledge_database.get("goal")
        self.assertEqual((new_goal.x, new_goal.y), (9.0, -1.0))

    def test_selection_survives_a_live_refresh(self):
        # Regression test: the periodic refresh used to delete()+reinsert() every
        # row every second, wiping the Treeview's selection each time and making
        # it hard to actually click "Edit Value" before it vanished again.
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.window.live_knowledge_tree.selection_set("tolerance")
        self.window._on_live_knowledge_selected()
        self.window._refresh_live_knowledge_tree()
        self.assertIn("tolerance", self.window.live_knowledge_tree.selection())
        self.assertEqual(self.window.selected_live_knowledge_key, "tolerance")

    def test_editing_a_live_value_with_no_selection_does_not_raise(self):
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.window._on_edit_live_knowledge_value()   # nothing selected -- must not raise

    def test_switching_target_platform_refreshes_the_live_knowledge_tree(self):
        self.window.target_platform_id.set("ugv2")
        self.window._on_target_platform_changed()
        self.assertIn("goal", self.window.live_knowledge_tree.get_children())

    #==========# Double-click-to-edit #==========#

    def test_double_click_bindings_are_registered_on_every_table(self):
        # Registration only, not a simulated click: like <Control-z>, driving a
        # real double-click via event_generate depends on window-manager focus
        # and exact row coordinates, which is unreliable to automate.
        self.assertTrue(self.window.nodes_tree.bind("<Double-1>"))
        self.assertTrue(self.window.primitives_tree.bind("<Double-1>"))
        self.assertTrue(self.window.edges_tree.bind("<Double-1>"))
        self.assertTrue(self.window.knowledge_tree.bind("<Double-1>"))
        self.assertTrue(self.window.live_knowledge_tree.bind("<Double-1>"))

    #==========# Undo/redo #==========#

    def test_undo_redo_buttons_start_disabled(self):
        self.assertEqual(str(self.window.undo_button["state"]), "disabled")
        self.assertEqual(str(self.window.redo_button["state"]), "disabled")

    def test_a_mutation_enables_undo_and_leaves_redo_disabled(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.assertEqual(str(self.window.undo_button["state"]), "normal")
        self.assertEqual(str(self.window.redo_button["state"]), "disabled")

    def test_undo_reverts_the_last_mutation(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_undo()
        self.assertNotIn("n2", self.window.draft["nodes"])

    def test_redo_reapplies_an_undone_mutation(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_undo()
        self.window._on_redo()
        self.assertIn("n2", self.window.draft["nodes"])

    def test_a_new_mutation_clears_the_redo_stack(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_undo()
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n3"))
        self.assertEqual(str(self.window.redo_button["state"]), "disabled")

    def test_undo_with_nothing_to_undo_does_not_raise(self):
        self.window._on_undo()   # must not raise
        self.assertEqual(self.window.draft, graph_draft.blank_graph())

    def test_redo_with_nothing_to_redo_does_not_raise(self):
        self.window._on_redo()   # must not raise

    def test_undo_then_redo_round_trips_back_to_the_same_draft(self):
        draft_after_add = graph_draft.add_node(self.window.draft, "n2")
        self.window._set_draft(draft_after_add)
        self.window._on_undo()
        self.window._on_redo()
        self.assertEqual(self.window.draft, draft_after_add)

    def test_multiple_undos_walk_back_through_history(self):
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n3"))
        self.window._on_undo()
        self.assertIn("n2", self.window.draft["nodes"])
        self.assertNotIn("n3", self.window.draft["nodes"])
        self.window._on_undo()
        self.assertNotIn("n2", self.window.draft["nodes"])

    def test_ctrl_z_and_ctrl_y_keybindings_are_registered(self):
        # Confirms the wiring exists rather than simulating a real keypress:
        # event_generate() for a keyboard event depends on actual window-manager
        # focus, which is unreliable to drive from an automated test even with a
        # real display -- _on_undo()/_on_redo() themselves are exercised directly
        # by the tests above.
        self.assertTrue(self.window.bind("<Control-z>"))
        self.assertTrue(self.window.bind("<Control-y>"))
        self.assertTrue(self.window.bind("<Control-Shift-Key-Z>"))

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

    #==========# Draft-source tracking #==========#

    def test_new_blank_starts_with_no_draft_source(self):
        self.assertIsNone(self.window.draft_source_platform_id)

    def test_load_live_records_the_source_platform_and_logs_it_to_the_console(self):
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.assertEqual(self.window.draft_source_platform_id, "ugv1")
        self.assertIn("ugv1", self.window.console_text.get("1.0", tk.END))

    def test_new_blank_after_load_live_clears_the_source(self):
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.window._on_new_blank()
        self.assertIsNone(self.window.draft_source_platform_id)

    def test_pushing_to_the_draft_source_platform_logs_no_mismatch_warning(self):
        for backseater in (self.target_backseater, self.other_backseater):
            backseater.platform_database.declare(
                "interface", PlatformRecord(privilege_level=0, status=PlatformStatus("idle"))
            )
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.window._on_push()
        self.assertNotIn("Warning", self.window.console_text.get("1.0", tk.END))

    def test_pushing_a_draft_loaded_from_a_different_platform_logs_a_mismatch_warning(self):
        for backseater in (self.target_backseater, self.other_backseater):
            backseater.platform_database.declare(
                "interface", PlatformRecord(privilege_level=0, status=PlatformStatus("idle"))
            )
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.window.target_platform_id.set("ugv2")
        self.window._on_push()
        console_contents = self.window.console_text.get("1.0", tk.END)
        self.assertIn("Warning", console_contents)
        self.assertIn("ugv1", console_contents)
        self.assertIn("ugv2", console_contents)

    #==========# Knowledge tree columns #==========#

    def test_knowledge_tree_shows_key_before_type_before_value(self):
        self.window._set_draft(graph_draft.add_knowledge_key(self.window.draft, "battery", float, 1.0))
        row = self.window.knowledge_tree.item("battery")
        self.assertEqual(row["values"], ["battery", "float", "1.0"])

    #==========# Graph tab Draft/Live preview toggle #==========#

    def test_draft_mode_note_mentions_editing(self):
        self.window.preview_mode.set("draft")
        self.window._on_preview_mode_changed()
        self.assertIn("draft", self.window.preview_mode_note.cget("text").lower())

    def test_live_mode_note_mentions_the_target_platform(self):
        self.window.target_platform_id.set("ugv1")
        self.window.preview_mode.set("live")
        self.window._on_preview_mode_changed()
        self.assertIn("ugv1", self.window.preview_mode_note.cget("text"))


if __name__ == "__main__":
    unittest.main()