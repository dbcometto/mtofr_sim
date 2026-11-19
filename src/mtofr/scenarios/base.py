"""Defines ScenarioConfig: everything main.py needs to run one scenario."""
from dataclasses import dataclass
from typing import Callable

from mtofr.core.environment import Environment
from mtofr.platform.platform import PlatformSpec
from mtofr.viz.base import EnvironmentViewer


@dataclass
class ScenarioConfig:
    """One scenario: how to build its environment and the viewer that draws it, and one
    PlatformSpec per platform (each from its platform type's own spec factory, e.g.
    bicycle_ugv(), so a scenario can mix platform types freely). A spec with no
    mission_graph boots onto its own Frontseater.default_mission_graph() instead.
    Builders rather than instances, like PlatformSpec, so importing every scenario loads
    no maps and spawns nothing."""
    build_environment: Callable[[], Environment]
    build_viewer: Callable[[Environment], EnvironmentViewer]
    platforms: list[PlatformSpec]

    def __post_init__(self):
        """Rejects duplicate platform_ids, which would otherwise silently overwrite
        one another once main.py keys the built platforms by id."""
        platform_ids = [spec.platform_id for spec in self.platforms]
        if len(platform_ids) != len(set(platform_ids)):
            raise ValueError(f"Duplicate platform_id in scenario: {platform_ids}")
