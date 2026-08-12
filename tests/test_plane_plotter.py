"""Tests for PlanePlotter as an EnvironmentViewer: renders onto a given Axes without
owning a Figure/window, and visually distinguishes the selected platform."""
import unittest
import matplotlib
matplotlib.use("Agg")   # headless backend: no window/display needed to draw
import matplotlib.pyplot as plt

from mtofr.viz.base import EnvironmentViewer
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.world.base import WorldState


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


if __name__ == "__main__":
    unittest.main()
