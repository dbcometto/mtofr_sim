"""Defines WorldViewerPanel: an overhead view of the interface hardware's sensed map with every
platform's sensed pose, plus a trajectory drawer (browser-side) whose output is copyable text."""
import io
import threading

import matplotlib.image as mpimg

from mtofr.database import Pose
from mtofr.environments.ground_plane.maps import GroundMap
from mtofr.environments.ground_plane.platforms.interface.web.config import BUILT_IN_PANEL_SCRIPT_DIRECTORY
from mtofr.environments.ground_plane.platforms.interface.web.panel import PanelContext, WebPanel
from mtofr.environments.ground_plane.platforms.interface.web.view import InterfaceView


#========================================#
# Config
#========================================#

PNG_CONTENT_TYPE = "image/png"
# Asset file name -> the GroundMap attribute holding that layer's image array
MAP_LAYER_ASSETS = {
    "cosmetic.png": "cosmetic_image",
    "traversability.png": "traversability_image",
    "regions.png": "regions_image",
}







#========================================#
# Panel
#========================================#

class WorldViewerPanel(WebPanel):
    """The map the interface's own hardware senses (InterfaceView.ground_map), drawn in world
    coordinates, with a marker for every Pose in Knowledge (each platform's sense_pose output,
    e.g. "ugv1/pose", as synced). The map layers are served as PNG assets.

    The trajectory drawer lives entirely in the browser: it turns clicked waypoints into
    Trajectory text to copy into a Knowledge value (Live Control or the Graph editor), so
    this panel has no commands."""
    name = "world_viewer"
    title = "World Viewer"
    script_path = BUILT_IN_PANEL_SCRIPT_DIRECTORY / "world_viewer.js"

    def __init__(self):
        """Nothing encoded yet."""
        # asset name -> (the GroundMap it was encoded from, PNG bytes)
        self._encoded_layers = {}
        # NOTE: asset() runs on server threads outside WebHost.lock (it is session-free), so the cache has its own lock.
        self._encode_lock = threading.Lock()

    def state(self, context: PanelContext) -> dict:
        """The map's extent (or None) and every sensed pose."""
        view = context.view
        poses = [
            {"key": key, "origin": row.origin_platform_id,
             "x": row.value.x, "y": row.value.y, "theta": row.value.theta,   # m, m, rad; world frame
             "age": None if row.timestamp is None or view.time is None else view.time - row.timestamp}   # s since written
            for key, row in sorted(view.knowledge.items()) if row.entry_type is Pose
        ]
        return {"map": _describe_map(view.ground_map), "poses": poses, "layers": list(MAP_LAYER_ASSETS)}

    def commands(self) -> dict:
        """None: the drawer's output is text the operator copies."""
        return {}

    def asset(self, asset_name: str, view: InterfaceView) -> tuple[bytes, str] | None:
        """One map layer as a PNG, encoded once per map; None with no map or an unknown layer."""
        attribute = MAP_LAYER_ASSETS.get(asset_name)
        ground_map = view.ground_map
        if attribute is None or ground_map is None:
            return None
        with self._encode_lock:
            cached = self._encoded_layers.get(asset_name)
            if cached is None or cached[0] is not ground_map:
                buffer = io.BytesIO()
                mpimg.imsave(buffer, getattr(ground_map, attribute), format="png")
                cached = (ground_map, buffer.getvalue())
                self._encoded_layers[asset_name] = cached
        return cached[1], PNG_CONTENT_TYPE


def _describe_map(ground_map: GroundMap | None) -> dict | None:
    """What the browser needs to place the map's images: its name, its extent (m, centered on
    world (0, 0), +y up), and a version that changes only when the map does."""
    if ground_map is None:
        return None
    return {"name": ground_map.name, "width_meters": ground_map.width_meters,
            "height_meters": ground_map.height_meters, "version": id(ground_map)}
