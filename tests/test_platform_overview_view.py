"""Tests for PlatformOverviewViewer's rendering and hover/click hit-testing."""
import unittest
import matplotlib
matplotlib.use("Agg")   # headless backend: no window/display needed to draw
import matplotlib.pyplot as plt

from mtofr.viz.platform_overview_view import PlatformOverviewViewer


class _FakeBackseater:
    def __init__(self, active_node_id, primitives=None):
        self._status = {
            "active_node_id": active_node_id,
            "blocked": False,
            "primitives": primitives or {},
        }

    def status(self):
        return self._status


class TestPlatformOverviewViewer(unittest.TestCase):
    def setUp(self):
        self.fig, self.ax = plt.subplots()
        self.viewer = PlatformOverviewViewer()

    def tearDown(self):
        plt.close(self.fig)

    def test_render_records_one_row_per_platform(self):
        backseaters = {"ugv1": _FakeBackseater("n1"), "ugv2": _FakeBackseater("n2")}
        self.viewer.render(self.ax, backseaters)
        self.assertEqual(len(self.viewer._rows), 2)

    def test_render_with_no_platforms_does_not_raise(self):
        self.viewer.render(self.ax, {})
        self.assertEqual(self.viewer._rows, [])

    def test_find_platform_label_at_matches_near_the_row(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater("n1")})
        display_x, display_y = self.viewer._to_display(self.viewer._rows[0]["position"])
        label = self.viewer.find_platform_label_at(display_x, display_y)
        self.assertIn("Platform: ugv1", label)

    def test_find_platform_label_at_returns_none_far_from_any_row(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater("n1")})
        self.assertIsNone(self.viewer.find_platform_label_at(10000.0, 10000.0))

    def test_find_platform_id_at_matches_near_the_row(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater("n1"), "ugv2": _FakeBackseater("n2")})
        display_x, display_y = self.viewer._to_display(self.viewer._rows[1]["position"])
        self.assertEqual(self.viewer.find_platform_id_at(display_x, display_y), "ugv2")

    def test_find_platform_id_at_returns_none_far_from_any_row(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater("n1")})
        self.assertIsNone(self.viewer.find_platform_id_at(10000.0, 10000.0))

    def test_render_draws_a_box_marker_per_platform(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater("n1")})
        self.assertEqual(len(self.ax.collections), 1)

    def test_active_node_is_always_shown_inline_not_just_on_hover(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater("return_to_start")})
        inline_texts = [text.get_text() for text in self.ax.texts]
        self.assertTrue(any("return_to_start" in text for text in inline_texts))

    def test_inline_label_shows_none_placeholder_when_no_active_node(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater(None)})
        inline_texts = [text.get_text() for text in self.ax.texts]
        self.assertTrue(any("(none)" in text for text in inline_texts))

    def test_hover_label_includes_active_primitives(self):
        self.viewer.render(self.ax, {"ugv1": _FakeBackseater(
            "n1", primitives={"nav": {"capability": "move_to", "status": "in_progress", "inputs": {}}}
        )})
        display_x, display_y = self.viewer._to_display(self.viewer._rows[0]["position"])
        label = self.viewer.find_platform_label_at(display_x, display_y)
        self.assertIn("move_to", label)
        self.assertIn("in_progress", label)


if __name__ == "__main__":
    unittest.main()