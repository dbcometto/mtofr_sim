"""Defines Environment, the passive description of the world Hardware steps against."""
from abc import ABC


class Environment(ABC):
    """A passive description of the world (terrain, bounds, ...) that each Hardware
    queries while stepping its own dynamics; it never steps anything itself. Each
    concrete environment defines whatever queries its vehicles need (e.g.
    GroundPlaneEnv.is_blocked()), alongside the Hardware base those vehicles subclass.
    Every subclass must set `state_type` (the State subclass every platform in it is
    expressed in, so it can be drawn and, later, ranged), which World checks at
    construction; a platform that can live anywhere is still placed in its host
    environment's terms."""
    # NOTE: state_type deliberately has no default here, mirroring Hardware.environment_type.
    state_type: type
