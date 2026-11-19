"""Tests for BicycleHardware's dynamics model: straight-line motion, turning, and
control clamping to the platform's speed/steer limits."""
import unittest

from mtofr.world.base import WorldState
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware


class TestBicycleHardwareDynamics(unittest.TestCase):
    def setUp(self):
        """Build a default BicycleHardware."""
        self.hardware = BicycleHardware()

    def test_zero_controls_leave_position_unchanged(self):
        """Zero speed and steer leave x and y unchanged."""
        start = WorldState(x=1.0, y=2.0, theta=0.0)
        end = self.hardware.calculate_dynamics(start, {"vel": 0.0, "steer": 0.0}, dt=0.1)
        self.assertAlmostEqual(end.x, 1.0)
        self.assertAlmostEqual(end.y, 2.0)

    def test_straight_forward_motion_moves_along_current_heading(self):
        """With zero steer, the vehicle travels vel*dt along its heading without turning."""
        start = WorldState(x=0.0, y=0.0, theta=0.0)
        end = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": 0.0}, dt=1.0)
        self.assertAlmostEqual(end.x, 1.0)
        self.assertAlmostEqual(end.y, 0.0)
        self.assertAlmostEqual(end.theta, 0.0)

    def test_positive_steer_turns_left(self):
        """Positive steer increases heading (counterclockwise)."""
        start = WorldState(x=0.0, y=0.0, theta=0.0)
        end = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": 0.2}, dt=0.1)
        self.assertGreater(end.theta, 0.0)

    def test_negative_steer_turns_right(self):
        """Negative steer decreases heading (clockwise)."""
        start = WorldState(x=0.0, y=0.0, theta=0.0)
        end = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": -0.2}, dt=0.1)
        self.assertLess(end.theta, 0.0)

    def test_speed_is_clamped_to_max(self):
        """A commanded speed above max_speed is clamped to it."""
        start = WorldState()
        end = self.hardware.calculate_dynamics(start, {"vel": 999.0, "steer": 0.0}, dt=1.0)
        self.assertAlmostEqual(end.x, self.hardware.max_speed)

    def test_max_speed_multiplier_scales_the_clamp(self):
        """max_speed_multiplier scales the speed clamp."""
        start = WorldState()
        end = self.hardware.calculate_dynamics(start, {"vel": 999.0, "steer": 0.0}, dt=1.0,
                                                max_speed_multiplier=0.5)
        self.assertAlmostEqual(end.x, self.hardware.max_speed * 0.5)

    def test_default_max_speed_multiplier_is_a_no_op(self):
        """Omitting max_speed_multiplier gives the same result as passing 1.0."""
        start = WorldState()
        with_default = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": 0.0}, dt=1.0)
        with_explicit_one = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": 0.0}, dt=1.0,
                                                               max_speed_multiplier=1.0)
        self.assertAlmostEqual(with_default.x, with_explicit_one.x)

    def test_steer_is_clamped_to_bounds(self):
        """An oversized steer command turns exactly as much as max_steer."""
        start = WorldState()
        clamped = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": 999.0}, dt=0.1)
        at_max = self.hardware.calculate_dynamics(start, {"vel": 1.0, "steer": self.hardware.max_steer}, dt=0.1)
        self.assertAlmostEqual(clamped.theta, at_max.theta)

    def test_time_advances_by_dt(self):
        """The returned state's time is the start time plus dt."""
        start = WorldState(t=5.0)
        end = self.hardware.calculate_dynamics(start, {"vel": 0.0, "steer": 0.0}, dt=0.25)
        self.assertAlmostEqual(end.t, 5.25)

    def test_step_dynamics_uses_pending_controls_sent_via_send_controls(self):
        """step_dynamics() applies the controls last passed to send_controls()."""
        self.hardware.state = WorldState(x=0.0, y=0.0, theta=0.0)
        self.hardware.send_controls({"vel": 1.0, "steer": 0.0})
        self.hardware.step_dynamics(1.0, GroundPlaneEnv())
        self.assertAlmostEqual(self.hardware.state.x, 1.0)

    def test_read_state_returns_current_state_via_sensor(self):
        """read_state() reports the hardware's current position."""
        self.hardware.state = WorldState(x=3.0, y=4.0)
        state = self.hardware.read_state()
        self.assertEqual((state.x, state.y), (3.0, 4.0))


if __name__ == "__main__":
    unittest.main()
