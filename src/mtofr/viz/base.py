"""Defines the environment-viewer interface shared across all environments."""
from abc import ABC, abstractmethod


class EnvironmentViewer(ABC):
    """Renders one environment's platforms onto a matplotlib Axes it does not own,
    so it can be embedded as one tile inside a larger visualization tool (e.g.
    MissionDashboard) instead of managing its own Figure/window."""

    # The Axes facecolor MissionDashboard applies before each render -- lets a
    # viewer with a bounded map (e.g. PlanePlotter with a GroundMap) mark the area
    # beyond the map's edge distinctly, so panning/zooming past it reads as "off the
    # map" instead of looking like more valid space. Plain white for a viewer with
    # no such notion of "off the map" (the default).
    background_color: str = "white"

    @abstractmethod
    def configure_ax(self, ax) -> None:
        """One-time (or per-redraw) axis setup: limits, aspect ratio, labels."""

    @abstractmethod
    def render(self, ax, states: dict, selected_id: str = None,
               show_traversability: bool = False, show_regions: bool = False) -> None:
        """Draws every platform in `states` (entity_id -> WorldState) onto ax,
        visually distinguishing `selected_id` if given. `show_traversability`/
        `show_regions` toggle optional map overlays; a viewer with no map ignores
        them."""
