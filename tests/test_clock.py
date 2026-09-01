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


class TestPeerOffset(unittest.TestCase):
    def test_unknown_peer_defaults_to_zero_offset(self):
        clock = Clock()
        self.assertEqual(clock.peer_offset("ugv2"), 0.0)

    def test_set_peer_offset_is_scoped_to_that_peer(self):
        clock = Clock()
        clock.set_peer_offset("ugv2", 5.0)
        self.assertEqual(clock.peer_offset("ugv2"), 5.0)
        self.assertEqual(clock.peer_offset("ugv3"), 0.0)

    def test_to_local_with_unknown_peer_is_identity(self):
        clock = Clock()
        self.assertEqual(clock.to_local("ugv2", 42.0), 42.0)

    def test_to_local_subtracts_the_peer_offset(self):
        clock = Clock()
        clock.set_peer_offset("ugv2", 5.0)
        self.assertEqual(clock.to_local("ugv2", 42.0), 37.0)


if __name__ == "__main__":
    unittest.main()