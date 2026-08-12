"""A 2D plot of ground_plane platforms on a plane"""
import numpy as np
from mtofr.viz.base import EnvironmentViewer

SELECTED_COLOR = "tab:orange"
UNSELECTED_COLOR = "tab:blue"


class PlanePlotter(EnvironmentViewer):
    """Vizualizes ground_plane platforms as a dot + heading arrow on a 2D plane.
    Draws onto an Axes it is given rather than owning a Figure/window, so it can be
    embedded inside a larger visualization tool."""
    def __init__(self, xlim=(-10, 10), ylim=(-10, 10), arrow_len=0.5):
        self.xlim = xlim
        self.ylim = ylim
        self.arrow_len = arrow_len
        self.markers = {}   # eid -> dot artist
        self.arrows = {}    # eid -> heading arrow artist

    def configure_ax(self, ax) -> None:
        """Sets axis limits/aspect ratio. Safe to call every redraw (ax.clear() resets them)."""
        ax.set_xlim(*self.xlim)
        ax.set_ylim(*self.ylim)
        ax.set_aspect("equal")

    def render(self, ax, states: dict, selected_id: str = None) -> None:
        """Draws all platforms; the selected one is drawn larger and in a distinct color."""
        self.markers = {}
        self.arrows = {}

        for eid, state in states.items():
            is_selected = eid == selected_id
            color = SELECTED_COLOR if is_selected else UNSELECTED_COLOR
            marker_size = 10 if is_selected else 6

            (marker,) = ax.plot([state.x], [state.y], "o", color=color, markersize=marker_size, label=eid)
            self.markers[eid] = marker

            dx = self.arrow_len * np.cos(state.theta)
            dy = self.arrow_len * np.sin(state.theta)
            self.arrows[eid] = ax.arrow(
                state.x, state.y, dx, dy,
                head_width=0.15, length_includes_head=True, color="black"
            )

        if states:
            ax.legend()
