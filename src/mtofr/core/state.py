"""Defines State, the minimal physical state every Hardware owns."""
from dataclasses import dataclass


@dataclass
class State:
    """The part of physical state every environment shares: sim time only.  Each
    environment subclasses this with whatever it actually tracks (e.g.
    GroundPlaneState's 2D pose and velocity), declared as its Environment.state_type."""
    t: float = 0.0   # s, sim time
