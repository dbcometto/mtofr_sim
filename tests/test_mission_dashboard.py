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

from mtofr.database import Location
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.environments.world import World
from mtofr.platform.platform import Platform

if TK_AVAILABLE:
    from mtofr.viz.dashboard import MissionDashboard, MISSION_OVERVIEW_ID
    from mtofr.viz.mission_graph_view import GRAPH_PLOT_BACKGROUND
    import matplotlib.colors


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboard(unittest.TestCase):
    def setUp(self):
        """Build a one-UGV world with a move_to mission and a dashboard showing that platform."""
        mission_graph = {
            "knowledge": {
                "goal": {"type": Location, "value": Location(2.0, 0.0)},
                "tolerance": {"type": float, "value": 0.5},
            },
            "nodes": {"n1": {"capabilities": {
                "nav": {"capability": "move_to", "inputs": {"target": "goal", "tolerance": "tolerance"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        platform = Platform(bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_graph))
        self.frontseater = platform.frontseater
        self.world = World(GroundPlaneEnv(), platforms={"ugv1": platform})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())
        # These tests exercise the single-platform mission-graph/capability view,
        # so select a specific platform rather than relying on the default
        # (Mission Overview, covered separately in TestMissionDashboardDefaults).
        self.dashboard.selected_id.set("ugv1")
        self.dashboard._refresh()

    def tearDown(self):
        """Close the dashboard and shut down the UGV's MPC worker."""
        self.dashboard._on_close()
        self.frontseater.shutdown()

    def test_update_after_a_sim_tick_does_not_raise(self):
        """update() succeeds after one world step."""
        self.world.step(0.1)
        self.dashboard.update()

    def test_capability_tree_reflects_active_capability_request(self):
        """After a tick, the capability tree lists the active node's capability request."""
        self.world.step(0.1)
        self.dashboard.update()
        self.assertIn("nav", self.dashboard.capability_tree.get_children())

    def test_capability_tree_shows_an_undeclared_binding_instead_of_crashing(self):
        """A binding to an undeclared key is shown as such in the capability tree."""
        backseater = self.world.platforms["ugv1"].backseater
        status = {"overall_status": "halted", "capabilities": {
            "nav": {"capability": "move_to", "status": "failed", "inputs": {"tolerance": "missing_key"}}}}
        self.dashboard._refresh_capability_tree(backseater, status)
        self.assertIn("undeclared key 'missing_key'", self.dashboard.capability_tree.item("nav", "values")[2])

    def test_knowledge_tree_lists_every_knowledge_entry(self):
        """The knowledge tree has a row for each declared key."""
        self.dashboard.update()
        self.assertIn("goal", self.dashboard.knowledge_tree.get_children())

    def test_knowledge_tree_splits_name_type_and_value_into_columns_in_that_order(self):
        """Each knowledge row's columns are name, type name, and described value."""
        self.dashboard.update()
        name, type_name, value = self.dashboard.knowledge_tree.item("goal", "values")
        self.assertEqual(name, "goal")
        self.assertEqual(type_name, "Location")
        self.assertEqual(value, "x=2.0, y=0.0")

    def test_is_open_becomes_false_after_close(self):
        """is_open() is False once the dashboard is closed."""
        self.dashboard._on_close()
        self.assertFalse(self.dashboard.is_open())

    def test_starts_unpaused(self):
        """A new dashboard is not paused."""
        self.assertFalse(self.dashboard.is_paused())

    def test_toggle_pause_flips_state_and_button_text(self):
        """Toggling pause flips is_paused() and swaps the button's text and style each time."""
        self.dashboard._toggle_pause()
        self.assertTrue(self.dashboard.is_paused())
        self.assertIn("Play", self.dashboard.pause_button.cget("text"))
        self.assertEqual(self.dashboard.pause_button.cget("style"), "Paused.TButton")
        self.dashboard._toggle_pause()
        self.assertFalse(self.dashboard.is_paused())
        self.assertIn("Pause", self.dashboard.pause_button.cget("text"))
        self.assertEqual(self.dashboard.pause_button.cget("style"), "TButton")

    def test_selecting_capabilities_panel_shows_capabilities_frame(self):
        """Choosing "Capabilities" packs the capabilities frame in place of the knowledge frame."""
        self.dashboard.side_panel_choice.set("Capabilities")
        self.dashboard._show_selected_side_panel()
        packed = self.dashboard.side_panel_container.pack_slaves()
        self.assertIn(self.dashboard.capabilities_frame, packed)
        self.assertNotIn(self.dashboard.knowledge_frame, packed)

    def test_switching_side_panels_does_not_resize_the_container(self):
        """Switching side panels keeps the container's width and height."""
        self.dashboard.root.update_idletasks()
        width_before = self.dashboard.side_panel_container.winfo_width()
        height_before = self.dashboard.side_panel_container.winfo_height()
        self.dashboard.side_panel_choice.set("Capabilities")
        self.dashboard._show_selected_side_panel()
        self.dashboard.root.update_idletasks()
        self.assertEqual(self.dashboard.side_panel_container.winfo_width(), width_before)
        self.assertEqual(self.dashboard.side_panel_container.winfo_height(), height_before)

    def test_environment_plot_has_a_white_background(self):
        """The environment Axes face color is white."""
        self.dashboard.update()
        self.assertEqual(self.dashboard.environment_ax.get_facecolor(), (1.0, 1.0, 1.0, 1.0))

    def test_mission_graph_plot_has_a_mid_gray_background(self):
        """The mission graph Axes face color is GRAPH_PLOT_BACKGROUND."""
        self.dashboard.update()
        expected = matplotlib.colors.to_rgba(GRAPH_PLOT_BACKGROUND)
        self.assertEqual(self.dashboard.graph_ax.get_facecolor(), expected)

    def test_graph_hover_over_active_node_sets_tooltip_text(self):
        """Hovering on a graph node makes the tooltip visible."""
        self.dashboard.update()
        node_position = self.dashboard.mission_graph_viewer._nodes[0]["position"]
        display_xy = self.dashboard.mission_graph_viewer._to_display(node_position)
        self.dashboard._last_graph_hover_xy = display_xy
        self.dashboard._apply_graph_hover()
        self.assertTrue(self.dashboard._graph_tooltip.get_visible())

    def test_graph_hover_away_from_anything_hides_tooltip(self):
        """Hovering far from every node and edge hides the tooltip."""
        self.dashboard.update()
        self.dashboard._last_graph_hover_xy = (1000.0, 1000.0)
        self.dashboard._apply_graph_hover()
        self.assertFalse(self.dashboard._graph_tooltip.get_visible())

    def test_dropdown_includes_mission_overview(self):
        """The platform dropdown offers the Mission Overview entry."""
        self.assertIn(MISSION_OVERVIEW_ID, self.dashboard.platform_dropdown.cget("values"))

    def test_edge_labels_checkbox_and_back_button_are_shown_for_a_selected_platform(self):
        """With a platform selected, the graph title shows the edge-label toggle and back button."""
        self.dashboard.update()
        self.assertIn(self.dashboard.edge_labels_checkbox, self.dashboard.graph_title.pack_slaves())
        self.assertIn(self.dashboard.back_to_overview_button, self.dashboard.graph_title.pack_slaves())

    def test_back_button_returns_to_mission_overview(self):
        """Deselecting the platform returns the dropdown to Mission Overview."""
        self.dashboard.update()
        self.dashboard._deselect_platform()
        self.assertEqual(self.dashboard.selected_id.get(), MISSION_OVERVIEW_ID)


class _FakeMouseEvent:
    def __init__(self, x, y):
        """Carry only the display-space x/y a click handler reads."""
        self.x = x
        self.y = y


class _FakeAxesMouseEvent:
    """A fake matplotlib MouseEvent carrying the data-space fields (inaxes/xdata/
    ydata/step/button) the environment pan/zoom handlers read, in addition to
    display-space x/y."""
    def __init__(self, ax, x, y, inaxes=True, step=0, button=1):
        """Fill the event fields, deriving xdata/ydata from display x/y through the Axes transform."""
        self.x = x
        self.y = y
        self.inaxes = ax if inaxes else None
        xdata, ydata = ax.transData.inverted().transform((x, y))
        self.xdata = xdata
        self.ydata = ydata
        self.step = step
        self.button = button


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboardEnvironmentPanZoom(unittest.TestCase):
    """Scroll-to-zoom and left-drag-to-pan on the environment plot, working
    directly without needing the matplotlib toolbar's own pan/zoom tools toggled on."""
    def setUp(self):
        """Build a one-UGV world and a dashboard with its environment view limits established."""
        platform = Platform(bicycle_ugv("ugv1", 0.0, 0.0))
        self.frontseater = platform.frontseater
        self.world = World(GroundPlaneEnv(), platforms={"ugv1": platform})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())
        self.dashboard.update()   # establishes the environment_ax's initial view limits
        self.ax = self.dashboard.environment_ax

    def tearDown(self):
        """Close the dashboard and shut down the UGV's MPC worker."""
        self.dashboard._on_close()
        self.frontseater.shutdown()

    def test_scroll_up_zooms_in_around_the_cursor(self):
        """Scrolling up shrinks both axis spans."""
        xlim_before, ylim_before = self.ax.get_xlim(), self.ax.get_ylim()
        center = self.ax.transData.transform((0, 0))
        event = _FakeAxesMouseEvent(self.ax, center[0], center[1], step=1)

        self.dashboard._on_environment_scroll(event)

        xlim_after, ylim_after = self.ax.get_xlim(), self.ax.get_ylim()
        self.assertLess(xlim_after[1] - xlim_after[0], xlim_before[1] - xlim_before[0])
        self.assertLess(ylim_after[1] - ylim_after[0], ylim_before[1] - ylim_before[0])

    def test_scroll_down_zooms_out(self):
        """Scrolling down widens the x span."""
        xlim_before = self.ax.get_xlim()
        center = self.ax.transData.transform((0, 0))
        event = _FakeAxesMouseEvent(self.ax, center[0], center[1], step=-1)

        self.dashboard._on_environment_scroll(event)

        xlim_after = self.ax.get_xlim()
        self.assertGreater(xlim_after[1] - xlim_after[0], xlim_before[1] - xlim_before[0])

    def test_scroll_outside_axes_does_not_raise_or_change_limits(self):
        """Scrolling outside the Axes leaves the limits unchanged."""
        xlim_before = self.ax.get_xlim()
        event = _FakeAxesMouseEvent(self.ax, 5, 5, inaxes=False, step=1)

        self.dashboard._on_environment_scroll(event)

        self.assertEqual(self.ax.get_xlim(), xlim_before)

    def test_left_drag_pans_the_view(self):
        """A horizontal left-drag moves the x limits but not the y limits."""
        xlim_before, ylim_before = self.ax.get_xlim(), self.ax.get_ylim()

        start = _FakeAxesMouseEvent(self.ax, 100, 100, button=1)
        self.dashboard._on_environment_pan_start(start)
        moved = _FakeAxesMouseEvent(self.ax, 120, 100, button=1)
        self.dashboard._on_environment_pan_move(moved)

        xlim_after, ylim_after = self.ax.get_xlim(), self.ax.get_ylim()
        self.assertNotEqual(xlim_after, xlim_before)
        # A purely horizontal drag should not move the vertical extent.
        self.assertAlmostEqual(ylim_after[0], ylim_before[0])
        self.assertAlmostEqual(ylim_after[1], ylim_before[1])

    def test_pan_end_stops_further_dragging_from_moving_the_view(self):
        """Mouse motion after the pan ends leaves the view unchanged."""
        start = _FakeAxesMouseEvent(self.ax, 100, 100, button=1)
        self.dashboard._on_environment_pan_start(start)
        self.dashboard._on_environment_pan_end(_FakeAxesMouseEvent(self.ax, 100, 100))

        xlim_before = self.ax.get_xlim()
        moved = _FakeAxesMouseEvent(self.ax, 150, 100, button=1)
        self.dashboard._on_environment_pan_move(moved)

        self.assertEqual(self.ax.get_xlim(), xlim_before)

    def test_right_click_drag_does_not_start_a_pan(self):
        """A right-button drag leaves the view unchanged."""
        start = _FakeAxesMouseEvent(self.ax, 100, 100, button=3)
        self.dashboard._on_environment_pan_start(start)

        xlim_before = self.ax.get_xlim()
        moved = _FakeAxesMouseEvent(self.ax, 150, 100, button=3)
        self.dashboard._on_environment_pan_move(moved)

        self.assertEqual(self.ax.get_xlim(), xlim_before)


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestMissionDashboardDefaults(unittest.TestCase):
    """A dashboard's defaults on first construction, before anything selects
    a specific platform or side panel."""
    def setUp(self):
        """Build a one-UGV world and a dashboard left at its defaults."""
        platform = Platform(bicycle_ugv("ugv1", 0.0, 0.0))
        self.frontseater = platform.frontseater
        self.world = World(GroundPlaneEnv(), platforms={"ugv1": platform})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())

    def tearDown(self):
        """Close the dashboard and shut down the UGV's MPC worker."""
        self.dashboard._on_close()
        self.frontseater.shutdown()

    def test_defaults_to_mission_overview(self):
        """The dropdown starts on Mission Overview."""
        self.assertEqual(self.dashboard.selected_id.get(), MISSION_OVERVIEW_ID)

    def test_defaults_to_the_knowledge_side_panel(self):
        """The side panel starts on Knowledge, with the capabilities frame unpacked."""
        self.assertEqual(self.dashboard.side_panel_choice.get(), "Knowledge")
        packed = self.dashboard.side_panel_container.pack_slaves()
        self.assertIn(self.dashboard.knowledge_frame, packed)
        self.assertNotIn(self.dashboard.capabilities_frame, packed)

    def test_edge_labels_checkbox_and_back_button_are_hidden_in_overview_mode(self):
        """In overview mode the graph title hides the edge-label toggle and back button."""
        self.dashboard.update()
        self.assertNotIn(self.dashboard.edge_labels_checkbox, self.dashboard.graph_title.pack_slaves())
        self.assertNotIn(self.dashboard.back_to_overview_button, self.dashboard.graph_title.pack_slaves())

    def test_switching_between_overview_and_a_platform_does_not_resize_the_window(self):
        """Selecting a platform and returning to the overview keeps the window size."""
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
    active capability requests) in place of a single platform's mission graph, and an empty
    knowledge panel in place of a single platform's own Knowledge (there is no
    canonical cross-platform store to show)."""
    def setUp(self):
        """Build a one-UGV world with a move_to mission and a dashboard on Mission Overview."""
        mission_graph = {
            "knowledge": {"ugv1/arrived": {"type": bool, "value": False}},
            "nodes": {"n1": {"capabilities": {
                "nav": {"capability": "move_to", "inputs": {}, "outputs": {}},
            }}},
            "edges": {},
            "start": "n1",
        }
        platform = Platform(bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_graph))
        self.frontseater = platform.frontseater
        self.world = World(GroundPlaneEnv(), platforms={"ugv1": platform})
        self.dashboard = MissionDashboard(self.world, PlanePlotter())
        self.dashboard.selected_id.set(MISSION_OVERVIEW_ID)

    def tearDown(self):
        """Close the dashboard and shut down the UGV's MPC worker."""
        self.dashboard._on_close()
        self.frontseater.shutdown()

    def test_selecting_mission_overview_does_not_raise(self):
        """update() succeeds in overview mode."""
        self.dashboard.update()

    def test_capability_tree_is_cleared_in_overview_mode(self):
        """The capability tree is empty in overview mode."""
        self.dashboard.update()
        self.assertEqual(self.capability_tree_children(), ())

    def test_knowledge_tree_is_empty_in_overview_mode(self):
        """The knowledge tree stays empty in overview mode, even after a tick."""
        self.world.step(0.1)
        self.dashboard.update()
        self.assertEqual(self.dashboard.knowledge_tree.get_children(), ())

    def test_hovering_a_platform_row_shows_a_titled_tooltip(self):
        """Hovering on a platform row shows a tooltip titled with that platform."""
        self.dashboard.update()
        row_position = self.dashboard.platform_overview_viewer._rows[0]["position"]
        display_xy = self.dashboard.platform_overview_viewer._to_display(row_position)
        self.dashboard._last_graph_hover_xy = display_xy
        self.dashboard._apply_graph_hover()
        self.assertTrue(self.dashboard._graph_tooltip.get_visible())
        self.assertIn("Platform: ugv1", self.dashboard._graph_tooltip.get_text())

    def test_clicking_a_platform_row_selects_that_platform(self):
        """Clicking a platform row selects that platform in the dropdown."""
        self.dashboard.update()
        row_position = self.dashboard.platform_overview_viewer._rows[0]["position"]
        display_x, display_y = self.dashboard.platform_overview_viewer._to_display(row_position)
        self.dashboard._on_graph_click(_FakeMouseEvent(display_x, display_y))
        self.assertEqual(self.dashboard.selected_id.get(), "ugv1")

    def test_clicking_away_from_any_row_does_not_change_selection(self):
        """Clicking far from every row keeps Mission Overview selected."""
        self.dashboard.update()
        self.dashboard._on_graph_click(_FakeMouseEvent(10000.0, 10000.0))
        self.assertEqual(self.dashboard.selected_id.get(), MISSION_OVERVIEW_ID)

    def capability_tree_children(self):
        """Return the capability tree's current row ids."""
        return self.dashboard.capability_tree.get_children()


if __name__ == "__main__":
    unittest.main()
