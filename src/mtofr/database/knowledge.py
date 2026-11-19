"""Defines KnowledgeDatabase: the arbitrary-key typed store one Backseater owns (as opposed
to MissionDatabase/PlatformDatabase in platform_keyed.py, which are keyed by platform_id).
Concrete entry types (e.g. Location) live in knowledge_types.py."""
import time


class KnowledgeDatabase:
    """Typed, type-locked store of known entities and values (locations, sensed flags,
    task outputs, etc). Every key must be declared with its type and a default value
    before it can be read or written, which is what lets a Backseater reject a
    Frontseater writing a wrong-typed value into a key. Every declare/set also records a
    timestamp (seconds, local clock frame; wall-clock time if not given) and an
    origin_platform_id (the platform that held this entry at its most recently
    locally-converted timestamp, transitively), which mesh sync's last-write-wins
    conflict resolution keys off."""

    def __init__(self):
        """Starts empty."""
        self._types = {}       # key -> declared type
        self._entries = {}     # key -> current value
        self._timestamps = {}  # key -> timestamp (s, local frame) of the value currently stored
        self._origins = {}     # key -> origin_platform_id of the value currently stored

    def declare(self, key: str, entry_type: type, value, timestamp: float = None, origin_platform_id: str = None) -> None:
        """Locks `key` to `entry_type` for the life of this store and seeds it with `value`."""
        self._types[key] = entry_type
        self._entries[key] = value
        self._timestamps[key] = timestamp if timestamp is not None else time.time()
        self._origins[key] = origin_platform_id

    def set(self, key: str, value, timestamp: float = None, origin_platform_id: str = None) -> None:
        """Raises ValueError if `key` wasn't declared, or if `value` isn't an instance
        of its declared type."""
        declared_type = self._types.get(key)
        if declared_type is None:
            raise ValueError(f"Knowledge key '{key}' was not declared")
        if not isinstance(value, declared_type):
            raise ValueError(
                f"Knowledge key '{key}' expected {declared_type.__name__}, got {type(value).__name__}"
            )
        self._entries[key] = value
        self._timestamps[key] = timestamp if timestamp is not None else time.time()
        self._origins[key] = origin_platform_id

    def set_or_declare(self, key: str, value, timestamp: float = None, origin_platform_id: str = None) -> None:
        """Behaves like set() if `key` is already declared; otherwise declares it on
        the fly using `type(value)`. The rare bypass mesh sync uses for a received fact
        this platform never declared, instead of the normal declare-before-use discipline."""
        if key in self._types:
            self.set(key, value, timestamp=timestamp, origin_platform_id=origin_platform_id)
        else:
            self.declare(key, type(value), value, timestamp=timestamp, origin_platform_id=origin_platform_id)

    def get(self, key: str):
        """Returns the current value of `key`; raises KeyError if it hasn't been declared."""
        return self._entries[key]

    def type_of(self, key: str) -> type | None:
        """Returns the declared type for `key`, or None if it hasn't been declared."""
        return self._types.get(key)

    def timestamp_of(self, key: str) -> float | None:
        """Returns the timestamp (s, local frame) of the value currently stored for
        `key`, or None if it hasn't been declared."""
        return self._timestamps.get(key)

    def origin_of(self, key: str) -> str | None:
        """Returns the origin_platform_id of the value currently stored for `key`, or
        None if it hasn't been declared (or was declared/set without one)."""
        return self._origins.get(key)

    def all(self) -> dict:
        """key -> value for every known entry, regardless of type. The query
        path a visualization tool or human uses to browse a platform's full knowledge."""
        return dict(self._entries)

    def all_of_type(self, entry_type: type) -> dict:
        """key -> value for every entry whose value is an instance of `entry_type`."""
        return {key: value for key, value in self._entries.items() if isinstance(value, entry_type)}
