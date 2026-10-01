"""Defines the platform_id-keyed databases a Backseater owns (as opposed to
KnowledgeDatabase in knowledge.py, which is keyed by arbitrary key instead of
platform_id): MissionDatabase and PlatformDatabase, sharing a PlatformKeyedDatabase base."""
import time
from dataclasses import dataclass
from typing import Optional

from mtofr.capability.capability import CapabilityRegistry
from mtofr.condition.condition import parse_condition


#==========# Shared base #==========#

class PlatformKeyedDatabase:
    """One value per platform_id, type-locked to a single fixed type declared by a
    subclass's `value_type` — unlike KnowledgeDatabase, which locks a type per
    arbitrary key, every entry here is the same shape (a mission graph, a capability
    registry snapshot, a status). Every declare/set records a timestamp (defaulting to
    wall-clock time if not given) and an origin_platform_id (the platform that held
    this entry at its most recently locally-converted timestamp, transitively) — this
    is what a future mesh sync's last-write-wins conflict resolution and privilege
    checks will key off of."""

    value_type: type = object

    def __init__(self):
        self._entries = {}     # platform_id -> current value
        self._timestamps = {}  # platform_id -> timestamp of the value currently stored
        self._origins = {}     # platform_id -> origin_platform_id of the value currently stored

    def declare(self, platform_id: str, value, timestamp: float = None, origin_platform_id: str = None) -> None:
        """Registers `platform_id`'s entry and seeds it with `value`. Raises ValueError
        if `value` isn't an instance of this database's fixed `value_type`."""
        self._check_type(value)
        self._entries[platform_id] = value
        self._timestamps[platform_id] = timestamp if timestamp is not None else time.time()
        self._origins[platform_id] = origin_platform_id

    def set(self, platform_id: str, value, timestamp: float = None, origin_platform_id: str = None) -> None:
        """Raises ValueError if `platform_id` wasn't declared, or if `value` isn't an
        instance of this database's fixed `value_type`."""
        if platform_id not in self._entries:
            raise ValueError(f"{type(self).__name__} has no entry declared for platform_id '{platform_id}'")
        self._check_type(value)
        self._entries[platform_id] = value
        self._timestamps[platform_id] = timestamp if timestamp is not None else time.time()
        self._origins[platform_id] = origin_platform_id

    def get(self, platform_id: str):
        return self._entries[platform_id]

    def timestamp_of(self, platform_id: str) -> float | None:
        """Returns the timestamp of the value currently stored for `platform_id`, or
        None if it hasn't been declared."""
        return self._timestamps.get(platform_id)

    def origin_of(self, platform_id: str) -> str | None:
        """Returns the origin_platform_id of the value currently stored for
        `platform_id`, or None if it hasn't been declared (or was declared/set
        without one)."""
        return self._origins.get(platform_id)

    def all(self) -> dict:
        """platform_id -> value for every declared entry."""
        return dict(self._entries)

    def _check_type(self, value) -> None:
        if not isinstance(value, self.value_type):
            raise ValueError(
                f"{type(self).__name__} expected {self.value_type.__name__}, got {type(value).__name__}"
            )


#==========# Mission #==========#

class MissionDatabase(PlatformKeyedDatabase):
    """Keyed by platform_id, one mission_graph value per platform. Direct declare()/set()
    calls remain unrestricted (used by Backseater to seed/self-write its own entry);
    a write originating from another platform must instead go through
    Backseater.write_mission(), the single gated write point (privilege check,
    structural verify, then this database's own type check). Backseater detects a
    changed entry and reacts to it (mission-change handling) on the next update()."""
    value_type = dict


class MissionStructuralError(ValueError):
    """Raised when a mission graph references a Knowledge key, in an edge condition or a
    primitive's inputs/outputs, that isn't declared in that same graph's own "knowledge" section."""


def verify_mission_structure(mission_graph: dict) -> None:
    """Raises MissionStructuralError if any edge condition or primitive input/output binding in
    `mission_graph` references a Knowledge key not declared in the graph's own "knowledge" section.
    Primitive bindings are checked here (not only at Backseater's bind time) so a bad graph is
    rejected at push instead of being accepted and then halting the running mission."""
    declared_keys = set(mission_graph.get("knowledge", {}).keys())
    referenced_keys = set()
    for edges in mission_graph.get("edges", {}).values():
        for edge in edges:
            referenced_keys |= parse_condition(edge["condition"]).keys()
    for node in mission_graph.get("nodes", {}).values():
        for primitive in node.get("primitives", {}).values():
            referenced_keys |= set(primitive.get("inputs", {}).values())
            referenced_keys |= set(primitive.get("outputs", {}).values())

    missing_keys = referenced_keys - declared_keys
    if missing_keys:
        raise MissionStructuralError(
            f"Mission graph references undeclared knowledge key(s): {sorted(missing_keys)}"
        )


#==========# Platform #==========#

@dataclass(frozen=True)
class PlatformStatus:
    """A platform's self-reported health: a status string plus an arbitrary free-text
    message, one field of the PlatformRecord value PlatformDatabase locks its entries to."""
    status: str
    message: str = ""


@dataclass(frozen=True)
class PlatformRecord:
    """Everything gossiped "about" one platform, merged into a single row so a mesh
    sync only has to reconcile one entry per peer instead of three: its privilege
    level (placeholder security, see Backseater), self-reported status, and its most
    recently advertised CapabilityRegistry snapshot."""
    privilege_level: int
    status: PlatformStatus = PlatformStatus("idle")
    capabilities: Optional[CapabilityRegistry] = None


class PlatformDatabase(PlatformKeyedDatabase):
    """Keyed by platform_id, one PlatformRecord per platform — self-write-only once mesh
    sync exists, but that restriction isn't enforced yet (except for privilege_level,
    which is never self-write-only even once sync exists: only a strictly
    higher-privilege platform may change it). Gossiped across the mesh (once sync
    exists) so an operator/LLM can observe a remote platform's health, capabilities, or
    privilege level without local access. This is also the lookup Backseater's Mission
    write gate uses to resolve both sides' privilege levels."""
    value_type = PlatformRecord