"""Defines the PlatformSpec factory for the mission-editor "interface" platform"""
from typing import Callable

from mtofr.core.state import State
from mtofr.environments.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.environments.anywhere.platforms.interface.frontseater import MissionEditorFrontseater
from mtofr.environments.anywhere.platforms.interface.web.panels import default_panels
from mtofr.mission.graph import MissionGraph
from mtofr.platform.frontseater import Frontseater
from mtofr.platform.platform import PlatformSpec


INTERFACE_PRIVILEGE_LEVEL = 0   # the highest; outranks every default-privilege platform


def interface(platform_id: str, initial_state: State, mission_graph: MissionGraph | None = None,
              privilege_level: int = INTERFACE_PRIVILEGE_LEVEL,
              build_panels: Callable[[], list] = default_panels) -> PlatformSpec:
    """A PlatformSpec for the mission-editor platform, fixed at `initial_state`, which must be the host
    environment's state_type (e.g. a GroundPlaneState on clear terrain). Defaults to privilege 0 (not
    the usual 1), since pushing mission graphs onto other platforms is this platform's whole job and
    write_mission()'s privilege gate requires strictly outranking the target. `build_panels` is the
    web UI's static panel registry: a callable returning fresh WebPanels, in tab order."""
    def build_frontseater(debug: bool = False) -> Frontseater:
        """Builds this platform's ConsoleHardware and MissionEditorFrontseater."""
        hardware = ConsoleHardware(initial_state=initial_state)
        return MissionEditorFrontseater(hardware=hardware, build_panels=build_panels, debug=debug)
    return PlatformSpec(platform_id=platform_id, build_frontseater=build_frontseater,
                        mission_graph=mission_graph, privilege_level=privilege_level)
