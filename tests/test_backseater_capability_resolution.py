"""End-to-end test: Backseater resolves Knowledge-id params against the Frontseater's
CapabilityRegistry and drives a mission graph to completion."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.knowledge.knowledge import Knowledge, Location
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class TestBackseaterCapabilityResolution(unittest.TestCase):
    def setUp(self):
        self.hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=self.hardware, nav_tolerance=0.5)
        self.knowledge = Knowledge()
        self.knowledge.add("goal", Location(2.0, 0.0))

        mission_graph = {
            "nodes": {
                "n1": {"primitives": {
                    "nav": {"type": "move_to", "params": {"target": "goal"}},
                }},
            },
            "edges": {},
            "start": "n1",
        }
        self.backseater = Backseater(frontseater=self.frontseater, knowledge=self.knowledge, mission_graph=mission_graph)

    def test_capabilities_passthrough_matches_frontseater(self):
        self.assertIs(self.backseater.capabilities(), self.frontseater.capabilities())

    def test_reaches_target_by_resolving_knowledge_id(self):
        for _ in range(500):
            self.backseater.update()
            self.frontseater.update()
            self.hardware.step_dynamics(0.1)

        self.assertEqual(self.backseater._statuses["nav"], "success")

    def test_unknown_knowledge_id_blocks_mission_without_crashing(self):
        mission_graph = {
            "nodes": {"n1": {"primitives": {
                "nav": {"type": "move_to", "params": {"target": "does_not_exist"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=self.frontseater, knowledge=self.knowledge, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater._blocked)

    def test_status_before_first_update_reports_pending(self):
        status = self.backseater.status()
        self.assertEqual(status["active_node_id"], "n1")
        self.assertFalse(status["blocked"])
        self.assertEqual(
            status["primitives"],
            {"nav": {"type": "move_to", "status": "pending", "handle": None}},
        )

    def test_status_after_actuation_reports_type_status_and_handle(self):
        self.backseater.update()
        status = self.backseater.status()
        primitive_status = status["primitives"]["nav"]
        self.assertEqual(primitive_status["type"], "move_to")
        self.assertEqual(primitive_status["status"], "received")
        self.assertIsNotNone(primitive_status["handle"])

    def test_status_reflects_blocked_mission(self):
        mission_graph = {
            "nodes": {"n1": {"primitives": {
                "nav": {"type": "move_to", "params": {"target": "does_not_exist"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=self.frontseater, knowledge=self.knowledge, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater.status()["blocked"])


if __name__ == "__main__":
    unittest.main()
