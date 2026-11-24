"""Example scenarios for main.py, one file per scenario: each holds its mission graphs
and its `SCENARIO = ScenarioConfig(...)`, and its docstring says what it exercises.
Every module here except base.py is discovered into SCENARIOS under its file name, so
a new scenario is just a new file.  Every coordinate in them is meters in the world
frame (origin at the map center, +y up); tolerances and radii are meters, durations
seconds.  Builds on everything else; nothing imports scenarios but main.py, scripts,
and tests."""
import importlib
import pkgutil

from mtofr.scenarios.base import ScenarioConfig


NON_SCENARIO_MODULES = {"base"}


SCENARIOS: dict[str, ScenarioConfig] = {
    module.name: importlib.import_module(f"{__name__}.{module.name}").SCENARIO
    for module in pkgutil.iter_modules(__path__)
    if module.name not in NON_SCENARIO_MODULES
}
