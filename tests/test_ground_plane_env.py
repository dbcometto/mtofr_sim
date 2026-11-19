"""Tests for GroundPlaneEnv: the passive terrain queries a GroundPlaneHardware steps itself
against -- no effects with no GroundMap, the map's own lookups with one."""
import unittest

import numpy as np

from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps.ground_map import GroundMap, TraversabilityType


def uniform_ground_map(traversability_type: TraversabilityType) -> GroundMap:
    """A 20x20m map whose every pixel is the same declared terrain type -- large
    enough that a full-speed step from the center never leaves the mapped area."""
    image = np.zeros((20, 20, 3), dtype=float)
    return GroundMap(
        name="uniform", meters_per_pixel=1.0, cosmetic_image=image, traversability_image=image,
        traversability_lookup={(0, 0, 0): traversability_type}, regions_image=image, regions_lookup={},
    )


class TestGroundPlaneEnvWithoutMap(unittest.TestCase):
    def test_speed_multiplier_is_a_no_op(self):
        """With no map, the speed multiplier is 1.0 everywhere."""
        self.assertEqual(GroundPlaneEnv().speed_multiplier_at(123.0, -45.0), 1.0)

    def test_nothing_is_blocked(self):
        """With no map, even a far-away point is not blocked."""
        self.assertFalse(GroundPlaneEnv().is_blocked(1e6, 1e6))


class TestGroundPlaneEnvWithGroundMap(unittest.TestCase):
    def test_speed_multiplier_comes_from_the_map(self):
        """The speed multiplier is the terrain type's own multiplier from the map."""
        environment = GroundPlaneEnv(uniform_ground_map(TraversabilityType("slow", blocking=False, speed_multiplier=0.5)))
        self.assertEqual(environment.speed_multiplier_at(0.0, 0.0), 0.5)

    def test_blocking_terrain_is_blocked(self):
        """A point on blocking terrain reports blocked."""
        environment = GroundPlaneEnv(uniform_ground_map(TraversabilityType("wall", blocking=True, speed_multiplier=1.0)))
        self.assertTrue(environment.is_blocked(0.0, 0.0))

    def test_clear_terrain_is_not_blocked_but_off_map_is(self):
        """Clear in-map terrain is passable, while a point off the map is blocked."""
        environment = GroundPlaneEnv(uniform_ground_map(TraversabilityType("clear", blocking=False, speed_multiplier=1.0)))
        self.assertFalse(environment.is_blocked(0.0, 0.0))
        self.assertTrue(environment.is_blocked(100.0, 100.0))


if __name__ == "__main__":
    unittest.main()
