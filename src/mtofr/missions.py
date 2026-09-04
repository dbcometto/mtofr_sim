"""Example mission graphs for main.py's demo platforms."""
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

from mtofr.database import Location
from mtofr.world.base import Frontseater, WorldState
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.interface.hardware import ConsoleHardware
from mtofr.world.interface.frontseater import MissionEditorFrontseater


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
    (see mtofr.maps; None for the old unbounded mapless mode), and each platform's
    Frontseater builder plus mission graph, keyed by platform_id. Hardware/Frontseater
    construction lives here (not main.py) since different mission sets may want
    different platform types/hardware configs, not just BicycleHardware. main.py
    builds one frontseater/backseater stack per key in platform_builders (mission_graphs
    need not cover every key -- a platform_id missing from mission_graphs boots onto its
    own Frontseater.default_mission_graph() instead). privilege_levels likewise defaults
    any platform_id it doesn't mention to 1 -- only the interface platform currently needs
    to outrank that default, to push mission graphs onto other platforms."""
    map_name: str | None
    platform_builders: dict            # platform_id -> Callable[[bool], Frontseater] (arg: debug)
    mission_graphs: dict                # platform_id -> mission graph dict
    privilege_levels: dict = field(default_factory=dict)   # platform_id -> int, default 1


def _bicycle_platform(start_x: float, start_y: float) -> Callable[[bool], Frontseater]:
    """A platform_builders entry for a UGV with bicycle dynamics starting at
    (start_x, start_y) -- only safe on a map with no blocking terrain at that point."""
    def build(debug: bool = False) -> Frontseater:
        hardware = BicycleHardware(initial_state=WorldState(x=start_x, y=start_y))
        return BicycleFrontseater(hardware=hardware, debug=debug)
    return build


def _interface_platform(start_x: float, start_y: float) -> Callable[[bool], Frontseater]:
    """A platform_builders entry for the mission-editor "interface" platform,
    fixed at (start_x, start_y) -- only safe on a map with no blocking terrain there."""
    def build(debug: bool = False) -> Frontseater:
        hardware = ConsoleHardware(initial_state=WorldState(x=start_x, y=start_y))
        return MissionEditorFrontseater(hardware=hardware, debug=debug)
    return build


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
        platform_builders={"ugv1": _bicycle_platform(0.0, 0.0), "ugv2": _bicycle_platform(0.0, 0.0)},
        mission_graphs={"ugv1": mission_split_ugv1, "ugv2": mission_split_ugv2},
    ),
    MissionSet.WAIT: MissionSetConfig(
        map_name="blank",
        platform_builders={"ugv1": _bicycle_platform(0.0, 0.0), "ugv2": _bicycle_platform(0.0, 0.0)},
        mission_graphs={"ugv1": mission_wait_ugv1, "ugv2": mission_wait_ugv2},
    ),
    MissionSet.VILLAGE: MissionSetConfig(
        map_name="simple_village",
        platform_builders={"ugv1": _bicycle_platform(-3.0, -20.0), "ugv2": _bicycle_platform(45.0, -25.0)},
        mission_graphs={"ugv1": mission_village_ugv1, "ugv2": mission_village_ugv2},
    ),
    MissionSet.VILLAGE_DEFAULT: MissionSetConfig(
        map_name="simple_village",
        platform_builders={
            "ugv1": _bicycle_platform(-3.0, -20.0),
            "ugv2": _bicycle_platform(45.0, -25.0),
            # (0, -30) is clear, unblocked terrain on simple_village's map -- verified
            # against GroundMap.is_blocked()/speed_multiplier_at() directly.
            "interface": _interface_platform(0.0, -30.0),
        },
        # No entries: every platform (ugv1/ugv2/interface) boots straight onto its own
        # Frontseater.default_mission_graph() -- ugv1/ugv2 idle-loiter, interface shows
        # its editor window -- until a mission is authored/pushed live via the editor.
        mission_graphs={},
        # interface must outrank the default privilege level (1) to push a mission
        # graph onto ugv1/ugv2 via write_mission()'s privilege gate.
        privilege_levels={"interface": 0},
    ),
}