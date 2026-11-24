"""Tests for solve_mpc() called in-process: the point-reaching cost (move_to, follow_trajectory)
and the pose-tracking cost (follow), selected by target_heading."""
import unittest

import numpy as np

from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import DEFAULT_NAV_DT, DEFAULT_NAV_HORIZON
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import (
    DEFAULT_MAX_SPEED,
    DEFAULT_MAX_STEER,
    DEFAULT_MIN_SPEED,
    DEFAULT_MIN_STEER,
    DEFAULT_WHEELBASE,
)
from mtofr.environments.ground_plane.platforms.bicycle_ugv.mpc import CONTROLS_PER_STEP, solve_mpc

STILL_SPEED = 0.1   # m/s, below which the vehicle counts as holding still


def _solve(state_xytheta: tuple, target_xy: tuple, target_heading: float | None) -> tuple:
    """One cold-started solve with the default bicycle limits and no avoid-regions; returns (vel, steer)."""
    prev_solution = np.zeros(DEFAULT_NAV_HORIZON * CONTROLS_PER_STEP)
    vel, steer, _ = solve_mpc(DEFAULT_NAV_HORIZON, DEFAULT_NAV_DT, DEFAULT_WHEELBASE, DEFAULT_MIN_SPEED,
                              DEFAULT_MAX_SPEED, DEFAULT_MIN_STEER, DEFAULT_MAX_STEER, prev_solution,
                              state_xytheta, target_xy, target_heading, [])
    return vel, steer


class TestSolveMpc(unittest.TestCase):
    def test_point_mode_drives_toward_a_target_ahead(self):
        """With no target heading, a point ahead gives forward speed (the existing cost is unchanged)."""
        vel, _ = _solve((0.0, 0.0, 0.0), (5.0, 0.0), None)
        self.assertGreater(vel, STILL_SPEED)

    def test_pose_mode_drives_toward_a_pose_ahead(self):
        """With a target heading, a pose ahead gives forward speed."""
        vel, _ = _solve((0.0, 0.0, 0.0), (2.0, 0.0), 0.0)
        self.assertGreater(vel, STILL_SPEED)

    def test_pose_mode_holds_still_at_the_target_pose(self):
        """Already at the target pose, the tracking cost commands (nearly) no motion."""
        vel, steer = _solve((0.0, 0.0, 0.0), (0.0, 0.0), 0.0)
        self.assertLess(abs(vel), STILL_SPEED)
        self.assertLess(abs(steer), STILL_SPEED)


if __name__ == "__main__":
    unittest.main()
