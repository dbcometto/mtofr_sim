# Ben's Thoughts

For human editing only




## Organization
- Maps should be moved under the environment they pertain to (groundplane)
- clock and capability should be with backseater and ABC platform/frontseater/hardware/etc under a core package.  Specific hardware and frontseater implementations go under their respective environments.  High-level world folder should be renamed environments.  world.base should be split:
    - core/state.py: WorldState
    - core/hardware.py: Hardware and PerfectSensor. The sensor is a hardware concern (how the hardware reports state), so it belongs there rather than with the state.
    - core/frontseater.py: Frontseater
    - core/environment.py: Environment
    - world.py stays under environments 
    - platform.py goes under core
    - Giving core/ a one-line rule in its __init__ docstring, like “platform-agnostic runtime pieces that also run on hardware,” keeps it honest.
- condition feels like its missing the rest of the mission specification... which seems like it should be its own part of the package.  Where is that defined?  Oh, platform keyed database?  Yeah, the mission definition should be pulled into `mission`, so it is separate, readable, and understandable
- missions.py feels out of place: rename to scenarios, and split into multiple files

## UI
- Webserver
- Shorthand for UI: interrupts, always-on capabilities, submissions


