"""Tests for GroundPlaneEnv: steps dynamics for every hardware instance it's given,
and (with a GroundMap) applies terrain speed multipliers and blocks motion into
blocking cells."""
import unittest

from mtofr.world.base import WorldState
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.maps.ground_map import GroundMap, TraversabilityType


class FakeHardware:
    def __init__(self):
        self.step_dynamics_called_with = None

    def step_dynamics(self, dt):
        self.step_dynamics_called_with = dt


class TestGroundPlaneEnv(unittest.TestCase):
    def test_step_dynamics_all_steps_every_hardware_instance(self):
        hardware_a, hardware_b = FakeHardware(), FakeHardware()
        GroundPlaneEnv().step_dynamics_all({"a": hardware_a, "b": hardware_b}, dt=0.1)
        self.assertEqual(hardware_a.step_dynamics_called_with, 0.1)
        self.assertEqual(hardware_b.step_dynamics_called_with, 0.1)

    def test_step_dynamics_all_with_no_hardware_does_not_raise(self):
        GroundPlaneEnv().step_dynamics_all({}, dt=0.1)


def _uniform_ground_map(traversability_type: TraversabilityType) -> GroundMap:
    """A 20x20m map whose every pixel is the same declared terrain type -- large
    enough that a full-speed step from the center never leaves the mapped area."""
    import numpy as np
    image = np.zeros((20, 20, 3), dtype=float)
    return GroundMap(
        name="uniform", meters_per_pixel=1.0, cosmetic_image=image, traversability_image=image,
        traversability_lookup={(0, 0, 0): traversability_type}, regions_image=image, regions_lookup={},
    )


class TestGroundPlaneEnvWithGroundMap(unittest.TestCase):
    def test_speed_multiplier_scales_max_speed(self):
        ground_map = _uniform_ground_map(TraversabilityType(name="slow", blocking=False, speed_multiplier=0.5))
        hardware = BicycleHardware()
        hardware.state = WorldState(x=0.0, y=0.0, theta=0.0)
        hardware.send_controls({"vel": 999.0, "steer": 0.0})

        GroundPlaneEnv(ground_map=ground_map).step_dynamics_all({"ugv1": hardware}, dt=1.0)

        self.assertAlmostEqual(hardware.state.x, hardware.max_speed * 0.5)

    def test_blocking_terrain_stops_the_vehicle_at_its_previous_position(self):
        ground_map = _uniform_ground_map(TraversabilityType(name="wall", blocking=True, speed_multiplier=1.0))
        hardware = BicycleHardware()
        hardware.state = WorldState(x=0.0, y=0.0, theta=0.0)
        hardware.send_controls({"vel": 1.0, "steer": 0.0})

        GroundPlaneEnv(ground_map=ground_map).step_dynamics_all({"ugv1": hardware}, dt=1.0)

        self.assertAlmostEqual(hardware.state.x, 0.0)
        self.assertAlmostEqual(hardware.state.y, 0.0)
        self.assertAlmostEqual(hardware.state.vx, 0.0)

    def test_blocking_terrain_still_advances_time(self):
        ground_map = _uniform_ground_map(TraversabilityType(name="wall", blocking=True, speed_multiplier=1.0))
        hardware = BicycleHardware()
        hardware.state = WorldState(t=1.0, x=0.0, y=0.0, theta=0.0)
        hardware.send_controls({"vel": 1.0, "steer": 0.0})

        GroundPlaneEnv(ground_map=ground_map).step_dynamics_all({"ugv1": hardware}, dt=0.5)

        self.assertAlmostEqual(hardware.state.t, 1.5)

    def test_off_map_position_is_blocked(self):
        ground_map = _uniform_ground_map(TraversabilityType(name="clear", blocking=False, speed_multiplier=1.0))
        hardware = BicycleHardware()
        hardware.state = WorldState(x=100.0, y=100.0, theta=0.0)   # already off the 4x4m map
        hardware.send_controls({"vel": 1.0, "steer": 0.0})

        GroundPlaneEnv(ground_map=ground_map).step_dynamics_all({"ugv1": hardware}, dt=1.0)

        self.assertAlmostEqual(hardware.state.x, 100.0)
        self.assertAlmostEqual(hardware.state.vx, 0.0)


if __name__ == "__main__":
    unittest.main()
