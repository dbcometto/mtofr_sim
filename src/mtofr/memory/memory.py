"""Defines memory"""
from abc import ABC, abstractmethod

#==========# Main Memory Storage #==========#

class Memory:
    """Typed store of known entities (locations, later agents, conditions, etc).
    Currently one instance per backseater; a planner-level Memory is expected later too."""

    def __init__(self):
        self._entries = {}   # id -> entry object

    def add(self, id: str, entry) -> None:
        self._entries[id] = entry

    def get(self, id: str):
        return self._entries[id]

    def all_of_type(self, cls) -> dict:
        return {id: e for id, e in self._entries.items() if isinstance(e, cls)}


#==========# Individual Memories #==========#

class MemoryEntry(ABC):
    """Base for typed memory entries. Platforms/systems are free to define their own entry
    types beyond the ones built in here — every entry type must self-describe in plaintext
    so a planner LLM or human can understand a custom type without reading its source, the
    same self-description contract Capability/ParamSpec use."""
    @classmethod
    @abstractmethod
    def describe(cls) -> str:
        """Plaintext description of what this entry type represents and its fields."""


class Location(MemoryEntry):
    """A location memory (2D)"""
    def __init__(self, x, y):
        self.x = x
        self.y = y

    @classmethod
    def describe(cls) -> str:
        return "Location(x, y): a 2D point in the platform's world frame, in meters."

    def __repr__(self):
        return f"Location(x={self.x}, y={self.y})"