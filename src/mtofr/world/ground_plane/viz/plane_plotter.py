"""A 2D plot of ground_plane platforms on a plane, optionally over a GroundMap"""
import numpy as np
from matplotlib.patches import Patch
from mtofr.viz.base import EnvironmentViewer, points_to_pixels
from mtofr.maps import GroundMap


#========================================#
# Config
#========================================#

DEFAULT_LIMITS = (-10, 10)   # m, x and y view limits with no map
SELECTED_COLOR = "tab:orange"
UNSELECTED_COLOR = "tab:blue"
SELECTED_MARKER_SIZE = 10     # points
UNSELECTED_MARKER_SIZE = 6    # points
TRAVERSABILITY_ALPHA = 0.45
REGIONS_ALPHA = 0.45
MAP_ZORDER = 0
OVERLAY_ZORDER = 1
HEADING_OFFSET_POINTS = 6   # fixed on-screen distance from the dot to the heading marker
HEADING_MARKER_SIZE = 5     # points
HEADING_MARKER_SIDES = 3    # a triangle
HEADING_MARKER_ROTATION_OFFSET = -90   # deg; matplotlib's unrotated triangle points up (+y), heading 0 is +x
HEADING_MARKER_COLOR = "black"
LEGEND_EDGE_COLOR = "black"
COLOR_CHANNEL_MAX = 255
OFF_MAP_COLOR = "#c8c8c8"   # marks the area beyond a GroundMap's edge







#========================================#
# Plotter
#========================================#

class PlanePlotter(EnvironmentViewer):
    """Visualizes ground_plane platforms as a dot + heading arrow on a 2D plane,
    optionally over a GroundMap's cosmetic image (always shown when a map is given)
    plus toggleable traversability/regions overlays and a combined legend covering
    both platforms and whichever overlay(s) are visible. Draws onto an Axes it is
    given rather than owning a Figure/window, so it can be embedded inside a larger
    visualization tool. With no GroundMap, uses fixed xlim/ylim and no map layers."""
    def __init__(self, xlim=DEFAULT_LIMITS, ylim=DEFAULT_LIMITS, heading_offset_points=HEADING_OFFSET_POINTS,
                 ground_map: GroundMap | None = None):
        """With a map, the view limits come from its extent and xlim/ylim are ignored."""
        self.ground_map = ground_map
        if ground_map is not None:
            half_width, half_height = ground_map.width_meters / 2, ground_map.height_meters / 2
            xlim, ylim = (-half_width, half_width), (-half_height, half_height)
            self.background_color = OFF_MAP_COLOR
        self.xlim = xlim   # m
        self.ylim = ylim   # m
        self.heading_offset_points = heading_offset_points
        self.markers = {}   # platform_id -> dot artist
        self.arrows = {}    # platform_id -> heading marker artist

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
        for platform_id, state in states.items():
            is_selected = platform_id == selected_id
            color = SELECTED_COLOR if is_selected else UNSELECTED_COLOR
            marker_size = SELECTED_MARKER_SIZE if is_selected else UNSELECTED_MARKER_SIZE

            (marker,) = ax.plot([state.x], [state.y], "o", color=color, markersize=marker_size, label=platform_id)
            self.markers[platform_id] = marker
            platform_handles.append(marker)

            # NOTE: a rotated triangle marker rather than a data-space ax.arrow(): marker
            # size/rotation live in points, so this stays a fixed on-screen size
            # across zoom levels instead of scaling with the current view (which an
            # ax.arrow, drawn as a patch in data units, would).
            heading_x, heading_y = self._offset_point_in_display_space(
                ax, state.x, state.y, state.theta, self.heading_offset_points
            )
            heading_degrees = np.degrees(state.theta) + HEADING_MARKER_ROTATION_OFFSET
            (heading_marker,) = ax.plot(
                [heading_x], [heading_y], marker=(HEADING_MARKER_SIDES, 0, heading_degrees),
                color=HEADING_MARKER_COLOR, markersize=HEADING_MARKER_SIZE, linestyle="None", label="_nolegend_",
            )
            self.arrows[platform_id] = heading_marker

        all_handles = platform_handles + legend_handles
        if all_handles:
            ax.legend(handles=all_handles)

    @staticmethod
    def _offset_point_in_display_space(ax, x: float, y: float, theta: float, offset_points: float) -> tuple:
        """Converts a fixed on-screen distance (points) in the heading direction (rad)
        into a data-space point (m), so the heading marker's distance from the platform
        dot stays visually constant across zoom levels instead of scaling with them."""
        display_point = np.array(ax.transData.transform((x, y)))   # px
        displaced = display_point + points_to_pixels(ax, offset_points) * np.array(
            [np.cos(theta), np.sin(theta)]
        )
        data_point = ax.transData.inverted().transform(displaced)
        return data_point[0], data_point[1]

    def _render_map_layers(self, ax, show_traversability: bool, show_regions: bool) -> list:
        """Draws the cosmetic image (always) plus whichever overlays are toggled on,
        aligned via the same world-meters extent used by configure_ax's limits.
        Returns legend handles for the currently-visible overlay(s)."""
        half_width, half_height = self.ground_map.width_meters / 2, self.ground_map.height_meters / 2
        extent = (-half_width, half_width, -half_height, half_height)   # m
        ax.imshow(self.ground_map.cosmetic_image, extent=extent, zorder=MAP_ZORDER)

        legend_handles = []
        if show_traversability:
            ax.imshow(self.ground_map.traversability_image, extent=extent, alpha=TRAVERSABILITY_ALPHA,
                      zorder=OVERLAY_ZORDER)
            legend_handles += self._legend_patches(self.ground_map.traversability_lookup)
        if show_regions:
            ax.imshow(self.ground_map.regions_image, extent=extent, alpha=REGIONS_ALPHA, zorder=OVERLAY_ZORDER)
            legend_handles += self._legend_patches(self.ground_map.regions_lookup)
        return legend_handles

    @staticmethod
    def _legend_patches(lookup: dict) -> list:
        """One legend Patch per declared color in a traversability/regions lookup."""
        return [
            Patch(facecolor=tuple(channel / COLOR_CHANNEL_MAX for channel in rgb), edgecolor=LEGEND_EDGE_COLOR,
                  label=entry.name)
            for rgb, entry in lookup.items()
        ]
