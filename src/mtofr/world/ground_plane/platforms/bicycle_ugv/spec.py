"""Defines the PlatformSpec factory for a bicycle-dynamics UGV"""
from mtofr.world.base import Frontseater, WorldState
from mtofr.world.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.world.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater
from mtofr.world.platform import PlatformSpec
from mtofr.backseater.backseater import DEFAULT_PRIVILEGE_LEVEL


def bicycle_ugv(platform_id: str, start_x: float, start_y: float, mission_graph: dict | None = None,
                privilege_level: int = DEFAULT_PRIVILEGE_LEVEL) -> PlatformSpec:
    """A PlatformSpec for a UGV with bicycle dynamics starting at (start_x, start_y) (m, world frame) --
    only safe on a map with no blocking terrain at that point."""
    def build_frontseater(debug: bool = False) -> Frontseater:
        """Builds this UGV's BicycleHardware and BicycleFrontseater."""
        hardware = BicycleHardware(initial_state=WorldState(x=start_x, y=start_y))
        return BicycleFrontseater(hardware=hardware, debug=debug)
    return PlatformSpec(platform_id=platform_id, build_frontseater=build_frontseater,
                        mission_graph=mission_graph, privilege_level=privilege_level)
