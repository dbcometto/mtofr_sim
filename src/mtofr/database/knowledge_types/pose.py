"""Defines Pose, a 2D position-plus-heading knowledge entry."""
from mtofr.database.knowledge_types.base import KnowledgeEntry


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
