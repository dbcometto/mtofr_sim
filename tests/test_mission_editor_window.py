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

from mtofr.database import Location, PlatformRecord, PlatformStatus
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.world import World
from mtofr.platform.platform import Platform

if TK_AVAILABLE:
    from mtofr.environments.anywhere.platforms.interface.mission_editor.window import MissionEditorWindow
    from mtofr.environments.anywhere.platforms.interface.mission_editor import graph_draft


class _StubDialog:
    """A callable stand-in for a modal dialog class: constructing "it" (calling
    the patched class) just returns an object whose `.result` is the canned value
    given here, without creating any real Toplevel or blocking the caller."""
    def __init__(self, result):
        """Hold the canned result every "dialog" will return."""
        self._result = result

    def __call__(self, *args, **kwargs):
        """Stand in for constructing the dialog: return an object carrying the canned result."""
        stub = object.__new__(_StubDialog)
        stub.result = self._result
        return stub


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionEditorWindow(unittest.TestCase):
    def setUp(self):
        """Build a two-UGV world and an editor window on a fresh Tk root."""
        mission_graph = {
            "knowledge": {
                "goal": {"type": Location, "value": Location(2.0, 0.0)},
                "tolerance": {"type": float, "value": 0.5},
            },
            "nodes": {"n1": {"capabilities":{}}},
            "edges": {},
            "start": "n1",
        }
        target_platform = Platform(bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_graph))
        self.frontseater, self.target_backseater = target_platform.frontseater, target_platform.backseater

        # A second platform, only used by the draft-source-mismatch tests below.
        other_platform = Platform(bicycle_ugv("ugv2", 0.0, 0.0, mission_graph=dict(mission_graph)))
        self.other_frontseater, self.other_backseater = other_platform.frontseater, other_platform.backseater

        self.world = World(GroundPlaneEnv(), platforms={"ugv1": target_platform, "ugv2": other_platform})
        self.root = tk.Tk()
        self.window = MissionEditorWindow(self.root, self.world, own_platform_id="interface")

    def tearDown(self):
        """Close the window, destroy the Tk root, and shut down both UGVs' MPC workers."""
        self.window.close()
        self.root.destroy()
        self.frontseater.shutdown()
        self.other_frontseater.shutdown()

    #===============# Live Control Tab #===============#

    def test_live_control_is_the_first_and_selected_tab(self):
        """Live Control is the first notebook tab and is selected on open."""
        self.assertEqual(self.window.notebook.tab(0, "text"), "Live Control")
        self.assertEqual(self.window.notebook.index(self.window.notebook.select()), 0)

    def test_live_knowledge_tree_reflects_the_target_platforms_knowledge(self):
        """The live knowledge tree lists the target platform's knowledge keys."""
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.assertIn("goal", self.window.live_knowledge_tree.get_children())
        self.assertIn("tolerance", self.window.live_knowledge_tree.get_children())

    def test_live_knowledge_tree_shows_key_type_and_value_columns(self):
        """A live knowledge row's columns are key, type name, and value."""
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        row = self.window.live_knowledge_tree.item("tolerance")
        self.assertEqual(row["values"], ["tolerance", "float", "0.5"])

    def test_editing_a_live_value_writes_through_to_the_target_platform(self):
        """Editing a live float value sets it in the target's knowledge database."""
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        # selection_set() alone doesn't fire <<TreeviewSelect>> without a real
        # event loop pump -- call the handler directly, same as a real click would.
        self.window.live_knowledge_tree.selection_set("tolerance")
        self.window._on_live_knowledge_selected()
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._LiveValueDialog", _StubDialog(1.5)):
            self.window._on_edit_live_knowledge_value()
        self.assertEqual(self.target_backseater.knowledge_database.get("tolerance"), 1.5)

    def test_editing_a_live_location_value_writes_through_to_the_target_platform(self):
        """Editing a live Location value sets it in the target's knowledge database."""
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.window.live_knowledge_tree.selection_set("goal")
        self.window._on_live_knowledge_selected()
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._LiveValueDialog", _StubDialog(Location(9.0, -1.0))):
            self.window._on_edit_live_knowledge_value()
        new_goal = self.target_backseater.knowledge_database.get("goal")
        self.assertEqual((new_goal.x, new_goal.y), (9.0, -1.0))

    def test_selection_survives_a_live_refresh(self):
        """A periodic live refresh keeps the selected row selected."""
        # The refresh runs every second; if it wiped the Treeview's selection, the
        # row would deselect before the user could click "Edit Value".
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.window.live_knowledge_tree.selection_set("tolerance")
        self.window._on_live_knowledge_selected()
        self.window._refresh_live_knowledge_tree()
        self.assertIn("tolerance", self.window.live_knowledge_tree.selection())
        self.assertEqual(self.window.selected_live_knowledge_key, "tolerance")

    def test_editing_a_live_value_with_no_selection_does_not_raise(self):
        """Edit Value with nothing selected is a no-op."""
        self.window.target_platform_id.set("ugv1")
        self.window._refresh_live_knowledge_tree()
        self.window._on_edit_live_knowledge_value()   # nothing selected -- must not raise

    def test_switching_target_platform_refreshes_the_live_knowledge_tree(self):
        """Changing the target platform repopulates the live knowledge tree from it."""
        self.window.target_platform_id.set("ugv2")
        self.window._on_target_platform_changed()
        self.assertIn("goal", self.window.live_knowledge_tree.get_children())





    #===============#Double-Click to Edit #===============#

    def test_double_click_bindings_are_registered_on_every_table(self):
        """Every editor table has a <Double-1> binding."""
        # Registration only, not a simulated click: like <Control-z>, driving a
        # real double-click via event_generate depends on window-manager focus
        # and exact row coordinates, which is unreliable to automate.
        self.assertTrue(self.window.nodes_tree.bind("<Double-1>"))
        self.assertTrue(self.window.capabilities_tree.bind("<Double-1>"))
        self.assertTrue(self.window.edges_tree.bind("<Double-1>"))
        self.assertTrue(self.window.knowledge_tree.bind("<Double-1>"))
        self.assertTrue(self.window.live_knowledge_tree.bind("<Double-1>"))





    #===============#Undo/Redo #===============#

    def test_undo_redo_buttons_start_disabled(self):
        """Undo and Redo are disabled on a fresh window."""
        self.assertEqual(str(self.window.undo_button["state"]), "disabled")
        self.assertEqual(str(self.window.redo_button["state"]), "disabled")

    def test_a_mutation_enables_undo_and_leaves_redo_disabled(self):
        """A draft mutation enables Undo while Redo stays disabled."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.assertEqual(str(self.window.undo_button["state"]), "normal")
        self.assertEqual(str(self.window.redo_button["state"]), "disabled")

    def test_undo_reverts_the_last_mutation(self):
        """Undo restores the draft from before the last mutation."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_undo()
        self.assertNotIn("n2", self.window.draft["nodes"])

    def test_redo_reapplies_an_undone_mutation(self):
        """Redo reapplies the mutation that was just undone."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_undo()
        self.window._on_redo()
        self.assertIn("n2", self.window.draft["nodes"])

    def test_a_new_mutation_clears_the_redo_stack(self):
        """A mutation after an undo disables Redo."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_undo()
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n3"))
        self.assertEqual(str(self.window.redo_button["state"]), "disabled")

    def test_undo_with_nothing_to_undo_does_not_raise(self):
        """Undo with empty history leaves the blank draft unchanged."""
        self.window._on_undo()   # must not raise
        self.assertEqual(self.window.draft, graph_draft.blank_graph())

    def test_redo_with_nothing_to_redo_does_not_raise(self):
        """Redo with nothing undone is a no-op."""
        self.window._on_redo()   # must not raise

    def test_undo_then_redo_round_trips_back_to_the_same_draft(self):
        """Undo followed by Redo restores an equal draft."""
        draft_after_add = graph_draft.add_node(self.window.draft, "n2")
        self.window._set_draft(draft_after_add)
        self.window._on_undo()
        self.window._on_redo()
        self.assertEqual(self.window.draft, draft_after_add)

    def test_multiple_undos_walk_back_through_history(self):
        """Successive undos revert mutations one at a time, newest first."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n3"))
        self.window._on_undo()
        self.assertIn("n2", self.window.draft["nodes"])
        self.assertNotIn("n3", self.window.draft["nodes"])
        self.window._on_undo()
        self.assertNotIn("n2", self.window.draft["nodes"])

    def test_ctrl_z_and_ctrl_y_keybindings_are_registered(self):
        """The window binds Ctrl+Z, Ctrl+Y, and Ctrl+Shift+Z."""
        # Confirms the wiring exists rather than simulating a real keypress:
        # event_generate() for a keyboard event depends on actual window-manager
        # focus, which is unreliable to drive from an automated test even with a
        # real display -- _on_undo()/_on_redo() themselves are exercised directly
        # by the tests above.
        self.assertTrue(self.window.bind("<Control-z>"))
        self.assertTrue(self.window.bind("<Control-y>"))
        self.assertTrue(self.window.bind("<Control-Shift-Key-Z>"))





    #===============#Nodes #===============#

    def test_adding_a_node_adds_it_to_the_draft(self):
        """Add Node puts the entered id into the draft."""
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._TextInputDialog", _StubDialog("n2")):
            self.window._on_add_node()
        self.assertIn("n2", self.window.draft["nodes"])

    def test_renaming_the_selected_node_keeps_it_selected(self):
        """Renaming the selected node keeps it selected under its new id."""
        self.window.selected_node_id = "start"
        self.window._refresh_nodes_tree()
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._TextInputDialog", _StubDialog("renamed")):
            self.window._on_rename_node()
        self.assertEqual(self.window.selected_node_id, "renamed")
        self.assertIn("renamed", self.window.nodes_tree.selection())

    def test_removing_the_selected_node_clears_the_selection(self):
        """Removing the selected node leaves no node selected."""
        self.window.selected_node_id = "start"
        self.window._on_remove_node()
        self.assertIsNone(self.window.selected_node_id)





    #===============#Capability Requests #===============#

    def test_adding_a_capability_selects_it(self):
        """Add Capability puts it on the selected node and selects it."""
        self.window.selected_node_id = "start"
        self.window._refresh_nodes_tree()
        canned = ("nav", "move_to", {"target": "goal", "tolerance": "tolerance"}, {})
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._CapabilityRequestDialog", _StubDialog(canned)):
            self.window._on_add_capability()
        self.assertIn("nav", self.window.draft["nodes"]["start"]["capabilities"])
        self.assertEqual(self.window.selected_request_name, "nav")
        self.assertIn("nav", self.window.capabilities_tree.selection())

    def test_editing_a_capability_can_rename_it_and_keeps_it_selected(self):
        """Editing a capability request with a new name renames it and keeps it selected."""
        self.window.selected_node_id = "start"
        self.window._set_draft(graph_draft.add_capability(
            self.window.draft, "start", "nav", "move_to", {"target": "goal", "tolerance": "tolerance"}, {}
        ))
        self.window.selected_request_name = "nav"
        self.window._refresh_capabilities_tree()
        canned = ("nav_renamed", "move_to", {"target": "goal", "tolerance": "tolerance"}, {})
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._CapabilityRequestDialog", _StubDialog(canned)):
            self.window._on_edit_capability()
        self.assertNotIn("nav", self.window.draft["nodes"]["start"]["capabilities"])
        self.assertIn("nav_renamed", self.window.draft["nodes"]["start"]["capabilities"])
        self.assertEqual(self.window.selected_request_name, "nav_renamed")





    #===============#Edges #===============#

    def test_adding_an_edge(self):
        """Add Edge puts the dialog's source, target, and condition into the draft."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._EdgeDialog", _StubDialog(("start", "n2", []))):
            self.window._on_add_edge()
        self.assertEqual(self.window.draft["edges"]["start"], [{"condition": [], "to": "n2"}])

    def test_editing_an_edge_updates_its_condition(self):
        """Editing the selected edge replaces its condition."""
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._set_draft(graph_draft.add_edge(self.window.draft, "start", "n2", []))
        row_id = next(iter(self.window.edges_tree.get_children()))
        self.window.edges_tree.selection_set(row_id)
        canned = ("start", "n2", ["goal", "is", "not", None])
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._EdgeDialog", _StubDialog(canned)):
            self.window._on_edit_edge()
        self.assertEqual(self.window.draft["edges"]["start"][0]["condition"], ["goal", "is", "not", None])





    #===============#Knowledge #===============#

    def test_adding_a_knowledge_key(self):
        """Add Key declares the dialog's key, type, and value in the draft."""
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._KnowledgeDialog", _StubDialog(("battery", float, 1.0))):
            self.window._on_add_knowledge_key()
        self.assertEqual(self.window.draft["knowledge"]["battery"], {"type": float, "value": 1.0})

    def test_editing_a_knowledge_key_changes_its_value(self):
        """Editing the selected key replaces its default value."""
        self.window._set_draft(graph_draft.add_knowledge_key(self.window.draft, "battery", float, 1.0))
        self.window.knowledge_tree.selection_set("battery")
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._KnowledgeDialog", _StubDialog(("battery", float, 0.5))):
            self.window._on_edit_knowledge_key()
        self.assertEqual(self.window.draft["knowledge"]["battery"]["value"], 0.5)

    def test_editing_a_knowledge_key_can_rename_it_and_cascades_to_bindings(self):
        """Renaming a key through Edit moves the declaration and rewrites capability request bindings."""
        draft = graph_draft.add_knowledge_key(self.window.draft, "battery", float, 1.0)
        draft = graph_draft.add_capability(draft, "start", "nav", "move_to", {"tolerance": "battery"}, {})
        self.window._set_draft(draft)
        self.window.knowledge_tree.selection_set("battery")
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window._KnowledgeDialog", _StubDialog(("battery_level", float, 1.0))):
            self.window._on_edit_knowledge_key()
        self.assertNotIn("battery", self.window.draft["knowledge"])
        self.assertEqual(self.window.draft["knowledge"]["battery_level"], {"type": float, "value": 1.0})
        self.assertEqual(self.window.draft["nodes"]["start"]["capabilities"]["nav"]["inputs"]["tolerance"], "battery_level")





    #===============#Validate #===============#

    def _draft_binding_tolerance_to(self, key_declarations: dict) -> dict:
        """A draft whose move_to binds tolerance to the key 'tolerance', with the given knowledge declared."""
        draft = {"knowledge": key_declarations, "edges": {}, "start": "n1", "nodes": {"n1": {"capabilities":{"go": {
            "capability": "move_to", "inputs": {"target": "goal", "tolerance": "tolerance"}, "outputs": {}}}}}}
        return draft

    def test_validate_rejects_a_binding_to_an_undeclared_key(self):
        """Validate rejects a move_to bound to an undeclared 'tolerance', which would halt the mission on push."""
        self.window.target_platform_id.set("ugv1")
        self.window._set_draft(self._draft_binding_tolerance_to({"goal": {"type": Location, "value": Location(1.0, 2.0)}}))
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window.messagebox.showerror") as showerror:
            self.window._on_validate()
        showerror.assert_called_once()
        self.assertIn("undeclared knowledge key(s): ['tolerance']", self.window.console_text.get("1.0", tk.END))

    def test_validate_reports_a_wrong_typed_binding_for_the_target_platform(self):
        """Validate reports a binding whose key type doesn't match the target's capability field."""
        self.window.target_platform_id.set("ugv1")
        self.window._set_draft(self._draft_binding_tolerance_to({
            "goal": {"type": Location, "value": Location(1.0, 2.0)}, "tolerance": {"type": bool, "value": True}}))
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window.messagebox.showerror") as showerror:
            self.window._on_validate()
        showerror.assert_called_once()
        console = self.window.console_text.get("1.0", tk.END)
        self.assertIn("Validation failed for 'ugv1'", console)
        self.assertIn("expects float, but key 'tolerance' is declared bool", console)

    def test_validate_passes_a_draft_the_target_platform_can_bind(self):
        """Validate shows no error and logs success for a draft the target can bind."""
        self.window.target_platform_id.set("ugv1")
        self.window._set_draft(self._draft_binding_tolerance_to({
            "goal": {"type": Location, "value": Location(1.0, 2.0)}, "tolerance": {"type": float, "value": 1.0}}))
        with patch("mtofr.environments.anywhere.platforms.interface.mission_editor.window.messagebox.showerror") as showerror:
            self.window._on_validate()
        showerror.assert_not_called()
        self.assertIn("binds on 'ugv1'", self.window.console_text.get("1.0", tk.END))





    #===============#Push #===============#

    def test_push_writes_the_draft_to_the_target_platforms_mission_database(self):
        """Push stores the draft object as the target's own Mission entry."""
        # Privilege gate needs the target to already know "interface" outranks it
        # -- normally seeded by mesh sync, done directly here.
        self.target_backseater.platform_database.declare(
            "interface", PlatformRecord(privilege_level=0, status=PlatformStatus("idle"))
        )
        self.window.target_platform_id.set("ugv1")
        self.window._set_draft(graph_draft.add_node(self.window.draft, "n2"))
        self.window._on_push()
        self.assertIs(self.target_backseater.mission_database.get("ugv1"), self.window.draft)





    #===============#Draft-Source Tracking #===============#

    def test_new_blank_starts_with_no_draft_source(self):
        """A fresh window's draft has no source platform."""
        self.assertIsNone(self.window.draft_source_platform_id)

    def test_load_live_records_the_source_platform_and_logs_it_to_the_console(self):
        """Load Live records the target as the draft source and logs it."""
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.assertEqual(self.window.draft_source_platform_id, "ugv1")
        self.assertIn("ugv1", self.window.console_text.get("1.0", tk.END))

    def test_new_blank_after_load_live_clears_the_source(self):
        """New Blank clears the draft source set by Load Live."""
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.window._on_new_blank()
        self.assertIsNone(self.window.draft_source_platform_id)

    def test_pushing_to_the_draft_source_platform_logs_no_mismatch_warning(self):
        """Pushing back to the draft's own source platform logs no warning."""
        for backseater in (self.target_backseater, self.other_backseater):
            backseater.platform_database.declare(
                "interface", PlatformRecord(privilege_level=0, status=PlatformStatus("idle"))
            )
        self.window.target_platform_id.set("ugv1")
        self.window._on_load_live()
        self.window._on_push()
        self.assertNotIn("Warning", self.window.console_text.get("1.0", tk.END))

    def test_pushing_a_draft_loaded_from_a_different_platform_logs_a_mismatch_warning(self):
        """Pushing a draft to a platform other than its source logs a warning naming both."""
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





    #===============#Knowledge Tree Columns #===============#

    def test_knowledge_tree_shows_key_before_type_before_value(self):
        """A draft knowledge row's columns are key, type name, and value."""
        self.window._set_draft(graph_draft.add_knowledge_key(self.window.draft, "battery", float, 1.0))
        row = self.window.knowledge_tree.item("battery")
        self.assertEqual(row["values"], ["battery", "float", "1.0"])





    #===============#Graph Tab Draft/Live Preview Toggle #===============#

    def test_draft_mode_note_mentions_editing(self):
        """In draft preview mode the note mentions the draft."""
        self.window.preview_mode.set("draft")
        self.window._on_preview_mode_changed()
        self.assertIn("draft", self.window.preview_mode_note.cget("text").lower())

    def test_live_mode_note_mentions_the_target_platform(self):
        """In live preview mode the note names the target platform."""
        self.window.target_platform_id.set("ugv1")
        self.window.preview_mode.set("live")
        self.window._on_preview_mode_changed()
        self.assertIn("ugv1", self.window.preview_mode_note.cget("text"))


if __name__ == "__main__":
    unittest.main()
