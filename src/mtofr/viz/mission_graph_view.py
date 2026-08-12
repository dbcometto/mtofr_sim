"""Draws a mission graph onto a matplotlib Axes, highlighting the active node."""
import numpy as np


#==========# Layout #==========#

LAYOUT_ITERATIONS = 150
LAYOUT_OPTIMAL_DISTANCE = 1.3   # target edge length the force simulation settles toward


def compute_graph_layout(mission_graph: dict, iterations: int = LAYOUT_ITERATIONS) -> dict:
    """Returns node_id -> (x, y) via a force-directed (Fruchterman-Reingold-style)
    layout: every node pair repels, every edge attracts its two endpoints, run for
    a fixed number of iterations with linearly-cooling step size. Unlike a columnar
    "one level per BFS distance from start" layout, this naturally spreads a cycle's
    nodes into a polygon (a triangle for 3 nodes) instead of a straight row, so a
    cycle-closing edge is a short straight line rather than a long one that has to
    curve around intervening nodes. Deterministic: nodes start evenly spaced on a
    circle (in mission-graph insertion order) rather than at random positions, so
    the same graph always lays out the same way."""
    node_ids = list(mission_graph.get("nodes", {}))
    if not node_ids:
        return {}
    if len(node_ids) == 1:
        return {node_ids[0]: (0.0, 0.0)}

    edges = mission_graph.get("edges", {})
    edge_pairs = [
        (source, edge["to"])
        for source, edge_list in edges.items() if source in node_ids
        for edge in edge_list if edge["to"] in node_ids
    ]

    angle_step = 2 * np.pi / len(node_ids)
    positions = {
        node_id: np.array([np.cos(index * angle_step), np.sin(index * angle_step)])
        for index, node_id in enumerate(node_ids)
    }

    for iteration in range(iterations):
        temperature = LAYOUT_OPTIMAL_DISTANCE * (1 - iteration / iterations)
        displacement = {node_id: np.zeros(2) for node_id in node_ids}

        for i, node_a in enumerate(node_ids):
            for node_b in node_ids[i + 1:]:
                delta = positions[node_a] - positions[node_b]
                distance = max(float(np.linalg.norm(delta)), 1e-6)
                direction = delta / distance
                repulsion = direction * (LAYOUT_OPTIMAL_DISTANCE ** 2) / distance
                displacement[node_a] += repulsion
                displacement[node_b] -= repulsion

        for source, target in edge_pairs:
            delta = positions[source] - positions[target]
            distance = max(float(np.linalg.norm(delta)), 1e-6)
            direction = delta / distance
            attraction = direction * (distance ** 2) / LAYOUT_OPTIMAL_DISTANCE
            displacement[source] -= attraction
            displacement[target] += attraction

        for node_id in node_ids:
            magnitude = max(float(np.linalg.norm(displacement[node_id])), 1e-6)
            step = displacement[node_id] / magnitude * min(magnitude, temperature)
            positions[node_id] = positions[node_id] + step

    return {node_id: (float(position[0]), float(position[1])) for node_id, position in positions.items()}


#==========# Viewer #==========#

NODE_MARKER_SIZE = 800   # points^2, passed straight to ax.scatter's `s`
NODE_MARKER_RADIUS_POINTS = (NODE_MARKER_SIZE / np.pi) ** 0.5   # matching on-screen radius, in points
NODE_HOVER_TOLERANCE_POINTS = NODE_MARKER_RADIUS_POINTS
EDGE_HOVER_TOLERANCE_POINTS = 12.0
LABEL_Y_OFFSET = 0.18   # keeps edge labels clear of the line itself, in data units
LAYOUT_PADDING = 0.6   # data units of empty space kept around the node grid on every side


class MissionGraphViewer:
    """Renders a mission graph's nodes/edges onto a matplotlib Axes it does not own,
    for embedding inside a larger visualization tool. Tracks node/edge positions and
    hover text from the last render so a dashboard can resolve a mouse position to
    whichever node or edge is under it. Hover hit-testing happens in *display*
    (pixel) space rather than data space: node/edge markers are a fixed size in
    points regardless of the current view, so a pixel-based tolerance stays
    correctly matched to what's actually on screen across window resizes, pans,
    and zooms — a data-unit tolerance would drift as the data-to-pixel scale
    changes."""
    def __init__(self):
        self._ax = None   # last render()'s Axes, needed to convert data positions to display pixels
        self._nodes = []   # [{"position": (x, y) in data coords, "label": str}, ...] from the last render()
        self._edges = []   # [{"midpoint": (x, y) in data coords, "label": str}, ...] from the last render()

    def render(self, ax, mission_graph: dict, active_node_id, primitive_statuses: dict = None,
               show_edge_labels: bool = False) -> None:
        """Draws every node (active node highlighted) and edge (optionally labeled).
        `primitive_statuses` (from Backseater.status()["primitives"]) supplies live
        status/handle for the active node's primitives in the hover text; other nodes
        show only their statically-defined primitive types."""
        self._ax = ax
        positions = compute_graph_layout(mission_graph)
        self._edges = []
        self._nodes = []

        for node_id, edge_list in mission_graph.get("edges", {}).items():
            if node_id not in positions:
                continue
            for edge in edge_list:
                target = edge["to"]
                if target not in positions:
                    continue
                self._render_edge(ax, node_id, target, positions[node_id], positions[target],
                                   edge.get("conditions", []), show_edge_labels)

        for node_id, position in positions.items():
            self._render_node(ax, mission_graph, node_id, position, active_node_id, primitive_statuses)

        self._set_padded_limits(ax, positions.values())
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_axis_off()

    @staticmethod
    def _set_padded_limits(ax, positions) -> None:
        """Sets explicit axis limits with generous, fixed padding instead of relying
        on matplotlib's autoscale. Autoscale margins are a percentage of the data
        range, which collapses to nearly nothing for e.g. a single-row graph (all
        nodes share one y value) — too tight to fit node markers or edge labels,
        clipping them at small window sizes."""
        positions = list(positions)
        xs = [x for x, _ in positions] or [0.0]
        ys = [y for _, y in positions] or [0.0]
        ax.set_xlim(min(xs) - LAYOUT_PADDING, max(xs) + LAYOUT_PADDING)
        ax.set_ylim(min(ys) - LAYOUT_PADDING, max(ys) + LAYOUT_PADDING)

    def _render_edge(self, ax, source_id: str, target_id: str, source: tuple, target: tuple,
                      conditions: list, show_edge_labels: bool) -> None:
        x1, y1 = source
        x2, y2 = target
        # A single annotate() spanning the whole edge would put the arrowhead
        # exactly at the target node's center — completely hidden underneath that
        # node's marker (drawn afterwards, on top). Draw a plain line for the full
        # edge, then a separate short arrowhead centered at the midpoint instead.
        ax.plot([x1, x2], [y1, y2], color="black", linewidth=1.2, zorder=1, clip_on=False)
        self._draw_midpoint_arrowhead(ax, source, target)

        midpoint = ((x1 + x2) / 2, (y1 + y2) / 2)
        label_position = (midpoint[0], midpoint[1] + LABEL_Y_OFFSET)
        label = f"{source_id} -> {target_id}: {self._describe_conditions(conditions)}"
        self._edges.append({"midpoint": midpoint, "label": label})
        if show_edge_labels:
            ax.text(label_position[0], label_position[1], self._abbreviate_conditions(conditions),
                    fontsize=7, color="black", ha="center", va="center", clip_on=False)

    @staticmethod
    def _draw_midpoint_arrowhead(ax, source: tuple, target: tuple) -> None:
        """Draws a short arrowhead centered on the edge's midpoint, pointing from
        source to target, independent of the full edge length."""
        x1, y1 = source
        x2, y2 = target
        dx, dy = x2 - x1, y2 - y1
        length = float(np.hypot(dx, dy)) or 1.0
        direction = (dx / length, dy / length)
        half_span = min(0.15, length / 4)
        midpoint = ((x1 + x2) / 2, (y1 + y2) / 2)
        start = (midpoint[0] - direction[0] * half_span, midpoint[1] - direction[1] * half_span)
        end = (midpoint[0] + direction[0] * half_span, midpoint[1] + direction[1] * half_span)
        ax.annotate("", xy=end, xytext=start, annotation_clip=False,
                    arrowprops=dict(arrowstyle="->", color="black", clip_on=False))

    def _render_node(self, ax, mission_graph, node_id, position, active_node_id, primitive_statuses) -> None:
        x, y = position
        color = "tab:orange" if node_id == active_node_id else "tab:blue"
        ax.scatter([x], [y], s=NODE_MARKER_SIZE, color=color, zorder=3, clip_on=False)
        ax.text(x, y, node_id, ha="center", va="center", zorder=4, color="white", fontsize=9, clip_on=False)
        self._nodes.append({
            "position": (x, y),
            "label": self._describe_node(mission_graph, node_id, active_node_id, primitive_statuses),
        })

    def _to_display(self, data_position: tuple) -> tuple:
        return tuple(self._ax.transData.transform(data_position))

    def _points_to_pixels(self, points: float) -> float:
        return points * self._ax.figure.dpi / 72.0

    def find_edge_label_at(self, display_x, display_y, tolerance_points: float = EDGE_HOVER_TOLERANCE_POINTS):
        """Returns the full condition text of the edge whose midpoint is within
        `tolerance_points` (converted to display pixels via the current figure's
        DPI) of (display_x, display_y) — mouse coordinates as reported by a
        matplotlib event's `.x`/`.y` — from the last render(), or None if none is
        close enough."""
        if display_x is None or display_y is None or self._ax is None:
            return None
        tolerance_pixels = self._points_to_pixels(tolerance_points)
        for edge in self._edges:
            midpoint_x, midpoint_y = self._to_display(edge["midpoint"])
            if (midpoint_x - display_x) ** 2 + (midpoint_y - display_y) ** 2 <= tolerance_pixels ** 2:
                return edge["label"]
        return None

    def find_node_label_at(self, display_x, display_y, tolerance_points: float = NODE_HOVER_TOLERANCE_POINTS):
        """Returns the hover text of the node whose position is within
        `tolerance_points` (converted to display pixels via the current figure's
        DPI) of (display_x, display_y) — mouse coordinates as reported by a
        matplotlib event's `.x`/`.y` — from the last render(), or None if none is
        close enough."""
        if display_x is None or display_y is None or self._ax is None:
            return None
        tolerance_pixels = self._points_to_pixels(tolerance_points)
        for node in self._nodes:
            node_x, node_y = self._to_display(node["position"])
            if (node_x - display_x) ** 2 + (node_y - display_y) ** 2 <= tolerance_pixels ** 2:
                return node["label"]
        return None

    @staticmethod
    def _describe_node(mission_graph: dict, node_id: str, active_node_id, primitive_statuses: dict) -> str:
        primitives = mission_graph.get("nodes", {}).get(node_id, {}).get("primitives", {})
        lines = [node_id]
        if not primitives:
            lines.append("(no primitives)")
        for name, primitive in primitives.items():
            if node_id == active_node_id and primitive_statuses and name in primitive_statuses:
                info = primitive_statuses[name]
                lines.append(f"{name} ({info['type']}): {info['status']}")
            else:
                lines.append(f"{name} ({primitive['type']})")
        return "\n".join(lines)

    @staticmethod
    def _describe_conditions(conditions: list) -> str:
        if not conditions:
            return "(always)"
        return ", ".join(f"{condition['primitive']}={condition['status']}" for condition in conditions)

    @staticmethod
    def _abbreviate_conditions(conditions: list) -> str:
        if not conditions:
            return "*"
        return ",".join(f"{condition['primitive']}={condition['status'][0]}" for condition in conditions)
