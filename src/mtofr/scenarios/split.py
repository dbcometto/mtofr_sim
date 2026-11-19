"""Split scenario: each platform runs its own independent loop on the blank map, with no
cross-platform coordination."""
from mtofr.database import Location
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps import load_map
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.viz import PlanePlotter
from mtofr.scenarios.base import ScenarioConfig


#========================================#
# Mission Graphs
#========================================#

mission_split_ugv1 = {
    "knowledge": {
        "ugv1/arrived": {"type": bool, "value": False},
        "ugv1/nav_tolerance": {"type": float, "value": 0.5},
        "ugv1/avoid_radius_small": {"type": float, "value": 2.0},
        "ugv1/avoid_radius_large": {"type": float, "value": 3.0},
        "east": {"type": Location, "value": Location(7.0, 7.0)},
        "west": {"type": Location, "value": Location(-7.0, 7.0)},
        "southeast": {"type": Location, "value": Location(7.0, -7.0)},
        "top_center": {"type": Location, "value": Location(0.0, 9.0)},
        "north_of_origin": {"type": Location, "value": Location(0.0, 2.0)},
    },
    "nodes": {
        "head_east": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "east", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
        "loop_west": {"capabilities": {
            "avoid_top_center": {"capability": "avoid", "inputs": {"point": "top_center", "radius": "ugv1/avoid_radius_large"}},
            "nav": {"capability": "move_to", "inputs": {"target": "west", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
        "return_southeast": {"capabilities": {
            "avoid_origin": {"capability": "avoid", "inputs": {"point": "north_of_origin", "radius": "ugv1/avoid_radius_small"}},
            "nav": {"capability": "move_to", "inputs": {"target": "southeast", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
    },
    "edges": {
        "head_east": [{"condition": ["ugv1/arrived", "==", True], "to": "loop_west"}],
        "loop_west": [{"condition": ["ugv1/arrived", "==", True], "to": "return_southeast"}],
        "return_southeast": [{"condition": ["ugv1/arrived", "==", True], "to": "head_east"}],
    },
    "start": "head_east",
}


mission_split_ugv2 = {
    "knowledge": {
        "ugv2/arrived": {"type": bool, "value": False},
        "ugv2/nav_tolerance": {"type": float, "value": 0.5},
        "ugv2/avoid_radius": {"type": float, "value": 2.5},
        "north_point": {"type": Location, "value": Location(0.0, 8.0)},
        "south_point": {"type": Location, "value": Location(0.0, -8.0)},
        "east_of_origin": {"type": Location, "value": Location(3.0, 0.0)},
    },
    "nodes": {
        "head_north": {"capabilities": {
            "avoid_east_of_origin": {"capability": "avoid", "inputs": {"point": "east_of_origin", "radius": "ugv2/avoid_radius"}},
            "nav": {"capability": "move_to", "inputs": {"target": "north_point", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
        "head_south": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "south_point", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
    },
    "edges": {
        "head_north": [{"condition": ["ugv2/arrived", "==", True], "to": "head_south"}],
        "head_south": [{"condition": ["ugv2/arrived", "==", True], "to": "head_north"}],
    },
    "start": "head_north",
}







#========================================#
# Scenario
#========================================#

SCENARIO = ScenarioConfig(
    build_environment=lambda: GroundPlaneEnv(load_map("blank")),
    build_viewer=PlanePlotter.for_environment,
    platforms=[
        bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_split_ugv1),
        bicycle_ugv("ugv2", 0.0, 0.0, mission_graph=mission_split_ugv2),
    ],
)
