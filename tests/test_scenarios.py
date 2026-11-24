"""Tests for mtofr.scenarios: scenario discovery, each ScenarioConfig, and each mission graph's basic shape."""
import unittest

from mtofr.core.environment import Environment
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.viz import PlanePlotter
from mtofr.platform.frontseater import Frontseater
from mtofr.platform.platform import PlatformSpec
from mtofr.scenarios import ScenarioConfig, SCENARIOS
from mtofr.scenarios.split import mission_split_ugv1, mission_split_ugv2
from mtofr.scenarios.village import mission_village_ugv1, mission_village_ugv2
from mtofr.scenarios.wait import mission_wait_ugv1, mission_wait_ugv2
from mtofr.viz.base import EnvironmentViewer

ALL_MISSION_GRAPHS = (
    mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
    mission_village_ugv1, mission_village_ugv2,
)


class TestScenarios(unittest.TestCase):
    def test_discovery_finds_every_scenario_file_by_name(self):
        """SCENARIOS holds exactly the scenario files, keyed by file name (base.py excluded)."""
        self.assertEqual(set(SCENARIOS), {"split", "wait", "village", "village_default"})

    def test_every_scenario_has_a_config_with_at_least_one_platform(self):
        """Every scenario is a ScenarioConfig with a non-empty list of PlatformSpecs."""
        for config in SCENARIOS.values():
            self.assertIsInstance(config, ScenarioConfig)
            self.assertTrue(config.platforms)
            for spec in config.platforms:
                self.assertIsInstance(spec, PlatformSpec)

    def test_every_scenario_builds_its_environment_and_viewer(self):
        """Every scenario's builders produce an Environment and an EnvironmentViewer over it."""
        for config in SCENARIOS.values():
            environment = config.build_environment()
            self.assertIsInstance(environment, Environment)
            self.assertIsInstance(config.build_viewer(environment), EnvironmentViewer)

    def test_ground_plane_viewer_draws_the_environments_own_map(self):
        """PlanePlotter.for_environment() reuses the environment's GroundMap rather than loading another."""
        environment = SCENARIOS["village"].build_environment()
        viewer = PlanePlotter.for_environment(environment)
        self.assertIsNotNone(environment.ground_map)
        self.assertIs(viewer.ground_map, environment.ground_map)

    def test_duplicate_platform_ids_are_rejected(self):
        """A ScenarioConfig with two specs sharing a platform_id raises ValueError."""
        with self.assertRaises(ValueError):
            ScenarioConfig(build_environment=lambda: None, build_viewer=lambda environment: None,
                           platforms=[bicycle_ugv("ugv1", 0.0, 0.0), bicycle_ugv("ugv1", 1.0, 1.0)])

    def test_village_default_has_no_explicit_mission_graphs(self):
        """VILLAGE_DEFAULT has ugv1, ugv2, and interface, none with an explicit mission graph."""
        # A spec with no mission_graph boots onto its own Frontseater.default_mission_graph().
        config = SCENARIOS["village_default"]
        self.assertEqual({spec.platform_id for spec in config.platforms}, {"ugv1", "ugv2", "interface"})
        self.assertTrue(all(spec.mission_graph is None for spec in config.platforms))

    def test_village_default_gives_the_interface_platform_higher_privilege(self):
        """In VILLAGE_DEFAULT, the interface's privilege level is lower (more privileged) than a UGV's."""
        specs = {spec.platform_id: spec for spec in SCENARIOS["village_default"].platforms}
        self.assertLess(specs["interface"].privilege_level, specs["ugv1"].privilege_level)

    def test_every_spec_builds_a_frontseater(self):
        """Every spec in every scenario builds a Frontseater."""
        for config in SCENARIOS.values():
            for spec in config.platforms:
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
        capability_requests = mission_village_ugv1["nodes"]["drive_into_building"]["capabilities"]
        self.assertIn("stopwatch", (capability_request["capability"] for capability_request in capability_requests.values()))
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
