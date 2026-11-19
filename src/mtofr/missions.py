"""Example mission graphs for main.py's demo platforms."""
from dataclasses import dataclass
from enum import IntEnum

from mtofr.database import Location
from mtofr.world.platform import PlatformSpec
from mtofr.world.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.world.anywhere.platforms.interface.spec import interface


class MissionSet(IntEnum):
    """Which mission set main.py wires up."""
    SPLIT = 0            # each platform runs its own independent loop, no coordination
    WAIT = 1             # ugv2 waits on a mesh-synced fact that originates on ugv1
    VILLAGE = 2          # exercises simple_village's road speed boost and blocked-terrain hard stop
    VILLAGE_DEFAULT = 3  # same map as VILLAGE, but every platform boots straight onto its own
                         # default_mission_graph() -- including the interface platform, present
                         # here so a live mission can be authored/pushed via the mission editor


@dataclass
class MissionSetConfig:
    """Everything main.py needs to wire up one mission set: which GroundMap to use
    (see mtofr.maps; None for the old unbounded mapless mode), and one PlatformSpec per
    platform -- built via each platform type's own spec factory (e.g. bicycle_ugv()), so
    different mission sets can mix platform types freely. A spec with no mission_graph
    boots onto its own Frontseater.default_mission_graph() instead."""
    map_name: str | None
    platforms: list[PlatformSpec]

    def __post_init__(self):
        """Rejects duplicate platform_ids, which would otherwise silently overwrite
        one another once main.py keys the built platforms by id."""
        platform_ids = [spec.platform_id for spec in self.platforms]
        if len(platform_ids) != len(set(platform_ids)):
            raise ValueError(f"Duplicate platform_id in mission set: {platform_ids}")


#==========# split: independent per-platform loops, no cross-platform coordination #==========#

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


#==========# wait: ugv2 waits on a mesh-synced fact that originates on ugv1 #==========#

mission_wait_ugv1 = {
    "knowledge": {
        "ugv1/arrived": {"type": bool, "value": False},
        "ugv1/nav_tolerance": {"type": float, "value": 0.5},
        "ugv1/destination": {"type": Location, "value": Location(6.0, 6.0)},
    },
    "nodes": {
        "drive_to_destination": {"primitives": {
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
        "stay_at_start": {"primitives": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/own_start", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
        "drive_elsewhere": {"primitives": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/destination", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
    },
    "edges": {
        "stay_at_start": [{"condition": ["ugv1/arrived", "==", True], "to": "drive_elsewhere"}],
    },
    "start": "stay_at_start",
}


#==========# village: exercises simple_village's road/blocked terrain #==========#

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
        "head_to_road": {"primitives": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv1/road_waypoint", "tolerance": "ugv1/nav_tolerance"},
                    "outputs": {"arrived": "ugv1/arrived"}},
        }},
        "drive_into_building": {"primitives": {
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
        "head_to_road": {"primitives": {
            "nav": {"capability": "move_to", "inputs": {"target": "ugv2/road_waypoint", "tolerance": "ugv2/nav_tolerance"},
                    "outputs": {"arrived": "ugv2/arrived"}},
        }},
        "head_to_clear": {"primitives": {
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


#==========# Mission sets: what main.py actually wires up #==========#

MISSION_SETS = {
    MissionSet.SPLIT: MissionSetConfig(
        map_name="blank",
        platforms=[
            bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_split_ugv1),
            bicycle_ugv("ugv2", 0.0, 0.0, mission_graph=mission_split_ugv2),
        ],
    ),
    MissionSet.WAIT: MissionSetConfig(
        map_name="blank",
        platforms=[
            bicycle_ugv("ugv1", 0.0, 0.0, mission_graph=mission_wait_ugv1),
            bicycle_ugv("ugv2", 0.0, 0.0, mission_graph=mission_wait_ugv2),
        ],
    ),
    MissionSet.VILLAGE: MissionSetConfig(
        map_name="simple_village",
        platforms=[
            bicycle_ugv("ugv1", -3.0, -20.0, mission_graph=mission_village_ugv1),
            bicycle_ugv("ugv2", 45.0, -25.0, mission_graph=mission_village_ugv2),
        ],
    ),
    # No mission graphs: every platform boots straight onto its own
    # Frontseater.default_mission_graph() -- ugv1/ugv2 idle-loiter, interface shows
    # its editor window -- until a mission is authored/pushed live via the editor.
    MissionSet.VILLAGE_DEFAULT: MissionSetConfig(
        map_name="simple_village",
        platforms=[
            bicycle_ugv("ugv1", -3.0, -20.0),
            bicycle_ugv("ugv2", 45.0, -25.0),
            # (0, -30) is clear, unblocked terrain on simple_village's map -- verified
            # against GroundMap.is_blocked()/speed_multiplier_at() directly. interface()
            # defaults to privilege 0, outranking ugv1/ugv2's default 1 so its pushes pass
            # write_mission()'s privilege gate.
            interface("interface", 0.0, -30.0),
        ],
    ),
}