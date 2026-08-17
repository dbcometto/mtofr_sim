"""Tests for MissionGraphViewer's layout, rendering, and hover-lookup logic."""
import unittest
import matplotlib
matplotlib.use("Agg")   # headless backend: no window/display needed to draw
import matplotlib.pyplot as plt

from mtofr.viz.mission_graph_view import compute_graph_layout, MissionGraphViewer, NODE_HOVER_TOLERANCE_POINTS


LINEAR_GRAPH = {
    "nodes": {"n1": {"primitives": {}}, "n2": {"primitives": {}}},
    "edges": {
        "n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}],
        "n2": [{"condition": ["ugv1/arrived", "==", True], "to": "n1"}],
    },
    "start": "n1",
}

BRANCHING_GRAPH = {
    "nodes": {"n1": {"primitives": {}}, "n2": {"primitives": {}}, "n3": {"primitives": {}}},
    "edges": {
        "n1": [
            {"condition": ["ugv1/arrived", "==", True], "to": "n2"},
            {"condition": ["ugv1/arrived", "==", False], "to": "n3"},
        ],
    },
    "start": "n1",
}

CYCLE_GRAPH = {
    "nodes": {
        "n1": {"primitives": {"nav": {"capability": "move_to", "inputs": {}}}},
        "n2": {"primitives": {}},
        "n3": {"primitives": {}},
    },
    "edges": {
        "n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}],
        "n2": [{"condition": ["ugv1/arrived", "==", True], "to": "n3"}],
        "n3": [{"condition": ["ugv1/arrived", "==", True], "to": "n1"}],
    },
    "start": "n1",
}


class TestComputeGraphLayout(unittest.TestCase):
    def test_every_node_gets_a_unique_position(self):
        positions = compute_graph_layout(BRANCHING_GRAPH)
        self.assertEqual(len(positions), 3)
        self.assertEqual(len(set(positions.values())), 3)

    def test_a_three_node_cycle_is_not_laid_out_in_a_straight_line(self):
        # Regression test: this is the whole point of the force-directed layout —
        # a 3-node cycle should settle into a triangle, not a row, so its
        # cycle-closing edge is a short straight line rather than a long one that
        # has to curve around the middle node to stay visible/hoverable.
        positions = compute_graph_layout(CYCLE_GRAPH)
        (x1, y1), (x2, y2), (x3, y3) = positions["n1"], positions["n2"], positions["n3"]
        cross_product = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1)
        self.assertGreater(abs(cross_product), 0.1)

    def test_node_unreachable_from_start_still_gets_placed(self):
        graph = {
            "nodes": {"n1": {"primitives": {}}, "orphan": {"primitives": {}}},
            "edges": {},
            "start": "n1",
        }
        positions = compute_graph_layout(graph)
        self.assertIn("orphan", positions)

    def test_single_node_graph_places_it_at_the_origin(self):
        graph = {"nodes": {"only": {"primitives": {}}}, "edges": {}, "start": "only"}
        self.assertEqual(compute_graph_layout(graph), {"only": (0.0, 0.0)})

    def test_empty_graph_returns_empty_layout(self):
        self.assertEqual(compute_graph_layout({"nodes": {}, "edges": {}, "start": None}), {})

    def test_layout_is_deterministic(self):
        self.assertEqual(compute_graph_layout(CYCLE_GRAPH), compute_graph_layout(CYCLE_GRAPH))

    def test_repeated_calls_on_the_same_graph_return_a_cached_result(self):
        # Regression test: compute_graph_layout is expensive (150 O(n^2) iterations)
        # and is called on every render(), even though a mission graph is static
        # once built -- results must be cached by the graph object's identity.
        graph = {
            "nodes": {"n1": {"primitives": {}}, "n2": {"primitives": {}}},
            "edges": {"n1": [{"condition": [], "to": "n2"}]},
            "start": "n1",
        }
        first = compute_graph_layout(graph)
        second = compute_graph_layout(graph)
        self.assertIs(first, second)

    def test_cache_keeps_a_strong_reference_to_the_cached_graph(self):
        # Regression test: caching by id(mission_graph) alone (without keeping a
        # reference to the graph) risks a garbage-collected graph's id being
        # reused by an unrelated graph, silently returning a stale layout. The
        # cache must hold the graph itself alongside its result so that can't happen.
        from mtofr.viz.mission_graph_view import _layout_cache

        graph = {
            "nodes": {"n1": {"primitives": {}}, "n2": {"primitives": {}}},
            "edges": {},
            "start": "n1",
        }
        compute_graph_layout(graph)
        cached_graph, cached_result = _layout_cache[id(graph)]
        self.assertIs(cached_graph, graph)
        self.assertEqual(cached_result, compute_graph_layout(graph))


class TestMissionGraphViewerRender(unittest.TestCase):
    def setUp(self):
        self.fig, self.ax = plt.subplots()
        self.viewer = MissionGraphViewer()

    def tearDown(self):
        plt.close(self.fig)

    def test_render_does_not_raise_on_branching_graph(self):
        self.viewer.render(self.ax, BRANCHING_GRAPH, active_node_id="n1")

    def test_render_records_one_edge_entry_per_graph_edge(self):
        self.viewer.render(self.ax, BRANCHING_GRAPH, active_node_id="n1")
        self.assertEqual(len(self.viewer._edges), 2)

    def test_find_edge_label_at_matches_near_midpoint(self):
        self.viewer.render(self.ax, LINEAR_GRAPH, active_node_id="n1")
        display_x, display_y = self.viewer._to_display(self.viewer._edges[0]["midpoint"])
        label = self.viewer.find_edge_label_at(display_x, display_y)
        self.assertEqual(label, "Edge: n1 -> n2\n" + "-" * 20 + "\nCondition: ugv1/arrived == True")

    def test_edge_arrowhead_sits_at_the_midpoint_not_the_target_node(self):
        # Regression test: an arrowhead drawn at the target node's exact center was
        # completely hidden underneath that node's marker (drawn on top). It should
        # sit at the edge's midpoint, clear of both node markers.
        self.viewer.render(self.ax, LINEAR_GRAPH, active_node_id="n1")
        arrow_annotation = next(t for t in self.ax.texts if getattr(t, "arrow_patch", None) is not None)
        source_position, target_position = self.viewer._nodes[0]["position"], self.viewer._nodes[1]["position"]
        expected_midpoint = ((source_position[0] + target_position[0]) / 2,
                              (source_position[1] + target_position[1]) / 2)
        self.assertAlmostEqual(arrow_annotation.xy[0], expected_midpoint[0], delta=0.2)
        self.assertAlmostEqual(arrow_annotation.xy[1], expected_midpoint[1], delta=0.2)

    def test_find_edge_label_at_returns_none_far_from_any_edge(self):
        self.viewer.render(self.ax, LINEAR_GRAPH, active_node_id="n1")
        self.assertIsNone(self.viewer.find_edge_label_at(1000.0, 1000.0))

    def test_find_edge_label_at_returns_none_for_missing_coordinates(self):
        self.viewer.render(self.ax, LINEAR_GRAPH, active_node_id="n1")
        self.assertIsNone(self.viewer.find_edge_label_at(None, None))

    def test_describe_condition_reports_always_when_unconditional(self):
        self.assertEqual(MissionGraphViewer._describe_condition([]), "(always)")

    def test_render_records_one_edge_entry_per_edge_including_the_cycle_closer(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        self.assertEqual(len(self.viewer._edges), 3)

    def test_render_records_one_node_entry_per_graph_node(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        self.assertEqual(len(self.viewer._nodes), 3)

    def test_find_node_label_at_matches_near_node_position(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        display_x, display_y = self.viewer._to_display(self.viewer._nodes[0]["position"])
        self.assertIsNotNone(self.viewer.find_node_label_at(display_x, display_y))

    def test_find_edge_label_at_matches_near_the_cycle_closing_edge(self):
        # Regression test: the cycle-closing edge used to be a large curve whose
        # rendered peak sat nowhere near the stored (straight-line) hover point,
        # making it impossible to hover over the visible line.
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        closing_edge = next(edge for edge in self.viewer._edges if edge["label"].startswith("Edge: n3 -> n1"))
        display_x, display_y = self.viewer._to_display(closing_edge["midpoint"])
        self.assertEqual(self.viewer.find_edge_label_at(display_x, display_y), closing_edge["label"])

    def test_find_node_label_at_returns_none_far_from_any_node(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        self.assertIsNone(self.viewer.find_node_label_at(1000.0, 1000.0))

    def test_find_node_label_at_returns_none_just_outside_the_marker(self):
        # Regression test: the hover tolerance used to be much larger than the drawn
        # marker, making the hover area feel oversized relative to the node itself.
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        display_x, display_y = self.viewer._to_display(self.viewer._nodes[0]["position"])
        tolerance_pixels = self.viewer._points_to_pixels(NODE_HOVER_TOLERANCE_POINTS)
        self.assertIsNone(self.viewer.find_node_label_at(display_x + tolerance_pixels + 10, display_y))

    def test_find_node_label_at_uses_display_space_so_resizing_the_figure_does_not_break_it(self):
        # Regression test: hover tolerance used to be in data units, so it drifted
        # out of sync with the (fixed-size, in points) marker whenever the figure's
        # pixel dimensions changed relative to its data limits (e.g. a window resize).
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        node_position = self.viewer._nodes[0]["position"]
        self.fig.set_size_inches(2, 2)   # simulates a much smaller window
        display_x, display_y = self.viewer._to_display(node_position)
        self.assertIsNotNone(self.viewer.find_node_label_at(display_x, display_y))

    def test_node_hover_label_includes_live_status_for_active_node(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1",
                            primitive_statuses={"nav": {"capability": "move_to", "status": "in_progress", "inputs": {}}})
        label = next(node["label"] for node in self.viewer._nodes if node["label"].startswith("Node: n1"))
        self.assertIn("in_progress", label)

    def test_node_hover_label_for_inactive_node_shows_capability_only(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1", primitive_statuses=None)
        label = next(node["label"] for node in self.viewer._nodes if node["label"].startswith("Node: n1"))
        self.assertIn("move_to", label)
        self.assertNotIn("in_progress", label)

    def test_render_pads_limits_around_the_node_layout(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        positions = [node["position"] for node in self.viewer._nodes]
        x_min, x_max = self.ax.get_xlim()
        y_min, y_max = self.ax.get_ylim()
        for x, y in positions:
            self.assertGreater(x, x_min)
            self.assertLess(x, x_max)
            self.assertGreater(y, y_min)
            self.assertLess(y, y_max)

    def test_node_marker_is_not_clipped_by_the_axes(self):
        self.viewer.render(self.ax, CYCLE_GRAPH, active_node_id="n1")
        self.assertFalse(self.ax.collections[-1].get_clip_on())


if __name__ == "__main__":
    unittest.main()
