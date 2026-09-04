"""Tests for missions.py: the MissionSet enum and each mission graph's basic shape."""
import unittest

from mtofr.missions import (
    MissionSet, MissionSetConfig, MISSION_SETS,
    mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
    mission_village_ugv1, mission_village_ugv2,
)
from mtofr.world.base import Frontseater

ALL_MISSION_GRAPHS = (
    mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
    mission_village_ugv1, mission_village_ugv2,
)


class TestMissionSet(unittest.TestCase):
    def test_mission_set_has_split_wait_village_and_village_default(self):
        self.assertEqual({member.name for member in MissionSet}, {"SPLIT", "WAIT", "VILLAGE", "VILLAGE_DEFAULT"})

    def test_every_mission_set_has_a_config_with_matching_platform_keys(self):
        # mission_graphs need not cover every platform_builders key -- a platform_id
        # missing from it boots onto its own Frontseater.default_mission_graph()
        # instead (see MissionSetConfig's docstring; VILLAGE_DEFAULT exercises this).
        for mission_set in MissionSet:
            self.assertIn(mission_set, MISSION_SETS)
            config = MISSION_SETS[mission_set]
            self.assertIsInstance(config, MissionSetConfig)
            self.assertTrue(set(config.platform_builders))
            self.assertTrue(set(config.mission_graphs) <= set(config.platform_builders))

    def test_village_default_has_no_explicit_mission_graphs(self):
        config = MISSION_SETS[MissionSet.VILLAGE_DEFAULT]
        self.assertEqual(set(config.platform_builders), {"ugv1", "ugv2", "interface"})
        self.assertEqual(config.mission_graphs, {})

    def test_village_default_gives_the_interface_platform_higher_privilege(self):
        config = MISSION_SETS[MissionSet.VILLAGE_DEFAULT]
        self.assertLess(config.privilege_levels["interface"], config.privilege_levels.get("ugv1", 1))

    def test_platform_builders_produce_a_frontseater_per_platform(self):
        for mission_set in MissionSet:
            for platform_id, build_frontseater in MISSION_SETS[mission_set].platform_builders.items():
                frontseater = build_frontseater(False)
                self.addCleanup(frontseater.shutdown)
                self.assertIsInstance(frontseater, Frontseater)


class TestMissionGraphShapes(unittest.TestCase):
    def test_every_mission_graph_has_the_required_top_level_keys(self):
        for mission_graph in ALL_MISSION_GRAPHS:
            self.assertEqual(set(mission_graph), {"knowledge", "nodes", "edges", "start"})
            self.assertIn(mission_graph["start"], mission_graph["nodes"])

    def test_wait_ugv2_predeclares_the_foreign_key_it_waits_on(self):
        self.assertIn("ugv1/arrived", mission_wait_ugv2["knowledge"])
        self.assertIs(mission_wait_ugv2["knowledge"]["ugv1/arrived"]["type"], bool)

    def test_wait_ugv2s_edge_condition_references_the_foreign_key(self):
        condition = mission_wait_ugv2["edges"]["stay_at_start"][0]["condition"]
        self.assertIn("ugv1/arrived", condition)


class TestVillageMissionGraphs(unittest.TestCase):
    def test_ugv1_targets_the_map_center_building_and_a_road_waypoint(self):
        knowledge = mission_village_ugv1["knowledge"]
        self.assertIn("ugv1/road_waypoint", knowledge)
        self.assertIn("ugv1/building_target", knowledge)

    def test_ugv1_heads_to_road_before_driving_into_the_building(self):
        self.assertEqual(mission_village_ugv1["start"], "head_to_road")
        edge = mission_village_ugv1["edges"]["head_to_road"][0]
        self.assertEqual(edge["to"], "drive_into_building")

    def test_ugv1_gives_up_on_the_building_after_a_max_stuck_duration(self):
        knowledge = mission_village_ugv1["knowledge"]
        self.assertIn("ugv1/stuck_duration", knowledge)
        primitives = mission_village_ugv1["nodes"]["drive_into_building"]["primitives"]
        self.assertIn("stopwatch", (primitive["capability"] for primitive in primitives.values()))
        edge = mission_village_ugv1["edges"]["drive_into_building"][0]
        self.assertEqual(edge["condition"], ["ugv1/stuck_duration", ">", 10.0])
        self.assertEqual(edge["to"], "head_to_road")

    def test_ugv2_loops_between_road_and_clear_waypoints(self):
        self.assertIn("ugv2/road_waypoint", mission_village_ugv2["knowledge"])
        self.assertIn("ugv2/clear_waypoint", mission_village_ugv2["knowledge"])
        self.assertEqual(set(mission_village_ugv2["edges"]), {"head_to_road", "head_to_clear"})


if __name__ == "__main__":
    unittest.main()