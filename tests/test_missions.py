"""Tests for missions.py: the MissionSet enum and each mission graph's basic shape."""
import unittest

from mtofr.missions import (
    MissionSet, MissionSetConfig, MISSION_SETS,
    mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
    mission_village_ugv1, mission_village_ugv2,
)
from mtofr.world.base import Frontseater
from mtofr.world.platform import PlatformSpec
from mtofr.world.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv

ALL_MISSION_GRAPHS = (
    mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
    mission_village_ugv1, mission_village_ugv2,
)


class TestMissionSet(unittest.TestCase):
    def test_mission_set_has_split_wait_village_and_village_default(self):
        """MissionSet has exactly the SPLIT, WAIT, VILLAGE, and VILLAGE_DEFAULT members."""
        self.assertEqual({member.name for member in MissionSet}, {"SPLIT", "WAIT", "VILLAGE", "VILLAGE_DEFAULT"})

    def test_every_mission_set_has_a_config_with_at_least_one_platform(self):
        """Every MissionSet maps to a MissionSetConfig with a non-empty list of PlatformSpecs."""
        for mission_set in MissionSet:
            self.assertIn(mission_set, MISSION_SETS)
            config = MISSION_SETS[mission_set]
            self.assertIsInstance(config, MissionSetConfig)
            self.assertTrue(config.platforms)
            for spec in config.platforms:
                self.assertIsInstance(spec, PlatformSpec)

    def test_duplicate_platform_ids_are_rejected(self):
        """A MissionSetConfig with two specs sharing a platform_id raises ValueError."""
        with self.assertRaises(ValueError):
            MissionSetConfig(map_name=None, platforms=[bicycle_ugv("ugv1", 0.0, 0.0), bicycle_ugv("ugv1", 1.0, 1.0)])

    def test_village_default_has_no_explicit_mission_graphs(self):
        """VILLAGE_DEFAULT has ugv1, ugv2, and interface, none with an explicit mission graph."""
        # A spec with no mission_graph boots onto its own Frontseater.default_mission_graph().
        config = MISSION_SETS[MissionSet.VILLAGE_DEFAULT]
        self.assertEqual({spec.platform_id for spec in config.platforms}, {"ugv1", "ugv2", "interface"})
        self.assertTrue(all(spec.mission_graph is None for spec in config.platforms))

    def test_village_default_gives_the_interface_platform_higher_privilege(self):
        """In VILLAGE_DEFAULT, the interface's privilege level is lower (more privileged) than a UGV's."""
        specs = {spec.platform_id: spec for spec in MISSION_SETS[MissionSet.VILLAGE_DEFAULT].platforms}
        self.assertLess(specs["interface"].privilege_level, specs["ugv1"].privilege_level)

    def test_every_spec_builds_a_frontseater(self):
        """Every spec in every mission set builds a Frontseater."""
        for mission_set in MissionSet:
            for spec in MISSION_SETS[mission_set].platforms:
                frontseater = spec.build_frontseater(False)
                self.addCleanup(frontseater.shutdown)
                self.assertIsInstance(frontseater, Frontseater)


class TestMissionGraphShapes(unittest.TestCase):
    def test_every_mission_graph_has_the_required_top_level_keys(self):
        """Every example graph has exactly the four top-level keys, and its start node exists."""
        for mission_graph in ALL_MISSION_GRAPHS:
            self.assertEqual(set(mission_graph), {"knowledge", "nodes", "edges", "start"})
            self.assertIn(mission_graph["start"], mission_graph["nodes"])

    def test_wait_ugv2_predeclares_the_foreign_key_it_waits_on(self):
        """ugv2's WAIT graph declares ugv1's arrived key as a bool."""
        self.assertIn("ugv1/arrived", mission_wait_ugv2["knowledge"])
        self.assertIs(mission_wait_ugv2["knowledge"]["ugv1/arrived"]["type"], bool)

    def test_wait_ugv2s_edge_condition_references_the_foreign_key(self):
        """ugv2's WAIT edge out of its start node conditions on ugv1's arrived key."""
        condition = mission_wait_ugv2["edges"]["stay_at_start"][0]["condition"]
        self.assertIn("ugv1/arrived", condition)


class TestVillageMissionGraphs(unittest.TestCase):
    def test_ugv1_targets_the_map_center_building_and_a_road_waypoint(self):
        """ugv1's village graph declares a road waypoint and a building target."""
        knowledge = mission_village_ugv1["knowledge"]
        self.assertIn("ugv1/road_waypoint", knowledge)
        self.assertIn("ugv1/building_target", knowledge)

    def test_ugv1_heads_to_road_before_driving_into_the_building(self):
        """ugv1 starts at head_to_road, whose edge leads to drive_into_building."""
        self.assertEqual(mission_village_ugv1["start"], "head_to_road")
        edge = mission_village_ugv1["edges"]["head_to_road"][0]
        self.assertEqual(edge["to"], "drive_into_building")

    def test_ugv1_gives_up_on_the_building_after_a_max_stuck_duration(self):
        """drive_into_building runs a stopwatch and returns to head_to_road once stuck over 10 s."""
        knowledge = mission_village_ugv1["knowledge"]
        self.assertIn("ugv1/stuck_duration", knowledge)
        primitives = mission_village_ugv1["nodes"]["drive_into_building"]["primitives"]
        self.assertIn("stopwatch", (primitive["capability"] for primitive in primitives.values()))
        edge = mission_village_ugv1["edges"]["drive_into_building"][0]
        self.assertEqual(edge["condition"], ["ugv1/stuck_duration", ">", 10.0])
        self.assertEqual(edge["to"], "head_to_road")

    def test_ugv2_loops_between_road_and_clear_waypoints(self):
        """ugv2's village graph declares road and clear waypoints and has edges out of both nodes."""
        self.assertIn("ugv2/road_waypoint", mission_village_ugv2["knowledge"])
        self.assertIn("ugv2/clear_waypoint", mission_village_ugv2["knowledge"])
        self.assertEqual(set(mission_village_ugv2["edges"]), {"head_to_road", "head_to_clear"})


if __name__ == "__main__":
    unittest.main()