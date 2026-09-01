"""Defines GroundMap: an image-based cosmetic/traversability/regions map."""
from dataclasses import dataclass
from pathlib import Path

import matplotlib.image as mpimg
import yaml


@dataclass
class TraversabilityType:
    """One traversability color's terrain properties."""
    name: str
    blocking: bool
    speed_multiplier: float


@dataclass
class RegionType:
    """One region color's label and pixel-space center (top-left origin), for
    display only -- no functional region-membership query exists yet."""
    name: str
    center_x: float
    center_y: float


# Returned by traversability_at() for an in-bounds pixel color that doesn't match
# any declared traversability color -- passable, no speed effect.
_DEFAULT_TRAVERSABILITY = TraversabilityType(name="unmapped", blocking=False, speed_multiplier=1.0)


class GroundMap:
    """An image-based map for the ground_plane environment: a cosmetic layer (always
    shown), a traversability layer (blocks motion / scales max speed), and a regions
    layer (currently display-only), all aligned via a shared meters_per_pixel. World
    coordinates are centered on the map (x=0, y=0 at the image center) with y increasing
    upward, matching the bicycle model's existing math convention -- the opposite of
    image row order, so pixel sampling flips vertically. A pixel color with no exact
    match in a map's declared palette is snapped to its nearest declared color, since
    PNG anti-aliasing blends a few pixels along every color boundary."""

    def __init__(self, name: str, meters_per_pixel: float, cosmetic_image, traversability_image,
                 traversability_lookup: dict, regions_image, regions_lookup: dict):
        self.name = name
        self.meters_per_pixel = meters_per_pixel
        self.cosmetic_image = cosmetic_image
        self.traversability_image = traversability_image
        self.traversability_lookup = traversability_lookup   # (r, g, b) 0-255 -> TraversabilityType
        self.regions_image = regions_image
        self.regions_lookup = regions_lookup   # (r, g, b) 0-255 -> RegionType

        height_px, width_px = traversability_image.shape[:2]
        self.width_meters = width_px * meters_per_pixel
        self.height_meters = height_px * meters_per_pixel

    #=====# Loading #=====#
    @classmethod
    def load(cls, map_directory: str) -> "GroundMap":
        """Loads a map from a directory containing one yaml file plus the cosmetic/
        traversability/regions PNGs it names via its *_image_path fields."""
        map_directory = Path(map_directory)
        yaml_path = next(map_directory.glob("*.yaml"))
        with open(yaml_path) as yaml_file:
            spec = yaml.safe_load(yaml_file)

        map_section = spec["map"]
        cosmetic_image = mpimg.imread(map_directory / f"{map_section['cosmetic_image_path']}.png")
        traversability_image = mpimg.imread(map_directory / f"{map_section['traversability_image_path']}.png")
        regions_image = mpimg.imread(map_directory / f"{map_section['regions_image_path']}.png")

        traversability_lookup = {
            _hex_to_rgb(color): TraversabilityType(**fields)
            for color, fields in (spec.get("traversability") or {}).items()
        }
        regions_lookup = {
            _hex_to_rgb(color): RegionType(**fields)
            for color, fields in (spec.get("regions") or {}).items()
        }

        return cls(
            name=map_section["name"], meters_per_pixel=map_section["meters_per_pixel"],
            cosmetic_image=cosmetic_image, traversability_image=traversability_image,
            traversability_lookup=traversability_lookup, regions_image=regions_image,
            regions_lookup=regions_lookup,
        )

    #=====# Sampling #=====#
    def _pixel_indices_at(self, x: float, y: float) -> tuple | None:
        """Converts world meters to (row, column) indices into the map's raster
        images, or None if (x, y) falls outside the mapped area."""
        height_px, width_px = self.traversability_image.shape[:2]
        column = int((x + self.width_meters / 2) / self.meters_per_pixel)
        row_from_bottom = int((y + self.height_meters / 2) / self.meters_per_pixel)
        row = height_px - 1 - row_from_bottom
        if 0 <= row < height_px and 0 <= column < width_px:
            return row, column
        return None

    def traversability_at(self, x: float, y: float) -> TraversabilityType | None:
        """Returns the TraversabilityType at (x, y), or None if off the mapped area."""
        indices = self._pixel_indices_at(x, y)
        if indices is None:
            return None
        rgb = _sample_rgb(self.traversability_image, *indices)
        return _nearest_lookup(rgb, self.traversability_lookup) or _DEFAULT_TRAVERSABILITY

    def is_blocked(self, x: float, y: float) -> bool:
        """True if (x, y) is off the mapped area or a declared blocking terrain type."""
        terrain = self.traversability_at(x, y)
        return terrain is None or terrain.blocking

    def speed_multiplier_at(self, x: float, y: float) -> float:
        """Returns the speed multiplier at (x, y); 1.0 (no effect) when off-map."""
        terrain = self.traversability_at(x, y)
        return 1.0 if terrain is None else terrain.speed_multiplier


def _hex_to_rgb(hex_color: str) -> tuple:
    """Converts "#rrggbb" to an (r, g, b) tuple of 0-255 ints."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[index:index + 2], 16) for index in (0, 2, 4))


def _sample_rgb(image, row: int, column: int) -> tuple:
    """Reads image[row, column]'s RGB channels (dropping alpha) as 0-255 ints,
    regardless of whether the image array is stored as floats in [0, 1] or uint8."""
    pixel = image[row, column]
    if pixel.dtype.kind == "f":
        return tuple(int(round(channel * 255)) for channel in pixel[:3])
    return tuple(int(channel) for channel in pixel[:3])


def _nearest_lookup(rgb: tuple, lookup: dict):
    """Returns lookup[rgb] on an exact match, otherwise the value for the nearest
    declared color by squared RGB distance -- absorbs PNG anti-aliasing at color
    boundaries. Returns None if lookup is empty."""
    if rgb in lookup:
        return lookup[rgb]
    if not lookup:
        return None
    nearest_color = min(lookup, key=lambda color: sum((a - b) ** 2 for a, b in zip(color, rgb)))
    return lookup[nearest_color]