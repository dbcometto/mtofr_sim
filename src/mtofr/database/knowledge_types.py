"""Defines concrete KnowledgeDatabase entry types: KnowledgeEntry, the ABC every richer
object type stored in a KnowledgeDatabase must implement, plus the built-in entry types
Location and Pose."""
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
    def __init__(self, x: float, y: float):
        """A point at (x, y) (m, world frame)."""
        self.x = x  # m, world frame
        self.y = y  # m, world frame

    @classmethod
    def describe(cls) -> str:
        """Plaintext description of a Location for a human or LLM reader."""
        return "Location(x, y): a 2D point in the platform's world frame, in meters."

    def __repr__(self):
        """Shows both coordinates, e.g. Location(x=1.0, y=2.0)."""
        return f"Location(x={self.x}, y={self.y})"


class Pose(KnowledgeEntry):
    """A pose knowledge entry (2D position plus heading)"""
    def __init__(self, x: float, y: float, theta: float):
        """A pose at (x, y) facing theta (m, m, rad; world frame)."""
        self.x = x          # m, world frame
        self.y = y          # m, world frame
        self.theta = theta  # rad, world frame, counterclockwise from +x

    @classmethod
    def describe(cls) -> str:
        """Plaintext description of a Pose for a human or LLM reader."""
        return ("Pose(x, y, theta): a platform's 2D position in meters and heading in radians "
                "(counterclockwise from +x), in the platform's world frame.")

    def __repr__(self):
        """Shows every field, e.g. Pose(x=1.0, y=2.0, theta=0.5)."""
        return f"Pose(x={self.x}, y={self.y}, theta={self.theta})"