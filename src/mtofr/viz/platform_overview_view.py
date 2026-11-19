"""Draws a simple vertical list of platform ids onto a matplotlib Axes, for the
dashboard's Mission Overview tab."""
from mtofr.viz.base import TOOLTIP_RULE, is_within_display_tolerance, points_to_pixels


#========================================#
# Config
#========================================#

ROW_SPACING = 1.0     # data units between platform rows
BOX_X_OFFSET = -0.55  # data units left of the label text where the hover box sits
BOX_MARKER_SIZE = 140   # points^2, passed straight to ax.scatter's `s`
BOX_COLOR = "tab:blue"
TEXT_COLOR = "white"
TEXT_FONT_SIZE = 11
ROW_ZORDER = 2
LABEL_HOVER_TOLERANCE_POINTS = 30.0
LAYOUT_PADDING = 0.6   # data units
X_LIMITS = (-1.5, 5.0)   # data units; fixed width, wide enough for a platform id + a short node name







#========================================#
# Viewer
#========================================#

class PlatformOverviewViewer:
    """Renders one row per platform id: a lightweight stand-in for a real
    cross-platform mission graph, which doesn't exist yet. Each row always shows the
    platform's active node inline (not just on hover) next to a small colored box
    marking where to hover for its active capability requests; the box's position (not the
    text) is what hover/click hit-testing tracks, since the box is the visible hover
    target. Hit-testing happens in *display* (pixel) space, mirroring
    MissionGraphViewer's node hover, so the hover/click area stays correctly sized
    across resizes/pans/zooms."""
    def __init__(self):
        """Starts with nothing rendered."""
        self._ax = None
        self._rows = []   # [{"position", "platform_id", "label"}, ...] from the last render()

    def render(self, ax, backseaters: dict) -> None:
        """Draws one row per platform_id -> Backseater in `backseaters`."""
        self._ax = ax
        self._rows = []

        for index, (platform_id, backseater) in enumerate(backseaters.items()):
            y = -index * ROW_SPACING
            status = backseater.status()
            box_position = (BOX_X_OFFSET, y)

            ax.scatter([box_position[0]], [box_position[1]], s=BOX_MARKER_SIZE, marker="s",
                        color=BOX_COLOR, zorder=ROW_ZORDER, clip_on=False)
            ax.text(0.0, y, self._describe_active_node(platform_id, status["active_node_id"]),
                     ha="left", va="center", zorder=ROW_ZORDER, color=TEXT_COLOR, fontsize=TEXT_FONT_SIZE,
                     clip_on=False)

            self._rows.append({
                "position": box_position,
                "platform_id": platform_id,
                "label": self._describe_platform(platform_id, status),
            })

        ys = [row["position"][1] for row in self._rows] or [0.0]
        ax.set_xlim(*X_LIMITS)
        ax.set_ylim(min(ys) - LAYOUT_PADDING, max(ys) + LAYOUT_PADDING)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_axis_off()

    def _to_display(self, data_position: tuple) -> tuple:
        """Converts a data-space position to display pixels on the last-rendered Axes."""
        return tuple(self._ax.transData.transform(data_position))

    def _points_to_pixels(self, points: float) -> float:
        """Converts points to display pixels at the last-rendered figure's DPI."""
        return points_to_pixels(self._ax, points)

    def _row_at(self, display_x, display_y, tolerance_points: float):
        """The row whose box is within `tolerance_points` of (display_x, display_y), or None."""
        if display_x is None or display_y is None or self._ax is None:
            return None
        return next((row for row in self._rows
                     if is_within_display_tolerance(self._ax, row["position"], display_x, display_y,
                                                    tolerance_points)),
                    None)

    def find_platform_label_at(self, display_x, display_y, tolerance_points: float = LABEL_HOVER_TOLERANCE_POINTS):
        """Returns the hover text of the platform row within `tolerance_points` of
        (display_x, display_y) (px, as reported by a matplotlib event's `.x`/`.y`)
        from the last render(), or None if none is close enough."""
        row = self._row_at(display_x, display_y, tolerance_points)
        return row["label"] if row else None

    def find_platform_id_at(self, display_x, display_y, tolerance_points: float = LABEL_HOVER_TOLERANCE_POINTS):
        """Returns the platform id of the row at (display_x, display_y), the same
        way find_platform_label_at() does: the click-to-select path."""
        row = self._row_at(display_x, display_y, tolerance_points)
        return row["platform_id"] if row else None

    @staticmethod
    def _describe_active_node(platform_id: str, active_node_id) -> str:
        """The inline row text: `platform_id: "active_node"`, or (none)."""
        if active_node_id is None:
            return f"{platform_id}: (none)"
        return f'{platform_id}: "{active_node_id}"'

    @staticmethod
    def _describe_platform(platform_id: str, status: dict) -> str:
        """A row's hover text: overall status plus each active capability request's status."""
        capability_requests = status["capabilities"]
        lines = [f"Platform: {platform_id}", TOOLTIP_RULE, status["overall_status"]]
        if not capability_requests:
            lines.append("(no active capabilities)")
        for name, info in capability_requests.items():
            lines.append(f"{name} ({info['capability']}): {info['status']}")
        return "\n".join(lines)
