# CLAUDE Instructions


## Current status
The convoying sim (`convoying_sim/`) is complete.  The planning sim (`planning_sim/`) is partly built: the height map loader, terrain analyzer, driveability analyzer (per-heading mask, vehicle limits in the `vehicle` config), and plotter are real.  The costmap, planner, and speed profile are still stubs with placeholder outputs, so the next step is the costmap (which should use the per-heading driveability stack) and then the planner.  The vehicle limits in `config.yaml` are untuned guesses for the F1Tenth.  Run with `.venv\Scripts\python.exe`.


## What to do
@docs/proc.md

## How to do it
@docs/style.md

## Overall picture
@docs/spec.md

## Detailed log
Can be found under `./docs/notes.md`, only load it if needed.

## Hardware notes
Almost all changes to the system pipeline will need to be added to hardware.  The current list of differences versus the hardware can be seen in `./docs/to_hardware.md`.