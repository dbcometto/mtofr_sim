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
from mtofr.relay.relay import Relay
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.world.world import World

if TK_AVAILABLE:
    from mtofr.viz.dashboard import MissionDashboard, GRAPH_PLOT_BACKGROUND, MISSION_OVERVIEW_ID
    import matplotlib.colors


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboard(unittest.TestCase):
    def setUp(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        knowledge = Knowledge()
        mission_graph = {
            "knowledge": {
                "goal": {"type": Location, "value": Location(2.0, 0.0)},
                "tolerance": {"type": float, "value": 0.5},
            },
            "nodes": {"n1": {"primitives": {
                "nav": {"capability": "move_to", "inputs": {"target": "goal", "tolerance": "tolerance"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=frontseater, knowledge=knowledge, mission_graph=mission_graph)
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": backseater})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())
        # These tests exercise the single-platform mission-graph/capability view,
        # so select a specific platform rather than relying on the default
        # (Mission Overview, covered separately in TestMissionDashboardDefaults).
        self.dashboard.selected_id.set("ugv1")
        self.dashboard._refresh()

    def tearDown(self):
        self.dashboard._on_close()

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

    def test_knowledge_tree_splits_name_type_and_value_into_columns_in_that_order(self):
        self.dashboard.update()
        name, type_name, value = self.dashboard.knowledge_tree.item("goal", "values")
        self.assertEqual(name, "goal")
        self.assertEqual(type_name, "Location")
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

    def test_selecting_capabilities_panel_shows_capabilities_frame(self):
        self.dashboard.side_panel_choice.set("Capabilities")
        self.dashboard._show_selected_side_panel()
        packed = self.dashboard.side_panel_container.pack_slaves()
        self.assertIn(self.dashboard.capabilities_frame, packed)
        self.assertNotIn(self.dashboard.knowledge_frame, packed)

    def test_switching_side_panels_does_not_resize_the_container(self):
        self.dashboard.root.update_idletasks()
        width_before = self.dashboard.side_panel_container.winfo_width()
        height_before = self.dashboard.side_panel_container.winfo_height()
        self.dashboard.side_panel_choice.set("Capabilities")
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

    def test_dropdown_includes_mission_overview(self):
        self.assertIn(MISSION_OVERVIEW_ID, self.dashboard.platform_dropdown.cget("values"))

    def test_edge_labels_checkbox_and_back_button_are_shown_for_a_selected_platform(self):
        self.dashboard.update()
        self.assertIn(self.dashboard.edge_labels_checkbox, self.dashboard.graph_title.pack_slaves())
        self.assertIn(self.dashboard.back_to_overview_button, self.dashboard.graph_title.pack_slaves())

    def test_back_button_returns_to_mission_overview(self):
        self.dashboard.update()
        self.dashboard._deselect_platform()
        self.assertEqual(self.dashboard.selected_id.get(), MISSION_OVERVIEW_ID)


class _FakeMouseEvent:
    def __init__(self, x, y):
        self.x = x
        self.y = y


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboardDefaults(unittest.TestCase):
    """A dashboard's defaults on first construction, before anything selects
    a specific platform or side panel."""
    def setUp(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        backseater = Backseater(frontseater=frontseater, knowledge=Knowledge(), platform_id="ugv1")
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": backseater})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())

    def tearDown(self):
        self.dashboard._on_close()

    def test_defaults_to_mission_overview(self):
        self.assertEqual(self.dashboard.selected_id.get(), MISSION_OVERVIEW_ID)

    def test_defaults_to_the_knowledge_side_panel(self):
        self.assertEqual(self.dashboard.side_panel_choice.get(), "Knowledge")
        packed = self.dashboard.side_panel_container.pack_slaves()
        self.assertIn(self.dashboard.knowledge_frame, packed)
        self.assertNotIn(self.dashboard.capabilities_frame, packed)

    def test_edge_labels_checkbox_and_back_button_are_hidden_in_overview_mode(self):
        self.dashboard.update()
        self.assertNotIn(self.dashboard.edge_labels_checkbox, self.dashboard.graph_title.pack_slaves())
        self.assertNotIn(self.dashboard.back_to_overview_button, self.dashboard.graph_title.pack_slaves())

    def test_switching_between_overview_and_a_platform_does_not_resize_the_window(self):
        self.dashboard.root.update_idletasks()
        size_before = (self.dashboard.root.winfo_width(), self.dashboard.root.winfo_height())

        self.dashboard.selected_id.set("ugv1")
        self.dashboard.update()
        self.dashboard.root.update_idletasks()
        size_with_platform_selected = (self.dashboard.root.winfo_width(), self.dashboard.root.winfo_height())

        self.dashboard.selected_id.set(MISSION_OVERVIEW_ID)
        self.dashboard.update()
        self.dashboard.root.update_idletasks()
        size_back_to_overview = (self.dashboard.root.winfo_width(), self.dashboard.root.winfo_height())

        self.assertEqual(size_before, size_with_platform_selected)
        self.assertEqual(size_before, size_back_to_overview)


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboardOverview(unittest.TestCase):
    """Covers the "Mission Overview" dropdown entry: a platform list (hover shows
    active primitives) in place of a single platform's mission graph, and Relay's
    canonical knowledge in place of a single platform's own Knowledge."""
    def setUp(self):
        knowledge = Knowledge()
        mission_graph = {
            "knowledge": {"ugv1/arrived": {"type": bool, "value": False}},
            "nodes": {"n1": {"primitives": {
                "nav": {"capability": "move_to", "inputs": {}, "outputs": {}},
            }}},
            "edges": {},
            "start": "n1",
        }
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        backseater = Backseater(frontseater=frontseater, knowledge=knowledge,
                                 mission_graph=mission_graph, platform_id="ugv1")
        self.relay = Relay()
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": backseater}, relay=self.relay)
        self.dashboard = MissionDashboard(self.world, PlanePlotter())
        self.dashboard.selected_id.set(MISSION_OVERVIEW_ID)

    def tearDown(self):
        self.dashboard._on_close()

    def test_selecting_mission_overview_does_not_raise(self):
        self.dashboard.update()

    def test_capability_tree_is_cleared_in_overview_mode(self):
        self.dashboard.update()
        self.assertEqual(self.capability_tree_children(), ())

    def test_knowledge_tree_reflects_relays_canonical_store(self):
        self.world.step(0.1)
        self.dashboard.update()
        self.assertIn("ugv1/arrived", self.dashboard.knowledge_tree.get_children())

    def test_hovering_a_platform_row_shows_a_titled_tooltip(self):
        self.dashboard.update()
        row_position = self.dashboard.platform_overview_viewer._rows[0]["position"]
        display_xy = self.dashboard.platform_overview_viewer._to_display(row_position)
        self.dashboard._last_graph_hover_xy = display_xy
        self.dashboard._apply_graph_hover()
        self.assertTrue(self.dashboard._graph_tooltip.get_visible())
        self.assertIn("Platform: ugv1", self.dashboard._graph_tooltip.get_text())

    def test_clicking_a_platform_row_selects_that_platform(self):
        self.dashboard.update()
        row_position = self.dashboard.platform_overview_viewer._rows[0]["position"]
        display_x, display_y = self.dashboard.platform_overview_viewer._to_display(row_position)
        self.dashboard._on_graph_click(_FakeMouseEvent(display_x, display_y))
        self.assertEqual(self.dashboard.selected_id.get(), "ugv1")

    def test_clicking_away_from_any_row_does_not_change_selection(self):
        self.dashboard.update()
        self.dashboard._on_graph_click(_FakeMouseEvent(10000.0, 10000.0))
        self.assertEqual(self.dashboard.selected_id.get(), MISSION_OVERVIEW_ID)

    def capability_tree_children(self):
        return self.dashboard.capability_tree.get_children()


if __name__ == "__main__":
    unittest.main()
