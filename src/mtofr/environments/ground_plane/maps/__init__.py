"""Image-based ground-plane maps: GroundMap plus one folder per map."""
from pathlib import Path

from .ground_map import GroundMap, TraversabilityType, RegionType


def load_map(map_name: str | None) -> GroundMap | None:
    """Loads the map folder `map_name` that sits next to this file, or None (the
    unbounded, mapless plane) when `map_name` is None."""
    return None if map_name is None else GroundMap.load(Path(__file__).parent / map_name)
