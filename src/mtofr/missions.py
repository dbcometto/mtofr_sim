"""Example mission graphs for main.py's demo platforms."""
from mtofr.knowledge.knowledge import Location


mission_ugv1 = {
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
        "head_east": {"primitives": {
            "nav": {"capability": "move_to", "inputs": {"target": "east", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
        "loop_west": {"primitives": {
            "avoid_top_center": {"capability": "avoid", "inputs": {"point": "top_center", "radius": "ugv1/avoid_radius_large"}},
            "nav": {"capability": "move_to", "inputs": {"target": "west", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
        "return_southeast": {"primitives": {
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


mission_ugv2 = {
    "knowledge": {
        "ugv2/arrived": {"type": bool, "value": False},
        "ugv2/nav_tolerance": {"type": float, "value": 0.5},
        "ugv2/avoid_radius": {"type": float, "value": 2.5},
        "north_point": {"type": Location, "value": Location(0.0, 8.0)},
        "south_point": {"type": Location, "value": Location(0.0, -8.0)},
        "east_of_origin": {"type": Location, "value": Location(3.0, 0.0)},
    },
    "nodes": {
        "head_north": {"primitives": {
            "avoid_east_of_origin": {"capability": "avoid", "inputs": {"point": "east_of_origin", "radius": "ugv2/avoid_radius"}},
            "nav": {"capability": "move_to", "inputs": {"target": "north_point", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
        "head_south": {"primitives": {
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