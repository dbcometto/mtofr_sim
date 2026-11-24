"""Defines the PlatformSpec factory for the mission-editor "interface" platform"""
from typing import Callable

from mtofr.environments.ground_plane.platforms.interface.hardware import ConsoleHardware
from mtofr.environments.ground_plane.platforms.interface.frontseater import MissionEditorFrontseater
from mtofr.environments.ground_plane.platforms.interface.web.panels import default_panels
from mtofr.environments.ground_plane.state import GroundPlaneState
from mtofr.mission.graph import MissionGraph
from mtofr.platform.frontseater import Frontseater
from mtofr.platform.platform import PlatformSpec


INTERFACE_PRIVILEGE_LEVEL = 0   # the highest; outranks every default-privilege platform


def interface(platform_id: str, initial_state: GroundPlaneState, mission_graph: MissionGraph | None = None,
              privilege_level: int = INTERFACE_PRIVILEGE_LEVEL,
              build_panels: Callable[[], list] = default_panels) -> PlatformSpec:
    """A PlatformSpec for the mission-editor platform, a fixed ground station at `initial_state`
    (e.g. on clear terrain). Defaults to privilege 0 (not the usual 1), since pushing mission graphs
    onto other platforms is this platform's whole job and write_mission()'s privilege gate requires
    strictly outranking the target. `build_panels` is the web UI's static panel registry: a
    callable returning fresh WebPanels, in tab order."""
    def build_frontseater(debug: bool = False) -> Frontseater:
        """Builds this platform's ConsoleHardware and MissionEditorFrontseater."""
        hardware = ConsoleHardware(initial_state=initial_state)
        return MissionEditorFrontseater(hardware=hardware, build_panels=build_panels, debug=debug)
    return PlatformSpec(platform_id=platform_id, build_frontseater=build_frontseater,
                        mission_graph=mission_graph, privilege_level=privilege_level)
