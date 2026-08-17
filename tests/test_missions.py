"""Tests for missions.py: the MissionSet enum and each mission graph's basic shape."""
import unittest

from mtofr.missions import (
    MissionSet, mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
)


class TestMissionSet(unittest.TestCase):
    def test_mission_set_has_split_and_wait(self):
        self.assertEqual({member.name for member in MissionSet}, {"SPLIT", "WAIT"})


class TestMissionGraphShapes(unittest.TestCase):
    def test_every_mission_graph_has_the_required_top_level_keys(self):
        for mission_graph in (mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2):
            self.assertEqual(set(mission_graph), {"knowledge", "nodes", "edges", "start"})
            self.assertIn(mission_graph["start"], mission_graph["nodes"])

    def test_wait_ugv2_predeclares_the_foreign_key_it_waits_on(self):
        self.assertIn("ugv1/arrived", mission_wait_ugv2["knowledge"])
        self.assertIs(mission_wait_ugv2["knowledge"]["ugv1/arrived"]["type"], bool)

    def test_wait_ugv2s_edge_condition_references_the_foreign_key(self):
        condition = mission_wait_ugv2["edges"]["stay_at_start"][0]["condition"]
        self.assertIn("ugv1/arrived", condition)


if __name__ == "__main__":
    unittest.main()