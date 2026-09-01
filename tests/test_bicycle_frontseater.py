"""Tests for BicycleFrontseater's capability implementations (start_capability/poll_status/
cancel) exercised directly, independent of any Backseater/mission-graph driving them. A
capability now calls query()/publish() on its own Backseater, so these tests wire in a
minimal fake backseater (a plain dict-backed query/publish) instead of a full Backseater."""
import unittest

from mtofr.database import Location
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class _FakeBackseater:
    """Minimal query()/publish() stand-in over a plain dict — enough for a capability to
    read its bound inputs and write its outputs, without needing a real Backseater/Knowledge."""
    def __init__(self, knowledge: dict):
        self.knowledge = knowledge

    def query(self, database_name: str, key):
        assert database_name == "knowledge"
        return self.knowledge[key]

    def publish(self, database_name: str, key, value, timestamp=None) -> None:
        assert database_name == "knowledge"
        self.knowledge[key] = value


class TestBicycleFrontseaterCapabilities(unittest.TestCase):
    def setUp(self):
        self.hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=self.hardware)
        self.knowledge = {}
        self.frontseater.backseater = _FakeBackseater(self.knowledge)

    def tearDown(self):
        self.frontseater.shutdown()

    def _start_move_to(self, target: Location, tolerance: float, with_output=True):
        self.knowledge["target"] = target
        self.knowledge["tolerance"] = tolerance
        outputs = {"arrived": "arrived"} if with_output else {}
        return self.frontseater.start_capability("move_to", {"target": "target", "tolerance": "tolerance"}, outputs)

    def _start_avoid(self, point: Location, radius: float, with_output=True):
        self.knowledge["point"] = point
        self.knowledge["radius"] = radius
        outputs = {"registered": "registered"} if with_output else {}
        return self.frontseater.start_capability("avoid", {"point": "point", "radius": "radius"}, outputs)

    def test_capabilities_advertises_move_to_and_avoid(self):
        registry = self.frontseater.capabilities()
        self.assertIsNotNone(registry.get("move_to"))
        self.assertIsNotNone(registry.get("avoid"))

    def test_start_capability_move_to_returns_a_pollable_handle(self):
        handle = self._start_move_to(Location(5.0, 0.0), 0.5)
        self.assertIn(self.frontseater.poll_status(handle)["status"], ("in_progress", "success"))

    def test_start_capability_avoid_is_instantaneous_success(self):
        handle = self._start_avoid(Location(0.0, 0.0), 1.0)
        self.assertEqual(self.frontseater.poll_status(handle)["status"], "success")

    def test_start_capability_unknown_capability_raises(self):
        with self.assertRaises(ValueError):
            self.frontseater.start_capability("fly", {}, {})

    def test_poll_status_reports_in_progress_while_far_from_target(self):
        handle = self._start_move_to(Location(100.0, 0.0), 0.5)
        self.assertEqual(self.frontseater.poll_status(handle)["status"], "in_progress")

    def test_poll_status_reports_arrived_false_while_far_from_target(self):
        handle = self._start_move_to(Location(100.0, 0.0), 0.5)
        self.assertEqual(self.frontseater.poll_status(handle)["outputs"]["arrived"], False)

    def test_poll_status_reports_success_once_within_tolerance(self):
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        handle = self._start_move_to(Location(0.1, 0.0), 0.5)
        self.assertEqual(self.frontseater.poll_status(handle)["status"], "success")

    def test_poll_status_reports_arrived_true_once_within_tolerance(self):
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        handle = self._start_move_to(Location(0.1, 0.0), 0.5)
        self.assertEqual(self.frontseater.poll_status(handle)["outputs"]["arrived"], True)

    def test_poll_status_publishes_arrived_to_its_bound_knowledge_key(self):
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        handle = self._start_move_to(Location(0.1, 0.0), 0.5)
        self.frontseater.poll_status(handle)
        self.assertTrue(self.knowledge["arrived"])

    def test_poll_status_reports_registered_true_for_avoid(self):
        handle = self._start_avoid(Location(0.0, 0.0), 1.0)
        self.assertEqual(self.frontseater.poll_status(handle)["outputs"]["registered"], True)

    def test_poll_status_publishes_registered_to_its_bound_knowledge_key(self):
        handle = self._start_avoid(Location(0.0, 0.0), 1.0)
        self.frontseater.poll_status(handle)
        self.assertTrue(self.knowledge["registered"])

    def test_poll_status_for_unknown_handle_reports_fail(self):
        self.assertEqual(self.frontseater.poll_status("nonexistent-handle")["status"], "fail")

    def test_move_to_reads_a_retargeted_knowledge_key_on_the_next_poll(self):
        handle = self._start_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater.poll_status(handle)
        self.knowledge["target"] = Location(0.0, 0.0)
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self.assertEqual(self.frontseater.poll_status(handle)["status"], "success")

    def test_cancel_active_move_to_marks_it_failed_and_clears_target(self):
        handle = self._start_move_to(Location(5.0, 0.0), 0.5)
        self.frontseater.cancel(handle)
        self.assertEqual(self.frontseater.poll_status(handle)["status"], "fail")
        self.assertIsNone(self.frontseater._active_target)

    def test_compute_controls_is_idle_with_no_active_target(self):
        controls = self.frontseater.compute_controls(self.hardware.read_state())
        self.assertEqual(controls, {"vel": 0.0, "steer": 0.0})


if __name__ == "__main__":
    unittest.main()