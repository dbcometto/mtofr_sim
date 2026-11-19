"""Example scenarios for main.py, one file per scenario: each holds its mission graphs
and its ScenarioConfig (environment, viewer, platforms).  Every coordinate in them is
meters in the world frame (origin at the map center, +y up); tolerances and radii are
meters, durations seconds.  Builds on everything else; nothing imports scenarios but
main.py, scripts, and tests."""
from enum import IntEnum

from mtofr.scenarios import split, village, village_default, wait
from mtofr.scenarios.base import ScenarioConfig


class Scenario(IntEnum):
    """Which scenario main.py runs."""
    SPLIT = 0            # each platform runs its own independent loop, no coordination
    WAIT = 1             # ugv2 waits on a mesh-synced fact that originates on ugv1
    VILLAGE = 2          # exercises simple_village's road speed boost and blocked-terrain hard stop
    VILLAGE_DEFAULT = 3  # same map as VILLAGE, every platform on its default mission, plus the interface platform


SCENARIOS: dict[Scenario, ScenarioConfig] = {
    Scenario.SPLIT: split.SCENARIO,
    Scenario.WAIT: wait.SCENARIO,
    Scenario.VILLAGE: village.SCENARIO,
    Scenario.VILLAGE_DEFAULT: village_default.SCENARIO,
}
