"""Defines the environment-viewer interface shared across all environments, plus the
display-space helpers every viewer's hover hit-testing uses."""
from abc import ABC, abstractmethod


#========================================#
# Config
#========================================#

POINTS_PER_INCH = 72.0
TOOLTIP_RULE = "-" * 20   # separates a tooltip's title line from its body







#========================================#
# Display Helpers
#========================================#

def points_to_pixels(ax, points: float) -> float:
    """Converts a size in points to display pixels at `ax`'s figure DPI."""
    return points * ax.figure.dpi / POINTS_PER_INCH


def is_within_display_tolerance(ax, data_position: tuple, display_x: float, display_y: float,
                                tolerance_points: float) -> bool:
    """Whether `data_position` (data units) lands within `tolerance_points` of
    (display_x, display_y) (px, as reported by a matplotlib event's `.x`/`.y`).
    Compared in display space so a fixed-size marker's hit area stays matched to
    what's on screen across resizes, pans, and zooms."""
    position_x, position_y = ax.transData.transform(data_position)
    tolerance_pixels = points_to_pixels(ax, tolerance_points)
    return (position_x - display_x) ** 2 + (position_y - display_y) ** 2 <= tolerance_pixels ** 2







#========================================#
# Environment Viewer
#========================================#

class EnvironmentViewer(ABC):
    """Renders one environment's platforms onto a matplotlib Axes it does not own,
    so it can be embedded as one tile inside a larger visualization tool (e.g.
    MissionDashboard) instead of managing its own Figure/window."""

    # The Axes facecolor MissionDashboard applies before each render. Lets a viewer
    # with a bounded map (e.g. PlanePlotter with a GroundMap) mark the area beyond the
    # map's edge distinctly, so panning/zooming past it reads as "off the map" instead
    # of looking like more valid space. Plain white for a viewer with no such notion
    # of "off the map" (the default).
    background_color: str = "white"

    @abstractmethod
    def configure_ax(self, ax) -> None:
        """One-time (or per-redraw) axis setup: limits, aspect ratio, labels."""

    @abstractmethod
    def render(self, ax, states: dict, selected_id: str = None,
               show_traversability: bool = False, show_regions: bool = False) -> None:
        """Draws every platform in `states` (platform_id -> WorldState) onto ax,
        visually distinguishing `selected_id` if given. `show_traversability`/
        `show_regions` toggle optional map overlays; a viewer with no map ignores
        them."""
