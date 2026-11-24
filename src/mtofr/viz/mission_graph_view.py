"""Draws a mission graph onto a matplotlib Axes, highlighting the active node."""
import numpy as np

from mtofr.viz.base import TOOLTIP_RULE, is_within_display_tolerance, points_to_pixels


#========================================#
# Config
#========================================#

# Layout (data units)
LAYOUT_ITERATIONS = 150
LAYOUT_OPTIMAL_DISTANCE = 1.3   # target edge length the force simulation settles toward
LAYOUT_MIN_DISTANCE = 1e-6      # floor on distances, so coincident nodes never divide by zero
LAYOUT_PADDING = 0.6   # empty space kept around the node grid on every side
CURVE_UNIT = 0.35   # perpendicular offset per curvature step, spreading apart
                      # multiple edges that share the same pair of endpoints (in either
                      # direction) so they don't render as visually-coincident straight lines
LABEL_Y_OFFSET = 0.18   # keeps edge labels clear of the line itself
ARROWHEAD_MAX_HALF_SPAN = 0.15
ARROWHEAD_EDGE_FRACTION = 0.25   # an arrowhead's half span is at most this fraction of its edge's length
BEZIER_SAMPLES = 30


# Markers and hover (points)
NODE_MARKER_SIZE = 800   # points^2, passed straight to ax.scatter's `s`
NODE_MARKER_RADIUS_POINTS = (NODE_MARKER_SIZE / np.pi) ** 0.5   # matching on-screen radius, in points
NODE_HOVER_TOLERANCE_POINTS = NODE_MARKER_RADIUS_POINTS
EDGE_HOVER_TOLERANCE_POINTS = 12.0


# Style
GRAPH_PLOT_BACKGROUND = "#808080"   # mid-gray, shared by every view that draws a mission graph
ACTIVE_NODE_COLOR = "tab:orange"
NODE_COLOR = "tab:blue"
NODE_TEXT_COLOR = "white"
NODE_FONT_SIZE = 9
EDGE_COLOR = "black"
EDGE_LINE_WIDTH = 1.2
EDGE_LABEL_FONT_SIZE = 7
EDGE_LABEL_MAX_LENGTH = 24   # characters, before an edge label is truncated with an ellipsis
EDGE_ZORDER = 1
NODE_ZORDER = 3
NODE_TEXT_ZORDER = 4


# id(mission_graph) -> (mission_graph, {node_id: (x, y)}), oldest first; see compute_graph_layout.
# (id(mission_graph), pinned positions as a sorted tuple) -> (mission_graph, {node_id: (x, y)}),
# oldest first; see compute_graph_layout.
# NOTE: the mission_graph itself is kept alongside the result (not just its id) so the
# object can never be garbage-collected and have its id reused by an unrelated
# dict while still "cached", which would silently return a stale, wrong layout.
_layout_cache: dict = {}
LAYOUT_CACHE_LIMIT = 64   # layouts kept; every editor edit (or node drag) makes a new graph or pin set







#========================================#
# Layout
#========================================#

def compute_graph_layout(mission_graph: dict, pinned_positions: dict | None = None,
                         iterations: int = LAYOUT_ITERATIONS) -> dict:
    """Returns node_id -> (x, y) via a force-directed (Fruchterman-Reingold-style)
    layout: every node pair repels, every edge attracts its two endpoints, run for
    a fixed number of iterations with linearly-cooling step size. Unlike a columnar
    "one level per BFS distance from start" layout, this naturally spreads a cycle's
    nodes into a polygon (a triangle for 3 nodes) instead of a straight row, so a
    cycle-closing edge is a short straight line rather than a long one that has to
    curve around intervening nodes. Deterministic: nodes start evenly spaced on a
    circle (in mission-graph insertion order) rather than at random positions, so
    the same graph always lays out the same way.

    A node in `pinned_positions` (node_id -> (x, y): where an editor placed it) stays there:
    the simulation moves only the others, and none runs when every node is placed. Pins for
    nodes the graph doesn't have are ignored.

    Result is cached by the mission_graph object's identity (plus the pins): a mission graph
    is never mutated in place (the editor's draft helpers return new dicts), so re-running an
    O(n^2) force simulation on every render() call, several times a second, would
    recompute an answer that never changes. The cache keeps the LAYOUT_CACHE_LIMIT most
    recently computed layouts."""
    node_ids = list(mission_graph.get("nodes", {}))
    pins = pinned_positions or {}
    pinned = {node_id: (float(pins[node_id][0]), float(pins[node_id][1])) for node_id in node_ids if node_id in pins}
    cache_key = (id(mission_graph), tuple(sorted(pinned.items())))
    cached_entry = _layout_cache.get(cache_key)
    if cached_entry is not None:
        return cached_entry[1]

    if len(pinned) == len(node_ids):
        result = pinned
    elif len(node_ids) == 1:
        result = {node_ids[0]: (0.0, 0.0)}
    else:
        edge_pairs = [
            (source, edge["to"])
            for source, edge_list in mission_graph.get("edges", {}).items() if source in node_ids
            for edge in edge_list if edge["to"] in node_ids
        ]
        result = _simulate_layout(node_ids, edge_pairs, pinned, iterations)

    _layout_cache[cache_key] = (mission_graph, result)
    while len(_layout_cache) > LAYOUT_CACHE_LIMIT:
        del _layout_cache[next(iter(_layout_cache))]   # oldest entry
    return result


def _simulate_layout(node_ids: list, edge_pairs: list, pinned_positions: dict, iterations: int) -> dict:
    """The force simulation behind compute_graph_layout(), never moving a pinned node."""
    # Unplaced nodes start evenly spaced on a unit circle around the placed ones' centroid
    center = np.mean([np.array(position) for position in pinned_positions.values()], axis=0) \
        if pinned_positions else np.zeros(2)
    angle_step = 2 * np.pi / len(node_ids)
    positions = {
        node_id: (np.array(pinned_positions[node_id]) if node_id in pinned_positions
                  else center + np.array([np.cos(index * angle_step), np.sin(index * angle_step)]))
        for index, node_id in enumerate(node_ids)
    }


    # Simulate, cooling linearly
    for iteration in range(iterations):
        temperature = LAYOUT_OPTIMAL_DISTANCE * (1 - iteration / iterations)
        displacement = {node_id: np.zeros(2) for node_id in node_ids}

        for index, node_a in enumerate(node_ids):
            for node_b in node_ids[index + 1:]:
                delta = positions[node_a] - positions[node_b]
                distance = max(float(np.linalg.norm(delta)), LAYOUT_MIN_DISTANCE)
                direction = delta / distance
                repulsion = direction * (LAYOUT_OPTIMAL_DISTANCE ** 2) / distance
                displacement[node_a] += repulsion
                displacement[node_b] -= repulsion

        for source, target in edge_pairs:
            delta = positions[source] - positions[target]
            distance = max(float(np.linalg.norm(delta)), LAYOUT_MIN_DISTANCE)
            direction = delta / distance
            attraction = direction * (distance ** 2) / LAYOUT_OPTIMAL_DISTANCE
            displacement[source] -= attraction
            displacement[target] += attraction

        for node_id in node_ids:
            if node_id not in pinned_positions:
                magnitude = max(float(np.linalg.norm(displacement[node_id])), LAYOUT_MIN_DISTANCE)
                step = displacement[node_id] / magnitude * min(magnitude, temperature)
                positions[node_id] = positions[node_id] + step


    return {node_id: (float(position[0]), float(position[1])) for node_id, position in positions.items()}


def _curvature_for_group_index(index: int) -> float:
    """Maps 0, 1, 2, 3, ... to 0, +1, -1, +2, -2, ... (in curvature-step units):
    the first edge between a given pair of nodes stays straight, every later one
    (including the reverse direction) spreads alternately outward from it."""
    if index == 0:
        return 0.0
    magnitude = (index + 1) // 2
    return float(magnitude) if index % 2 == 1 else -float(magnitude)


def _bezier_control_and_midpoint(source: tuple, target: tuple, curvature: float) -> tuple:
    """Returns (control_point, curve_midpoint) for a quadratic bezier from source to
    target bowed by `curvature` (data units, perpendicular to the chord). At
    curvature 0 both points collapse to the ordinary straight-line midpoint."""
    x1, y1 = source
    x2, y2 = target
    chord_midpoint = ((x1 + x2) / 2, (y1 + y2) / 2)
    if curvature == 0.0:
        return chord_midpoint, chord_midpoint

    dx, dy = x2 - x1, y2 - y1
    length = float(np.hypot(dx, dy)) or 1.0
    perpendicular = (-dy / length, dx / length)
    control = (chord_midpoint[0] + perpendicular[0] * curvature, chord_midpoint[1] + perpendicular[1] * curvature)
    # A quadratic bezier's midpoint (t=0.5) sits halfway between the chord midpoint
    # and the control point: B(0.5) = 0.25*P0 + 0.5*C + 0.25*P2 = 0.5*(midpoint + C).
    curve_midpoint = ((chord_midpoint[0] + control[0]) / 2, (chord_midpoint[1] + control[1]) / 2)
    return control, curve_midpoint







#========================================#
# Viewer
#========================================#

class MissionGraphViewer:
    """Renders a mission graph's nodes/edges onto a matplotlib Axes it does not own,
    for embedding inside a larger visualization tool. Tracks node/edge positions and
    hover text from the last render so a dashboard can resolve a mouse position to
    whichever node or edge is under it. Hover hit-testing happens in *display*
    (pixel) space rather than data space: node/edge markers are a fixed size in
    points regardless of the current view, so a pixel-based tolerance stays
    correctly matched to what's actually on screen across window resizes, pans,
    and zooms, where a data-unit tolerance would drift."""
    def __init__(self):
        """Starts with nothing rendered."""
        self._ax = None   # last render()'s Axes, needed to convert data positions to display pixels
        self._nodes = []   # [{"position": (x, y) in data coords, "label": str}, ...] from the last render()
        self._edges = []   # [{"midpoint": (x, y) in data coords, "label": str}, ...] from the last render()

    #===============# Rendering #===============#

    def render(self, ax, mission_graph: dict, active_node_id, request_statuses: dict = None,
               overall_status: str = None, show_edge_labels: bool = False) -> None:
        """Draws every node (active node highlighted) and edge (optionally labeled).
        `request_statuses` (from Backseater.status()["capabilities"]) supplies live
        status for the active node's capability requests in the hover text; other nodes
        show only their statically-defined capability types. `overall_status` (from
        Backseater.status()["overall_status"]) is shown only on the active node's hover."""
        self._ax = ax
        positions = compute_graph_layout(mission_graph)
        self._edges = []
        self._nodes = []

        # Grouped by unordered endpoint pair (not by direction), so an edge and its
        # reverse (or a plain duplicate) are recognized as sharing the same chord
        # and curved apart from each other instead of overlapping.
        edge_group_indices = {}
        for node_id, edge_list in mission_graph.get("edges", {}).items():
            for edge in edge_list:
                target = edge["to"]
                if node_id in positions and target in positions:
                    group_key = frozenset((node_id, target))
                    group_index = edge_group_indices.get(group_key, 0)
                    edge_group_indices[group_key] = group_index + 1
                    curvature = _curvature_for_group_index(group_index) * CURVE_UNIT
                    self._render_edge(ax, node_id, target, positions[node_id], positions[target],
                                       edge.get("condition", []), show_edge_labels, curvature)

        for node_id, position in positions.items():
            self._render_node(ax, mission_graph, node_id, position, active_node_id, request_statuses, overall_status)

        self._set_padded_limits(ax, positions.values())
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_axis_off()

    @staticmethod
    def _set_padded_limits(ax, positions) -> None:
        """Sets explicit axis limits with generous, fixed padding instead of relying
        on matplotlib's autoscale. Autoscale margins are a percentage of the data
        range, which collapses to nearly nothing for e.g. a single-row graph (all
        nodes share one y value): too tight to fit node markers or edge labels,
        clipping them at small window sizes."""
        positions = list(positions)
        xs = [x for x, _ in positions] or [0.0]
        ys = [y for _, y in positions] or [0.0]
        ax.set_xlim(min(xs) - LAYOUT_PADDING, max(xs) + LAYOUT_PADDING)
        ax.set_ylim(min(ys) - LAYOUT_PADDING, max(ys) + LAYOUT_PADDING)

    def _render_edge(self, ax, source_id: str, target_id: str, source: tuple, target: tuple,
                      condition: list, show_edge_labels: bool, curvature: float = 0.0) -> None:
        """Draws one edge (straight, or bowed by `curvature`) with a midpoint arrowhead,
        and records its hover label."""
        control, curve_midpoint = _bezier_control_and_midpoint(source, target, curvature)
        if curvature == 0.0:
            # NOTE: a single annotate() spanning the whole edge would put the arrowhead
            # exactly at the target node's center, completely hidden underneath that
            # node's marker (drawn afterwards, on top). Draw a plain line for the full
            # edge, then a separate short arrowhead at the midpoint instead.
            ax.plot([source[0], target[0]], [source[1], target[1]], color=EDGE_COLOR,
                     linewidth=EDGE_LINE_WIDTH, zorder=EDGE_ZORDER, clip_on=False)
        else:
            # Multiple edges between the same pair of nodes (including the reverse
            # direction) would otherwise draw as visually-coincident straight lines;
            # bow this one along a quadratic bezier through `control` instead.
            steps = np.linspace(0.0, 1.0, BEZIER_SAMPLES)
            bezier_x = (1 - steps) ** 2 * source[0] + 2 * (1 - steps) * steps * control[0] + steps ** 2 * target[0]
            bezier_y = (1 - steps) ** 2 * source[1] + 2 * (1 - steps) * steps * control[1] + steps ** 2 * target[1]
            ax.plot(bezier_x, bezier_y, color=EDGE_COLOR, linewidth=EDGE_LINE_WIDTH, zorder=EDGE_ZORDER,
                    clip_on=False)
        # A quadratic bezier's tangent at t=0.5 is parallel to the source->target
        # chord regardless of curvature, so the straight-line arrowhead direction
        # is still correct; only its position (curve_midpoint) needs to move.
        self._draw_midpoint_arrowhead(ax, source, target, curve_midpoint)

        label_position = (curve_midpoint[0], curve_midpoint[1] + LABEL_Y_OFFSET)
        label = (f"Edge: {source_id} -> {target_id}\n{TOOLTIP_RULE}\n"
                 f"Condition: {self._describe_condition(condition)}")
        self._edges.append({"midpoint": curve_midpoint, "label": label})
        if show_edge_labels:
            ax.text(label_position[0], label_position[1], self._abbreviate_condition(condition),
                    fontsize=EDGE_LABEL_FONT_SIZE, color=EDGE_COLOR, ha="center", va="center", clip_on=False)

    @staticmethod
    def _draw_midpoint_arrowhead(ax, source: tuple, target: tuple, midpoint: tuple) -> None:
        """Draws a short arrowhead centered on `midpoint`, pointing in the
        source->target direction, independent of the full edge length."""
        x1, y1 = source
        x2, y2 = target
        dx, dy = x2 - x1, y2 - y1
        length = float(np.hypot(dx, dy)) or 1.0
        direction = (dx / length, dy / length)
        half_span = min(ARROWHEAD_MAX_HALF_SPAN, length * ARROWHEAD_EDGE_FRACTION)
        start = (midpoint[0] - direction[0] * half_span, midpoint[1] - direction[1] * half_span)
        end = (midpoint[0] + direction[0] * half_span, midpoint[1] + direction[1] * half_span)
        ax.annotate("", xy=end, xytext=start, annotation_clip=False,
                    arrowprops=dict(arrowstyle="->", color=EDGE_COLOR, clip_on=False))

    def _render_node(self, ax, mission_graph, node_id, position, active_node_id, request_statuses, overall_status) -> None:
        """Draws one node (highlighted if active) and records its hover label."""
        x, y = position
        color = ACTIVE_NODE_COLOR if node_id == active_node_id else NODE_COLOR
        ax.scatter([x], [y], s=NODE_MARKER_SIZE, color=color, zorder=NODE_ZORDER, clip_on=False)
        ax.text(x, y, node_id, ha="center", va="center", zorder=NODE_TEXT_ZORDER, color=NODE_TEXT_COLOR,
                fontsize=NODE_FONT_SIZE, clip_on=False)
        self._nodes.append({
            "position": (x, y),
            "label": self._describe_node(mission_graph, node_id, active_node_id, request_statuses, overall_status),
        })





    #===============# Hover #===============#

    def _to_display(self, data_position: tuple) -> tuple:
        """Converts a data-space position to display pixels on the last-rendered Axes."""
        return tuple(self._ax.transData.transform(data_position))

    def _points_to_pixels(self, points: float) -> float:
        """Converts points to display pixels at the last-rendered figure's DPI."""
        return points_to_pixels(self._ax, points)

    def find_edge_label_at(self, display_x, display_y, tolerance_points: float = EDGE_HOVER_TOLERANCE_POINTS):
        """Returns the full condition text of the edge whose midpoint is within
        `tolerance_points` of (display_x, display_y) (px, as reported by a matplotlib
        event's `.x`/`.y`) from the last render(), or None if none is close enough."""
        if display_x is None or display_y is None or self._ax is None:
            return None
        return next((edge["label"] for edge in self._edges
                     if is_within_display_tolerance(self._ax, edge["midpoint"], display_x, display_y,
                                                    tolerance_points)),
                    None)

    def find_node_label_at(self, display_x, display_y, tolerance_points: float = NODE_HOVER_TOLERANCE_POINTS):
        """Returns the hover text of the node whose position is within
        `tolerance_points` of (display_x, display_y) (px, as reported by a matplotlib
        event's `.x`/`.y`) from the last render(), or None if none is close enough."""
        if display_x is None or display_y is None or self._ax is None:
            return None
        return next((node["label"] for node in self._nodes
                     if is_within_display_tolerance(self._ax, node["position"], display_x, display_y,
                                                    tolerance_points)),
                    None)





    #===============# Text #===============#

    @staticmethod
    def _describe_node(mission_graph: dict, node_id: str, active_node_id, request_statuses: dict, overall_status: str) -> str:
        """A node's hover text: its capability requests, with live status if it's the active node."""
        capability_requests = mission_graph.get("nodes", {}).get(node_id, {}).get("capabilities", {})
        lines = [f"Node: {node_id}", TOOLTIP_RULE]
        if node_id == active_node_id and overall_status:
            lines.append(overall_status)
        if not capability_requests:
            lines.append("(no capabilities)")
        for name, capability_request in capability_requests.items():
            if node_id == active_node_id and request_statuses and name in request_statuses:
                info = request_statuses[name]
                lines.append(f"{name} ({info['capability']}): {info['status']}")
            else:
                lines.append(f"{name} ({capability_request['capability']})")
        return "\n".join(lines)

    @staticmethod
    def _describe_condition(condition: list) -> str:
        """The condition's tokens joined with spaces, or "(always)" for an empty one."""
        if not condition:
            return "(always)"
        return " ".join(str(token) for token in condition)

    @staticmethod
    def _abbreviate_condition(condition: list, max_length: int = EDGE_LABEL_MAX_LENGTH) -> str:
        """The condition's text truncated to `max_length` characters, or "*" for an empty one."""
        if not condition:
            return "*"
        text = " ".join(str(token) for token in condition)
        return text if len(text) <= max_length else text[:max_length - 1] + "…"
