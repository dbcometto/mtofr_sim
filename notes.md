# Notes




## Pre-notes 8 Aug 26
(Written by Claude)

The system must control a robot in two different ways. Some actions are continuous. The optimal controller must move the robot toward a goal. Other actions are discrete. The robot must do the action one time, not gradually. The system must not try to blend these two types into one method. Each method must handle only the type of action it can control well. *MTOFR just puts the robot at the right place at the right time and signals for an action*

The mtofr system must not control hardware directly. The mtofr system must decide where the robot must be and when the robot must act. The mtofr system must send a command to another process to perform the action. The other process must control the camera, the gripper, or other hardware. This separation must keep mtofr simple. This separation must also let other hardware programs change without changes to mtofr.

An action may take time to finish. The mtofr system must start the action and then check its status. The status must be "waiting", "success", "fail", or "timeout". The mtofr system must also be able to cancel an action before it finishes. This capability is necessary if a higher priority task must interrupt the current action. The team must build a simple version of this system first. The team may build a more complex version, like a graph structure, at a later time.


## Status 7 Aug 26
(Written by Claude)

**Working:** Full sim loop runs live: `World.step()` → agents plan → env steps dynamics → mission update → viz renders position + heading arrow. Ctrl+C to exit.

**Package layout** (`src/mtofr/`, editable install):
- `world/base.py` — `WorldState`, `Platform` (ABC), `Environment` (ABC)
- `world/world.py` — `World` (owns env + agents, sequences plan→dynamics→mission)
- `world/ground_plane/env.py` — `GroundPlaneEnv` (infinite plane, no bounds/collisions)
- `world/ground_plane/platforms.py` — `BicycleUGV` (kinematic bicycle model, vel+steer control)
- `agent/agent.py` — `Agent` (wraps platform + memory + mission_state; `plan` returns fixed controls set at construction; `update_mission` is a no-op stub)
- `memory/memory.py` — `Memory` (typed key-store), `Location`
- `viz/plane_plotter.py` — `PlanePlotter` (live matplotlib dot + heading arrow per agent)
- `main.py` (repo root) — wires one `BicycleUGV` + `Agent` + `Memory` into a `World`, runs fixed-timestep loop with drift monitoring

**Not yet built:**
- `Primitive` base + `Visit` (next planned step — will reference `Memory`'s `Location` entries)
- Real `plan()` logic (currently hardcoded constant controls)
- Mission state schema / actual mission tracking
- Comms/SSH layer, OPORD→primitive pipeline, object database — all deferred

**Known open questions / soft spots:**
- No validation that `controls` dict has an entry for every agent each tick (silent `KeyError` risk once >1 agent)
- `collides`/bounds concept dropped entirely for now (infinite world, no obstacles)
- Follow-type primitives will need cross-agent info flow (comms/perception) since each agen