"""End-to-end test: Backseater resolves Memory-id params against the Frontseater's
CapabilityRegistry and drives a mission graph to completion."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.memory.memory import Memory, Location
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class TestBackseaterCapabilityResolution(unittest.TestCase):
    def setUp(self):
        self.hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=self.hardware, nav_tolerance=0.5)
        self.memory = Memory()
        self.memory.add("goal", Location(2.0, 0.0))

        mission_graph = {
            "nodes": {
                "n1": {"primitives": {
                    "nav": {"type": "move_to", "params": {"target": "goal"}},
                }},
            },
            "edges": {},
            "start": "n1",
        }
        self.backseater = Backseater(frontseater=self.frontseater, memory=self.memory, mission_graph=mission_graph)

    def test_capabilities_passthrough_matches_frontseater(self):
        self.assertIs(self.backseater.capabilities(), self.frontseater.capabilities())

    def test_reaches_target_by_resolving_memory_id(self):
        for _ in range(500):
            self.backseater.update()
            self.frontseater.update()
            self.hardware.step_dynamics(0.1)

        self.assertEqual(self.backseater._statuses["nav"], "success")

    def test_unknown_memory_id_blocks_mission_without_crashing(self):
        mission_graph = {
            "nodes": {"n1": {"primitives": {
                "nav": {"type": "move_to", "params": {"target": "does_not_exist"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=self.frontseater, memory=self.memory, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater._blocked)


if __name__ == "__main__":
    unittest.main()
