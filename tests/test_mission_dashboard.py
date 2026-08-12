"""Smoke test for MissionDashboard: constructs the full Tkinter window (dropdown,
environment view, mission graph, capability/knowledge panel, pause button) against a
real World/Backseater and ticks it once. Skips if this environment cannot open a Tk
window at all (e.g. a headless CI runner with no display)."""
import tkinter as tk
import unittest

try:
    _probe = tk.Tk()
    _probe.destroy()
    TK_AVAILABLE = True
except tk.TclError:
    TK_AVAILABLE = False

from mtofr.backseater.backseater import Backseater
from mtofr.knowledge.knowledge import Knowledge, Location
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.world.world import World

if TK_AVAILABLE:
    from mtofr.viz.dashboard import MissionDashboard, GRAPH_PLOT_BACKGROUND
    import matplotlib.colors


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboard(unittest.TestCase):
    def setUp(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        knowledge = Knowledge()
        knowledge.add("goal", Location(2.0, 0.0))
        mission_graph = {
            "nodes": {"n1": {"primitives": {"nav": {"type": "move_to", "params": {"target": "goal"}}}}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=frontseater, knowledge=knowledge, mission_graph=mission_graph)
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": backseater})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())

    def tearDown(self):
        self.dashboard._on_close()

    def test_dropdown_defaults_to_first_platform(self):
        self.assertEqual(self.dashboard.selected_id.get(), "ugv1")

    def test_update_after_a_sim_tick_does_not_raise(self):
        self.world.step(0.1)
        self.dashboard.update()

    def test_capability_tree_reflects_active_primitive(self):
        self.world.step(0.1)
        self.dashboard.update()
        self.assertIn("nav", self.dashboard.capability_tree.get_children())

    def test_knowledge_tree_lists_every_knowledge_entry(self):
        self.dashboard.update()
        self.assertIn("goal", self.dashboard.knowledge_tree.get_children())

    def test_knowledge_tree_splits_type_name_and_value_into_columns(self):
        self.dashboard.update()
        type_name, name, value = self.dashboard.knowledge_tree.item("goal", "values")
        self.assertEqual(type_name, "Location")
        self.assertEqual(name, "goal")
        self.assertEqual(value, "x=2.0, y=0.0")

    def test_is_open_becomes_false_after_close(self):
        self.dashboard._on_close()
        self.assertFalse(self.dashboard.is_open())

    def test_starts_unpaused(self):
        self.assertFalse(self.dashboard.is_paused())

    def test_toggle_pause_flips_state_and_button_text(self):
        self.dashboard._toggle_pause()
        self.assertTrue(self.dashboard.is_paused())
        self.assertIn("Play", self.dashboard.pause_button.cget("text"))
        self.assertEqual(self.dashboard.pause_button.cget("style"), "Paused.TButton")
        self.dashboard._toggle_pause()
        self.assertFalse(self.dashboard.is_paused())
        self.assertIn("Pause", self.dashboard.pause_button.cget("text"))
        self.assertEqual(self.dashboard.pause_button.cget("style"), "TButton")

    def test_side_panel_defaults_to_capabilities(self):
        self.assertEqual(self.dashboard.side_panel_choice.get(), "Capabilities")
        packed = self.dashboard.side_panel_container.pack_slaves()
        self.assertIn(self.dashboard.capabilities_frame, packed)
        self.assertNotIn(self.dashboard.knowledge_frame, packed)

    def test_selecting_knowledge_panel_shows_knowledge_frame(self):
        self.dashboard.side_panel_choice.set("Knowledge")
        self.dashboard._show_selected_side_panel()
        packed = self.dashboard.side_panel_container.pack_slaves()
        self.assertIn(self.dashboard.knowledge_frame, packed)
        self.assertNotIn(self.dashboard.capabilities_frame, packed)

    def test_switching_side_panels_does_not_resize_the_container(self):
        self.dashboard.root.update_idletasks()
        width_before = self.dashboard.side_panel_container.winfo_width()
        height_before = self.dashboard.side_panel_container.winfo_height()
        self.dashboard.side_panel_choice.set("Knowledge")
        self.dashboard._show_selected_side_panel()
        self.dashboard.root.update_idletasks()
        self.assertEqual(self.dashboard.side_panel_container.winfo_width(), width_before)
        self.assertEqual(self.dashboard.side_panel_container.winfo_height(), height_before)

    def test_environment_plot_has_a_white_background(self):
        self.dashboard.update()
        self.assertEqual(self.dashboard.environment_ax.get_facecolor(), (1.0, 1.0, 1.0, 1.0))

    def test_mission_graph_plot_has_a_mid_gray_background(self):
        self.dashboard.update()
        expected = matplotlib.colors.to_rgba(GRAPH_PLOT_BACKGROUND)
        self.assertEqual(self.dashboard.graph_ax.get_facecolor(), expected)

    def test_graph_hover_over_active_node_sets_tooltip_text(self):
        self.dashboard.update()
        node_position = self.dashboard.mission_graph_viewer._nodes[0]["position"]
        display_xy = self.dashboard.mission_graph_viewer._to_display(node_position)
        self.dashboard._last_graph_hover_xy = display_xy
        self.dashboard._apply_graph_hover()
        self.assertTrue(self.dashboard._graph_tooltip.get_visible())

    def test_graph_hover_away_from_anything_hides_tooltip(self):
        self.dashboard.update()
        self.dashboard._last_graph_hover_xy = (1000.0, 1000.0)
        self.dashboard._apply_graph_hover()
        self.assertFalse(self.dashboard._graph_tooltip.get_visible())


if __name__ == "__main__":
    unittest.main()
