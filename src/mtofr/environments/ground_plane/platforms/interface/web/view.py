"""Defines InterfaceView: a read-only snapshot of one Backseater's three databases (plus the
interface hardware's sensed map), the only thing the web UI's panels read."""
from dataclasses import dataclass, field

from mtofr.environments.ground_plane.maps import GroundMap


@dataclass(frozen=True)
class KnowledgeRow:
    """One Knowledge entry as the capturing platform holds it."""
    entry_type: type
    value: object
    origin_platform_id: str | None
    timestamp: float | None   # s, the capturing platform's local clock frame


@dataclass(frozen=True)
class InterfaceView:
    """What the interface platform's own Backseater knows, as of one tick: every platform's
    gossiped PlatformRecord and Mission entry, and the whole Knowledge namespace, plus the
    map its own hardware senses. Built on the sim thread by capture() and only read
    afterwards, so web server threads can use it while the next tick runs."""
    # NOTE: capture() copies each database's dict but shares the entries themselves. That is
    # safe because nothing mutates them in place: PlatformRecords are frozen, mission graphs
    # and Knowledge values are replaced on write, never edited, and a GroundMap is never edited.
    own_platform_id: str | None
    time: float | None = None                       # s, own local clock at capture; None before the first tick
    platforms: dict = field(default_factory=dict)   # platform_id -> PlatformRecord
    missions: dict = field(default_factory=dict)    # platform_id -> mission graph
    knowledge: dict = field(default_factory=dict)   # key -> KnowledgeRow
    last_sync: dict = field(default_factory=dict)   # peer platform_id -> own local clock time (s) of the last sync with it
    ground_map: GroundMap | None = None             # the interface hardware's sensed map; None if none

    @classmethod
    def capture(cls, backseater, ground_map: GroundMap | None = None) -> "InterfaceView":
        """Snapshots `backseater`'s databases, alongside `ground_map` (the interface hardware's
        sensed map); call only on the thread that runs its ticks."""
        knowledge_database = backseater.knowledge_database
        knowledge = {
            key: KnowledgeRow(knowledge_database.type_of(key), value,
                              knowledge_database.origin_of(key), knowledge_database.timestamp_of(key))
            for key, value in knowledge_database.all().items()
        }
        return cls(
            own_platform_id=backseater.platform_id,
            time=backseater.clock.now(),
            platforms=backseater.platform_database.all(),
            missions=backseater.mission_database.all(),
            knowledge=knowledge,
            last_sync=backseater.last_sync_times(),
            ground_map=ground_map,
        )

    def capabilities_of(self, platform_id: str | None):
        """The CapabilityRegistry `platform_id` advertises, or None if unknown here."""
        record = self.platforms.get(platform_id)
        return record.capabilities if record is not None else None

    def sync_age(self, platform_id: str | None) -> float | None:
        """Seconds (as of capture) since the interface last synced with `platform_id`; None if never."""
        synced_at = self.last_sync.get(platform_id)
        return None if synced_at is None or self.time is None else self.time - synced_at
