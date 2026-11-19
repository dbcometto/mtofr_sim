"""Tests for Clock: wall-clock time with an adjustable offset."""
import time
import unittest

from mtofr.clock.clock import Clock


class TestClock(unittest.TestCase):
    def test_now_defaults_to_wall_clock_time(self):
        """With no offset, now() falls between two surrounding time.time() reads."""
        clock = Clock()
        before = time.time()
        now = clock.now()
        after = time.time()
        self.assertTrue(before <= now <= after)

    def test_offset_shifts_now(self):
        """A constructor offset is added to wall time in now()."""
        clock = Clock(offset=100.0)
        self.assertAlmostEqual(clock.now(), time.time() + 100.0, delta=1.0)

    def test_set_offset_changes_subsequent_now_calls(self):
        """set_offset() applies a new offset to later now() calls."""
        clock = Clock()
        clock.set_offset(-50.0)
        self.assertAlmostEqual(clock.now(), time.time() - 50.0, delta=1.0)


class TestPeerOffset(unittest.TestCase):
    def test_unknown_peer_defaults_to_zero_offset(self):
        """A peer with no recorded offset reports 0.0."""
        clock = Clock()
        self.assertEqual(clock.peer_offset("ugv2"), 0.0)

    def test_set_peer_offset_is_scoped_to_that_peer(self):
        """set_peer_offset() affects only the named peer, leaving others at zero."""
        clock = Clock()
        clock.set_peer_offset("ugv2", 5.0)
        self.assertEqual(clock.peer_offset("ugv2"), 5.0)
        self.assertEqual(clock.peer_offset("ugv3"), 0.0)

    def test_to_local_with_unknown_peer_is_identity(self):
        """to_local() returns the timestamp unchanged for a peer with no offset."""
        clock = Clock()
        self.assertEqual(clock.to_local("ugv2", 42.0), 42.0)

    def test_to_local_subtracts_the_peer_offset(self):
        """to_local() converts a peer timestamp by subtracting that peer's offset."""
        clock = Clock()
        clock.set_peer_offset("ugv2", 5.0)
        self.assertEqual(clock.to_local("ugv2", 42.0), 37.0)


if __name__ == "__main__":
    unittest.main()