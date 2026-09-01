"""Tests for GroundMap: loading a map directory and sampling world-meters
coordinates against its traversability layer."""
import unittest
from pathlib import Path

import mtofr.maps as maps_package
from mtofr.maps.ground_map import GroundMap, TraversabilityType, RegionType, _hex_to_rgb, _nearest_lookup

MAPS_DIRECTORY = Path(maps_package.__file__).parent


class TestGroundMapLoadBlank(unittest.TestCase):
    def setUp(self):
        self.ground_map = GroundMap.load(MAPS_DIRECTORY / "blank")

    def test_loads_name_and_extent(self):
        self.assertEqual(self.ground_map.name, "blank")
        self.assertAlmostEqual(self.ground_map.width_meters, 128.0)
        self.assertAlmostEqual(self.ground_map.height_meters, 128.0)

    def test_center_is_clear_and_not_blocked(self):
        self.assertFalse(self.ground_map.is_blocked(0.0, 0.0))
        self.assertAlmostEqual(self.ground_map.speed_multiplier_at(0.0, 0.0), 1.0)

    def test_off_map_is_blocked(self):
        self.assertTrue(self.ground_map.is_blocked(1000.0, 1000.0))
        self.assertAlmostEqual(self.ground_map.speed_multiplier_at(1000.0, 1000.0), 1.0)

    def test_edge_of_map_within_bounds_is_not_blocked(self):
        half_width = self.ground_map.width_meters / 2
        self.assertFalse(self.ground_map.is_blocked(half_width - 1.0, 0.0))


class TestGroundMapLoadSimpleVillage(unittest.TestCase):
    def setUp(self):
        self.ground_map = GroundMap.load(MAPS_DIRECTORY / "simple_village")

    def test_declares_blocked_road_and_clear(self):
        names = {entry.name for entry in self.ground_map.traversability_lookup.values()}
        self.assertEqual(names, {"blocked", "road", "clear"})

    def test_blocked_terrain_type_is_blocking(self):
        blocked_type = next(t for t in self.ground_map.traversability_lookup.values() if t.name == "blocked")
        self.assertTrue(blocked_type.blocking)

    def test_road_is_fastest_terrain(self):
        road_type = next(t for t in self.ground_map.traversability_lookup.values() if t.name == "road")
        clear_type = next(t for t in self.ground_map.traversability_lookup.values() if t.name == "clear")
        self.assertEqual(road_type.speed_multiplier, 1.0)
        self.assertLess(clear_type.speed_multiplier, road_type.speed_multiplier)

    def test_regions_are_loaded(self):
        names = {entry.name for entry in self.ground_map.regions_lookup.values()}
        self.assertEqual(names, {"A", "B", "C", "D"})


class TestGroundMapHelpers(unittest.TestCase):
    def test_hex_to_rgb(self):
        self.assertEqual(_hex_to_rgb("#ff0000"), (255, 0, 0))
        self.assertEqual(_hex_to_rgb("00ff00"), (0, 255, 0))

    def test_nearest_lookup_exact_match(self):
        lookup = {(255, 0, 0): "red", (0, 255, 0): "green"}
        self.assertEqual(_nearest_lookup((255, 0, 0), lookup), "red")

    def test_nearest_lookup_snaps_to_closest_color(self):
        lookup = {(255, 0, 0): "red", (0, 255, 0): "green"}
        self.assertEqual(_nearest_lookup((250, 5, 5), lookup), "red")

    def test_nearest_lookup_empty_returns_none(self):
        self.assertIsNone(_nearest_lookup((1, 2, 3), {}))


class TestGroundMapConstruction(unittest.TestCase):
    """Exercises the plain constructor directly, without touching disk, to isolate
    coordinate-conversion behavior from yaml/image loading."""
    def setUp(self):
        import numpy as np
        # 4x4 traversability image: top-left quadrant is red ("blocked"), rest blue ("clear").
        image = np.zeros((4, 4, 3), dtype=float)
        image[:, :] = (0, 0, 1)
        image[0:2, 0:2] = (1, 0, 0)
        self.ground_map = GroundMap(
            name="test", meters_per_pixel=1.0, cosmetic_image=image, traversability_image=image,
            traversability_lookup={
                (255, 0, 0): TraversabilityType(name="blocked", blocking=True, speed_multiplier=0.0),
                (0, 0, 255): TraversabilityType(name="clear", blocking=False, speed_multiplier=1.0),
            },
            regions_image=image, regions_lookup={},
        )

    def test_top_left_quadrant_in_world_frame_is_the_upper_left_of_the_image(self):
        # 4x4 at 1 m/pixel -> 4x4m map, centered: world (-1.5, 1.5) is row 0, col 0.
        self.assertTrue(self.ground_map.is_blocked(-1.5, 1.5))

    def test_bottom_right_quadrant_is_clear(self):
        self.assertFalse(self.ground_map.is_blocked(1.5, -1.5))


if __name__ == "__main__":
    unittest.main()