"""Defines Trajectory, an ordered list of 2D waypoints stored as plain text."""
import json
from numbers import Real

from mtofr.database.knowledge_types.base import KnowledgeEntry


#========================================#
# Config
#========================================#

POINT_LENGTH = 2   # [x, y]







#========================================#
# Trajectory
#========================================#

class Trajectory(KnowledgeEntry):
    """A trajectory knowledge entry: waypoints as JSON text, e.g. "[[0, 0], [10, 5]]".  Plain
    text on purpose: the one str field rides through the editors, save/load, mesh sync,
    and the LLM like any scalar.  The World Viewer's trajectory drawer writes this format."""
    def __init__(self, waypoints: str):
        """Parses `waypoints` (a JSON list of [x, y] pairs, m, world frame; "" for none);
        raises ValueError if it isn't one."""
        self.waypoints = waypoints   # the text, as given
        self.points: tuple[tuple[float, float], ...] = parse_waypoints(waypoints)   # m, world frame

    @classmethod
    def describe(cls) -> str:
        """Plaintext description of a Trajectory for a human or LLM reader."""
        return ('Trajectory(waypoints): an ordered route of 2D waypoints in the platform\'s world frame, in '
                'meters. `waypoints` is a JSON list of [x, y] pairs as text, e.g. "[[0, 0], [10, 5], [20, -3]]" '
                '(empty text for no waypoints). Give it as {"waypoints": "[[x, y], ...]"}.')

    def __repr__(self):
        """Shows the waypoint text, e.g. Trajectory(waypoints='[[0, 0], [10, 5]]')."""
        return f"Trajectory(waypoints={self.waypoints!r})"


def parse_waypoints(waypoints: str) -> tuple[tuple[float, float], ...]:
    """Trajectory text as ((x, y), ...) (m); "" (or only whitespace) is no waypoints.  Raises
    ValueError for anything but a JSON list of [x, y] number pairs."""
    if not waypoints.strip():
        return ()
    try:
        parsed = json.loads(waypoints)
    except json.JSONDecodeError as error:
        raise ValueError(f"waypoints must be a JSON list of [x, y] pairs: {error}")
    if not isinstance(parsed, list):
        raise ValueError("waypoints must be a JSON list of [x, y] pairs")
    points = []
    for point in parsed:
        # NOTE: bool is a Real subclass in Python, so it's excluded explicitly.
        if (not isinstance(point, list) or len(point) != POINT_LENGTH
                or not all(isinstance(coordinate, Real) and not isinstance(coordinate, bool) for coordinate in point)):
            raise ValueError(f"each waypoint must be an [x, y] pair of numbers, not {point!r}")
        points.append((float(point[0]), float(point[1])))
    return tuple(points)
