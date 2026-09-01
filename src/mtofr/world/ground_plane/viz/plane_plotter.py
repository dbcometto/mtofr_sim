"""A 2D plot of ground_plane platforms on a plane, optionally over a GroundMap"""
import numpy as np
from matplotlib.patches import Patch
from mtofr.viz.base import EnvironmentViewer
from mtofr.maps import GroundMap

SELECTED_COLOR = "tab:orange"
UNSELECTED_COLOR = "tab:blue"
TRAVERSABILITY_ALPHA = 0.45
REGIONS_ALPHA = 0.45
HEADING_OFFSET_POINTS = 6   # fixed on-screen distance from the dot to the heading marker
HEADING_MARKER_SIZE = 5
OFF_MAP_COLOR = "#c8c8c8"   # marks the area beyond a GroundMap's edge


class PlanePlotter(EnvironmentViewer):
    """Vizualizes ground_plane platforms as a dot + heading arrow on a 2D plane,
    optionally over a GroundMap's cosmetic image (always shown when a map is given)
    plus toggleable traversability/regions overlays and a combined legend covering
    both platforms and whichever overlay(s) are visible. Draws onto an Axes it is
    given rather than owning a Figure/window, so it can be embedded inside a larger
    visualization tool. With no GroundMap, behaves exactly as before (fixed xlim/
    ylim, no map layers)."""
    def __init__(self, xlim=(-10, 10), ylim=(-10, 10), heading_offset_points=HEADING_OFFSET_POINTS,
                 ground_map: GroundMap | None = None):
        self.ground_map = ground_map
        if ground_map is not None:
            half_width, half_height = ground_map.width_meters / 2, ground_map.height_meters / 2
            xlim, ylim = (-half_width, half_width), (-half_height, half_height)
            self.background_color = OFF_MAP_COLOR
        self.xlim = xlim
        self.ylim = ylim
        self.heading_offset_points = heading_offset_points
        self.markers = {}   # eid -> dot artist
        self.arrows = {}    # eid -> heading marker artist

    def configure_ax(self, ax) -> None:
        """Sets axis limits/aspect ratio. Safe to call every redraw (ax.clear() resets them)."""
        ax.set_xlim(*self.xlim)
        ax.set_ylim(*self.ylim)
        ax.set_aspect("equal")

    def render(self, ax, states: dict, selected_id: str = None,
               show_traversability: bool = False, show_regions: bool = False) -> None:
        """Draws the map (if any) and all platforms; the selected platform is drawn
        larger and in a distinct color."""
        self.markers = {}
        self.arrows = {}
        legend_handles = []

        if self.ground_map is not None:
            legend_handles += self._render_map_layers(ax, show_traversability, show_regions)

        platform_handles = []
        for eid, state in states.items():
            is_selected = eid == selected_id
            color = SELECTED_COLOR if is_selected else UNSELECTED_COLOR
            marker_size = 10 if is_selected else 6

            (marker,) = ax.plot([state.x], [state.y], "o", color=color, markersize=marker_size, label=eid)
            self.markers[eid] = marker
            platform_handles.append(marker)

            # A rotated triangle marker rather than a data-space ax.arrow(): marker
            # size/rotation live in points, so this stays a fixed on-screen size
            # across zoom levels instead of scaling with the current view (which an
            # ax.arrow -- drawn as a patch in data units -- would).
            heading_x, heading_y = self._offset_point_in_display_space(
                ax, state.x, state.y, state.theta, self.heading_offset_points
            )
            heading_degrees = np.degrees(state.theta) - 90
            (heading_marker,) = ax.plot(
                [heading_x], [heading_y], marker=(3, 0, heading_degrees), color="black",
                markersize=HEADING_MARKER_SIZE, linestyle="None", label="_nolegend_",
            )
            self.arrows[eid] = heading_marker

        all_handles = platform_handles + legend_handles
        if all_handles:
            ax.legend(handles=all_handles)

    @staticmethod
    def _offset_point_in_display_space(ax, x: float, y: float, theta: float, offset_points: float) -> tuple:
        """Converts a fixed on-screen distance (points) in the heading direction into
        a data-space point, so the heading marker's distance from the platform dot
        stays visually constant across zoom levels instead of scaling with them."""
        display_point = np.array(ax.transData.transform((x, y)))
        pixels_per_point = ax.figure.dpi / 72.0
        displaced = display_point + offset_points * pixels_per_point * np.array(
            [np.cos(theta), np.sin(theta)]
        )
        data_point = ax.transData.inverted().transform(displaced)
        return data_point[0], data_point[1]

    def _render_map_layers(self, ax, show_traversability: bool, show_regions: bool) -> list:
        """Draws the cosmetic image (always) plus whichever overlays are toggled on,
        aligned via the same world-meters extent used by configure_ax's limits.
        Returns legend handles for the currently-visible overlay(s)."""
        half_width, half_height = self.ground_map.width_meters / 2, self.ground_map.height_meters / 2
        extent = (-half_width, half_width, -half_height, half_height)
        ax.imshow(self.ground_map.cosmetic_image, extent=extent, zorder=0)

        legend_handles = []
        if show_traversability:
            ax.imshow(self.ground_map.traversability_image, extent=extent, alpha=TRAVERSABILITY_ALPHA, zorder=1)
            legend_handles += self._legend_patches(self.ground_map.traversability_lookup)
        if show_regions:
            ax.imshow(self.ground_map.regions_image, extent=extent, alpha=REGIONS_ALPHA, zorder=1)
            legend_handles += self._legend_patches(self.ground_map.regions_lookup)
        return legend_handles

    @staticmethod
    def _legend_patches(lookup: dict) -> list:
        """One legend Patch per declared color in a traversability/regions lookup."""
        return [
            Patch(facecolor=tuple(channel / 255 for channel in rgb), edgecolor="black", label=entry.name)
            for rgb, entry in lookup.items()
        ]