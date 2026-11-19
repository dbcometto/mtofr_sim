"""Defines Platform, one platform's assembled Hardware/Frontseater/Backseater stack"""
from dataclasses import dataclass
from typing import Callable

from mtofr.backseater.backseater import Backseater
from mtofr.clock.clock import Clock
from mtofr.database import KnowledgeDatabase
from mtofr.world.base import Frontseater


@dataclass
class PlatformSpec:
    """Everything needed to build one platform: its id, a callable building its
    Hardware + Frontseater (starting WorldState included), and its Backseater settings.
    Declarative, so a mission set can list platforms without building anything (no
    MPC worker processes spawned) until a Platform is actually constructed from it."""
    platform_id: str
    build_frontseater: Callable[[bool], Frontseater]   # arg: debug
    mission_graph: dict | None = None   # None -> the Frontseater's own default_mission_graph()
    privilege_level: int = 1
    clock: Clock | None = None
    sync_interval: float = 1.0


class Platform:
    """Builds and owns one platform's Hardware -> Frontseater -> Backseater stack from a
    PlatformSpec, and handles its lifecycle via attach()/shutdown(). Assembly only, not a
    runtime layer: the layers still talk to each other directly, as they would as separate
    processes on a real robot -- the sim's equivalent of a per-robot launch file. Holds no
    reference to World, so World can own Platforms without the dependency running back up."""

    def __init__(self, spec: PlatformSpec, debug: bool = False):
        self.platform_id = spec.platform_id
        self.frontseater = spec.build_frontseater(debug)
        self.hardware = self.frontseater.hardware
        self.knowledge_database = KnowledgeDatabase()
        self.backseater = Backseater(
            frontseater=self.frontseater, knowledge_database=self.knowledge_database,
            mission_graph=spec.mission_graph, platform_id=spec.platform_id,
            privilege_level=spec.privilege_level, clock=spec.clock,
            sync_interval=spec.sync_interval, debug=debug,
        )

    def attach(self, world, window_root=None) -> None:
        """Forwards to Frontseater.attach() -- see there for why this is a separate step."""
        self.frontseater.attach(world, window_root)

    def shutdown(self) -> None:
        """Releases the Frontseater's resources (e.g. BicycleFrontseater's MPC worker process)."""
        self.frontseater.shutdown()
