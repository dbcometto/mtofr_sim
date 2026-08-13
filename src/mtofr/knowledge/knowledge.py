"""Defines knowledge"""
from abc import ABC, abstractmethod

#==========# Main Knowledge Storage #==========#

class Knowledge:
    """Typed, type-locked store of known entities and values (locations, sensed flags,
    task outputs, etc). Every key must be declared with its type and a default value
    before it can be read or written — this is what lets a Backseater reject a
    Frontseater trying to write a wrong-typed value into a key. Currently one instance
    per backseater; a planner-level Knowledge is expected later too."""

    def __init__(self):
        self._types = {}     # key -> declared type
        self._entries = {}   # key -> current value

    def declare(self, key: str, type: type, value) -> None:
        """Locks `key` to `type` for the life of this store and seeds it with `value`."""
        self._types[key] = type
        self._entries[key] = value

    def set(self, key: str, value) -> None:
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

    def get(self, key: str):
        return self._entries[key]

    def type_of(self, key: str) -> type | None:
        """Returns the declared type for `key`, or None if it hasn't been declared."""
        return self._types.get(key)

    def all(self) -> dict:
        """key -> value for every known entry, regardless of type. The query
        path a visualization tool or human uses to browse a platform's full knowledge."""
        return dict(self._entries)

    def all_of_type(self, cls) -> dict:
        return {key: value for key, value in self._entries.items() if isinstance(value, cls)}


#==========# Individual Entries #==========#

class KnowledgeEntry(ABC):
    """Base for typed knowledge entries. Platforms/systems are free to define their own entry
    types beyond the ones built in here — every entry type must self-describe in plaintext
    so a planner LLM or human can understand a custom type without reading its source, the
    same self-description contract Capability/ParamSpec use."""
    @classmethod
    @abstractmethod
    def describe(cls) -> str:
        """Plaintext description of what this entry type represents and its fields."""


class Location(KnowledgeEntry):
    """A location knowledge entry (2D)"""
    def __init__(self, x, y):
        self.x = x
        self.y = y

    @classmethod
    def describe(cls) -> str:
        return "Location(x, y): a 2D point in the platform's world frame, in meters."

    def __repr__(self):
        return f"Location(x={self.x}, y={self.y})"
