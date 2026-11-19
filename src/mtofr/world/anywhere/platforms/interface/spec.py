"""Defines the PlatformSpec factory for the mission-editor "interface" platform"""
from mtofr.world.base import Frontseater, WorldState
from mtofr.world.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.world.anywhere.platforms.interface.frontseater import MissionEditorFrontseater
from mtofr.world.platform import PlatformSpec


def interface(platform_id: str, start_x: float, start_y: float, mission_graph: dict | None = None,
              privilege_level: int = 0) -> PlatformSpec:
    """A PlatformSpec for the mission-editor platform, fixed at (start_x, start_y) -- only
    safe on a map with no blocking terrain there. Defaults to privilege 0 (not the usual 1),
    since pushing mission graphs onto other platforms is this platform's whole job and
    write_mission()'s privilege gate requires strictly outranking the target."""
    def build_frontseater(debug: bool = False) -> Frontseater:
        """Builds this platform's ConsoleHardware and MissionEditorFrontseater."""
        hardware = ConsoleHardware(initial_state=WorldState(x=start_x, y=start_y))
        return MissionEditorFrontseater(hardware=hardware, debug=debug)
    return PlatformSpec(platform_id=platform_id, build_frontseater=build_frontseater,
                        mission_graph=mission_graph, privilege_level=privilege_level)
