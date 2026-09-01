"""Tests for PlanePlotter as an EnvironmentViewer: renders onto a given Axes without
owning a Figure/window, and visually distinguishes the selected platform."""
import unittest
import matplotlib
matplotlib.use("Agg")   # headless backend: no window/display needed to draw
import matplotlib.pyplot as plt
import numpy as np

from mtofr.viz.base import EnvironmentViewer
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.world.base import WorldState
from mtofr.maps.ground_map import GroundMap, TraversabilityType, RegionType


class TestPlanePlotter(unittest.TestCase):
    def setUp(self):
        self.fig, self.ax = plt.subplots()
        self.plotter = PlanePlotter()
        self.states = {
            "ugv1": WorldState(x=1.0, y=2.0, theta=0.0),
            "ugv2": WorldState(x=-3.0, y=4.0, theta=1.5),
        }

    def tearDown(self):
        plt.close(self.fig)

    def test_is_an_environment_viewer(self):
        self.assertIsInstance(self.plotter, EnvironmentViewer)

    def test_configure_ax_sets_limits(self):
        self.plotter.configure_ax(self.ax)
        self.assertEqual(self.ax.get_xlim(), self.plotter.xlim)
        self.assertEqual(self.ax.get_ylim(), self.plotter.ylim)

    def test_render_draws_a_marker_per_platform(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1")
        self.assertEqual(set(self.plotter.markers), {"ugv1", "ugv2"})

    def test_render_highlights_selected_platform(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1")
        selected_size = self.plotter.markers["ugv1"].get_markersize()
        unselected_size = self.plotter.markers["ugv2"].get_markersize()
        self.assertGreater(selected_size, unselected_size)

    def test_render_with_no_selection_does_not_raise(self):
        self.plotter.render(self.ax, self.states, selected_id=None)

    def test_render_with_empty_states_does_not_raise(self):
        self.plotter.render(self.ax, {}, selected_id=None)

    def test_heading_marker_stays_a_fixed_pixel_distance_from_the_dot_across_zoom(self):
        """The heading marker is offset from the dot by a fixed number of points, not
        a fixed number of data units -- so its on-screen (pixel) distance from the dot
        should be the same whether zoomed in or out, unlike the old data-space arrow."""
        def pixel_distance():
            self.plotter.render(self.ax, self.states, selected_id="ugv1")
            dot_display = self.ax.transData.transform(self.plotter.markers["ugv1"].get_data())
            heading_display = self.ax.transData.transform(self.plotter.arrows["ugv1"].get_data())
            return float(np.linalg.norm(np.array(heading_display) - np.array(dot_display)))

        self.plotter.configure_ax(self.ax)
        zoomed_out_distance = pixel_distance()

        self.ax.set_xlim(-2, 2)
        self.ax.set_ylim(-2, 2)
        zoomed_in_distance = pixel_distance()

        self.assertAlmostEqual(zoomed_out_distance, zoomed_in_distance, places=3)

    def test_background_color_defaults_to_white_with_no_map(self):
        self.assertEqual(self.plotter.background_color, "white")


def _tiny_ground_map() -> GroundMap:
    image = np.zeros((4, 4, 3), dtype=float)
    return GroundMap(
        name="tiny", meters_per_pixel=1.0, cosmetic_image=image, traversability_image=image,
        traversability_lookup={(0, 0, 0): TraversabilityType(name="clear", blocking=False, speed_multiplier=1.0)},
        regions_image=image,
        regions_lookup={(0, 0, 0): RegionType(name="A", center_x=2.0, center_y=2.0)},
    )


class TestPlanePlotterWithGroundMap(unittest.TestCase):
    def setUp(self):
        self.fig, self.ax = plt.subplots()
        self.ground_map = _tiny_ground_map()
        self.plotter = PlanePlotter(ground_map=self.ground_map)
        self.states = {"ugv1": WorldState(x=0.0, y=0.0, theta=0.0)}

    def tearDown(self):
        plt.close(self.fig)

    def test_background_color_marks_off_map_area_when_a_map_is_given(self):
        self.assertNotEqual(self.plotter.background_color, "white")

    def test_configure_ax_uses_map_extent_as_limits(self):
        self.plotter.configure_ax(self.ax)
        self.assertEqual(self.ax.get_xlim(), (-2.0, 2.0))
        self.assertEqual(self.ax.get_ylim(), (-2.0, 2.0))

    def test_render_with_layers_hidden_does_not_raise(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1")

    def test_render_with_traversability_shown_does_not_raise(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1", show_traversability=True)

    def test_render_with_regions_shown_does_not_raise(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1", show_regions=True)

    def test_legend_includes_traversability_swatch_when_shown(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1", show_traversability=True)
        legend_labels = {text.get_text() for text in self.ax.get_legend().get_texts()}
        self.assertIn("clear", legend_labels)
        self.assertIn("ugv1", legend_labels)

    def test_legend_omits_traversability_swatch_when_hidden(self):
        self.plotter.render(self.ax, self.states, selected_id="ugv1", show_traversability=False)
        legend_labels = {text.get_text() for text in self.ax.get_legend().get_texts()}
        self.assertNotIn("clear", legend_labels)


if __name__ == "__main__":
    unittest.main()
