"""Wait scenario: ugv2 waits on a mesh-synced fact that originates on ugv1, on the blank map."""
from mtofr.database import Location
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps import load_map
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.viz import PlanePlotter
from mtofr.scenarios.base import ScenarioConfig


#========================================#
# Mission Graphs
#========================================#

mission_wait_ugv1 = {
    "knowledge": {
        "ugv1/arrived": {"type": bool, "value": False},
        "ugv1/nav_tolerance": {"type": float, "value": 0.5},
        "ugv1/destination": {"type": Location, "value": Location(6.0, 6.0)},
    },
    "nodes": {
        "drive_to_destination": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv1/destination", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
    },
    "edges": {},
    "start": "drive_to_destination",
}


mission_wait_ugv2 = {
    "knowledge": {
        "ugv2/arrived": {"type": bool, "value": False},
        "ugv2/nav_tolerance": {"type": float, "value": 0.5},
        "ugv2/own_start": {"type": Location, "value": Location(0.0, 0.0)},
        "ugv2/destination": {"type": Location, "value": Location(-6.0, -6.0)},
        # Foreign key: not written by ugv2 at all, only ever filled in by mesh sync
        # once ugv1 writes it. Declaring it here (per Knowledge's declare-before-use
        # discipline) is what lets ugv2's own edge condition reference it.
        "ugv1/arrived": {"type": bool, "value": False},
    },
    "nodes": {
        "stay_at_start": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/own_start", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
        "drive_elsewhere": {"capabilities": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/destination", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
    },
    "edges": {
        "stay_at_start": [{"condition": ["ugv1/arrived", "==", True], "to": "drive_elsewhere"}],
    },
    "start": "stay_at_start",
}







#========================================#
# Scenario
#========================================#

SCENARIO = ScenarioConfig(
    build_environment=lambda: GroundPlaneEnv(load_map("blank")),
    build_viewer=PlanePlotter.for_environment,
    platforms=[
        bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_wait_ugv1),
        bicycle_ugv("ugv2", 0.0, 0.0, mission_graph=mission_wait_ugv2),
    ],
)
