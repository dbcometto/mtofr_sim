"""Tests for Clock: wall-clock time with an adjustable offset."""
import time
import unittest

from mtofr.clock.clock import Clock


class TestClock(unittest.TestCase):
    def test_now_defaults_to_wall_clock_time(self):
        clock = Clock()
        before = time.time()
        now = clock.now()
        after = time.time()
        self.assertTrue(before <= now <= after)

    def test_offset_shifts_now(self):
        clock = Clock(offset=100.0)
        self.assertAlmostEqual(clock.now(), time.time() + 100.0, delta=1.0)

    def test_set_offset_changes_subsequent_now_calls(self):
        clock = Clock()
        clock.set_offset(-50.0)
        self.assertAlmostEqual(clock.now(), time.time() - 50.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()