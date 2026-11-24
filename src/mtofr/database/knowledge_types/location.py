"""Defines Location, a 2D point knowledge entry."""
from mtofr.database.knowledge_types.base import KnowledgeEntry


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
