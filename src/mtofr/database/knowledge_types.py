"""Defines concrete KnowledgeDatabase entry types: KnowledgeEntry, the ABC every richer
object type stored in a KnowledgeDatabase must implement, plus Location, the only
built-in entry type so far."""
from abc import ABC, abstractmethod


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