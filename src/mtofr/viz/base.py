"""Defines the environment-viewer interface shared across all environments."""
from abc import ABC, abstractmethod


class EnvironmentViewer(ABC):
    """Renders one environment's platforms onto a matplotlib Axes it does not own,
    so it can be embedded as one tile inside a larger visualization tool (e.g.
    MissionDashboard) instead of managing its own Figure/window."""

    @abstractmethod
    def configure_ax(self, ax) -> None:
        """One-time (or per-redraw) axis setup: limits, aspect ratio, labels."""

    @abstractmethod
    def render(self, ax, states: dict, selected_id: str = None) -> None:
        """Draws every platform in `states` (entity_id -> WorldState) onto ax,
        visually distinguishing `selected_id` if given."""
