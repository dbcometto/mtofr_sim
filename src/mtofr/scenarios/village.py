"""Village scenario: exercises simple_village's road speed boost and blocked-terrain hard stop."""
from mtofr.database import Location
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps import load_map
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.viz import PlanePlotter
from mtofr.scenarios.base import ScenarioConfig


#========================================#
# Mission Graphs
#========================================#

mission_village_ugv1 = {
    "knowledge": {
        "ugv1/arrived": {"type": bool, "value": False},
        "ugv1/nav_tolerance": {"type": float, "value": 1.0},
        # A road patch east of the map's central building -- reached faster than
        # equivalent clear terrain thanks to simple_village.yaml's speed_multiplier.
        "ugv1/road_waypoint": {"type": Location, "value": Location(30.0, -6.0)},
        # Inside the central blocked building: GroundPlaneEnv will stop ugv1 dead at
        # the building's edge instead of letting it enter, so this node never
        # reports arrived -- ugv1 gives up and heads back to the road once
        # ugv1/stuck_duration exceeds the 10-second cap below instead of staying
        # stuck against the wall forever.
        "ugv1/building_target": {"type": Location, "value": Location(-3.0, -3.0)},
        "ugv1/stuck_duration": {"type": float, "value": 0.0},
    },
    "nodes": {
        "head_to_road": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv1/road_waypoint", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
        "drive_into_building": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv1/building_target", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
            "stuck_timer": {"capability": "stopwatch", "inputs": {},
                             "outputs": {"elapsed_time": "ugv1/stuck_duration"}},
        }},
    },
    "edges": {
        "head_to_road": [{"condition": ["ugv1/arrived", "==", True], "to": "drive_into_building"}],
        "drive_into_building": [{"condition": ["ugv1/stuck_duration", ">", 10.0], "to": "head_to_road"}],
    },
    "start": "head_to_road",
}


mission_village_ugv2 = {
    "knowledge": {
        "ugv2/arrived": {"type": bool, "value": False},
        "ugv2/nav_tolerance": {"type": float, "value": 1.0},
        # Alternates between a road patch (fast) and open clear terrain (slower per
        # simple_village.yaml's speed_multiplier), visualizing the speed difference.
        "ugv2/road_waypoint": {"type": Location, "value": Location(20.0, -10.0)},
        "ugv2/clear_waypoint": {"type": Location, "value": Location(45.0, -25.0)},
    },
    "nodes": {
        "head_to_road": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/road_waypoint", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
        "head_to_clear": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/clear_waypoint", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
    },
    "edges": {
        "head_to_road": [{"condition": ["ugv2/arrived", "==", True], "to": "head_to_clear"}],
        "head_to_clear": [{"condition": ["ugv2/arrived", "==", True], "to": "head_to_road"}],
    },
    "start": "head_to_road",
}







#========================================#
# Scenario
#========================================#

SCENARIO = ScenarioConfig(
    build_environment=lambda: GroundPlaneEnv(load_map("simple_village")),
    build_viewer=PlanePlotter.for_environment,
    platforms=[
        bicycle_ugv("ugv1", -3.0, -20.0, mission_graph=mission_village_ugv1),
        bicycle_ugv("ugv2", 45.0, -25.0, mission_graph=mission_village_ugv2),
    ],
)
