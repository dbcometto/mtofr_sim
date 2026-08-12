# Notes


## Status 12 Aug 26 (evening)
(Written by Claude)

Step 2 of the build order done: promoted the capability dictionary from a hardcoded per-frontseater dict to a real, self-describing registry, and gave the Backseater a real query path instead of assuming.

- New `capability/capability.py`: `ParamSpec` (name, `type`, plaintext description, `is_memory_ref` flag), `Capability` (`ipl_type`, description, `params` tuple, `validate()`, `describe()`), `CapabilityRegistry` (keyed by `ipl_type`, `.get()`, `.all()`, `.describe()`). Each `Frontseater` builds its own registry declaratively in `__init__` and returns it from `capabilities()` — no separate central manifest; a planner discovers what a platform can do only by querying that platform's own backseater, which now has a `capabilities()` passthrough method to `frontseater.capabilities()`.
- Memory params (e.g. `move_to`'s `target`, `avoid`'s `point`) are now Memory-id references, not raw tuples: a `ParamSpec` with `is_memory_ref=True` types itself as the Memory entry class (e.g. `Location`) rather than a primitive type, so the same `isinstance(value, spec.type)` check in `Capability.validate()` covers both primitive and memory-object params uniformly. The Backseater resolves ids to entries (`Memory.get(id)`) before validating/actuating; unknown ids or type mismatches halt the mission gracefully (same path as an unsupported capability) instead of crashing.
- Memory entries got their own self-description contract to match capabilities: new `MemoryEntry` ABC (`memory/memory.py`) requires every entry type — built-in or user-defined per platform — to implement `describe()`. `Location` now implements it. This means a planner/human can fully understand both "what can this platform do" and "what does this parameter type mean" without reading source, straight from `CapabilityRegistry.describe()` (which includes each memory-ref param's `type.describe()` inline).
- Also fixed a small pre-existing wart while touching this code: `capabilities()` used to map an IPL type to a *different* internal capability name (`"move_to"` -> `"navigate"`, `"avoid"` -> `"set_avoid"`) for no real reason. Now `Capability.ipl_type` *is* what gets passed to `actuate()` — one name, not two.
- `BicycleFrontseater`'s `_active_target` and `_avoid_regions` now hold `Location` objects (`.x`/`.y`) instead of raw tuples/indices, since actuate() now receives resolved Memory entries.
- `main.py`'s hardcoded mission dicts now reference named Memory locations (e.g. `"target": "northeast"`) instead of literal `(x, y)` tuples, with `Memory` populated up front in the "Set up" section.
- First `tests/` directory landed (stdlib `unittest`, no new dependency — pytest isn't installed and the project stays pure Python): `test_capability.py`, `test_memory.py`, `test_backseater_capability_resolution.py` — 15 tests total, covering `Capability`/`ParamSpec` validation and description, `MemoryEntry`'s enforced contract, and an end-to-end Backseater run (including the unknown-memory-id failure path). All pass; also re-verified with a full headless multi-tick run of `main.py`'s wiring.

Left off here — step 3 (a minimal single-platform planner querying `backseater.capabilities()` to emit the mission graph, replacing the hardcoded dicts in `main.py`) is next and untouched.


## Status 12 Aug 26
(Written by Claude)

Terminology reframe, adopted from external architecture notes on the planner/mission-graph/backseater-frontseater design:
- "Agent" -> "Backseater": platform-agnostic relay between a mission graph and a Frontseater. Never sends controls, only capability requests (`actuate`/`poll_status`/`cancel`).
- "Platform" (the software role, not the physical robot) split into two: "Frontseater" (platform-specific planning/control brain — the MPC, target/avoid-region tracking, capability implementation) and "Hardware" (the MCU/actuator-equivalent layer — owns `WorldState`, runs `calculate_dynamics`, exposes only `send_controls`/`read_state`). This mirrors a real robot: a companion computer (frontseater) talking to firmware (hardware) rather than one object doing both.
- `Hardware.read_state()` goes through a `PerfectSensor` stub that returns ground truth unchanged — a placeholder seam so a future noisy/partial sensor model can be swapped in without changing the Frontseater interface.
- Concretely: `BicycleUGV` (one class, owned state + ran its own MPC) split into `BicycleHardware` (dynamics only) and `BicycleFrontseater` (MPC only, holds a reference to its `hardware` and reads/writes it only through `send_controls`/`read_state`). The Frontseater's MPC rollout still calls `hardware.calculate_dynamics(...)` directly as a pure prediction model (this is legitimate — real planners often carry their own internal dynamics model for lookahead, which just happens to match the hardware's model exactly in sim).
- No behavior change from this split; confirmed via headless smoke test (see `main.py` for wiring: `BicycleHardware` -> `BicycleFrontseater(hardware=...)` -> `Backseater(frontseater=...)`).
- Naming convention note: avoid abbreviations in identifiers (e.g. `environment` not `env`, `hardware_instance` not `hw`) — applies going forward.

Confirmed architecture-alignment finding (from reviewing the codebase against the external doc): the hard part — keeping control-computation logic out of the relay/mission-graph layer — was already done correctly before this rename, in the commit "platform/agent separation architected." This session's changes are a pure terminology/structure alignment, not a behavior fix.

Agreed incremental build order for closing remaining gaps vs. the target design (planner / backseater / frontseater / hardware, capability dictionary, mission graph, comms):
1. Rename Agent->Backseater + split Platform into Frontseater/Hardware. **(done, this entry)**
2. Promote the capability dictionary from a per-platform hardcoded dict (`Frontseater.capabilities()`) to a real registry with typed inputs + plaintext descriptions, and a real query path (Backseater asks Frontseater, rather than assuming).
3. Build a minimal planner (single platform, no comms boundary yet) that queries the capability dictionary via the backseater and emits the mission graph, replacing the hardcoded dicts in `main.py`.
4. Introduce a real comms boundary with simulated delay between planner<->backseater and backseater<->frontseater (in-process/threaded shim is fine, doesn't need real sockets yet). Make `poll_status` able to actually return `"timeout"` for the first time.
5. Add staleness/timeout semantics to mission-graph edges (e.g. "unsatisfied if last update older than threshold"), testable single-platform once step 4 lands.
6. Support true concurrent active nodes in the mission graph (today only one node is ever active at a time, even though multiple primitives within a node already run concurrently) — do this after 4-5 so timeout/staleness logic doesn't need retrofitting onto a more complex graph.
7. Add a second platform + backseater and tackle cross-platform dependent edges + planner-level reconciliation on reconnect — the hardest open item, only testable with two real backseater/frontseater pairs talking through the step-4 comms shim. Write the comms-blackout stress test here.
8. Object/world-state/OPORD layer (object lists, confidence, OPORD parsing) — lowest priority, deferred until the three-tier skeleton (1-7) is solid.

Tests should land alongside each step above, not as a separate phase — there is currently no `tests/` directory at all.



## Status 10 Aug 26
(Written by Claude)

Architecture landed on today (after several deliberate reframes):

World — owns Environment + agents dict, runs the tick loop: agents update (issue/poll tasks) → environment steps physical dynamics
Agent — holds a mission graph, memory, and per-primitive task handles. Never touches WorldState — only issues capability requests and reads status. Translates IPL primitive types (move_to, avoid) into platform-specific capability names via platform.capabilities(), so Agent stays fully platform-agnostic
Platform (BicycleUGV) — owns physical state, runs its own internal MPC (scipy.optimize.minimize, warm-started) to compute controls each tick based on whatever tasks are currently active. Exposes actuate/poll_status/cancel (async-style, even though currently synchronous) plus persistent avoid regions
Environment (GroundPlaneEnv) — infinite plane, no bounds/collisions, just steps each platform's dynamics
Memory — per-agent typed store (currently Location), private per platform (no shared ground truth between agents)
viz (PlanePlotter) — live matplotlib position + heading arrow, headless-mode toggle in main.py

Mission representation: graph-based — nodes hold multiple primitives, edges hold explicit conditions referencing specific primitive indices and required statuses (e.g. {"primitive": 1, "status": "success"}). Replaced an earlier flat-list version once concurrency/multi-primitive needs became clear.

Key design principles established:

Continuous capabilities (move_to, avoid) are persistent platform state feeding one combined MPC cost — not independent per-primitive control outputs
Discrete capabilities use actuate/poll/cancel with success/fail/timeout, modeled loosely on ROS-action-style semantics but kept custom/minimal for now
Platform reports task-completion status; Agent only reasons about status, never raw physical state
LLM will write DSL (not raw Python/dicts); a compiler layer validates and translates DSL → the graph structure Agent consumes — keeps LLM output safely inspectable/rejectable before reaching hardware
The graph itself is a candidate artifact for human-commander review/approval — directly supports the thesis's human-oversight claim

Known open items, deferred intentionally:

avoid-as-mission-node is mechanically working but conceptually awkward (fires as a normal primitive with no real "done" state; a cleaner separate mechanism may be warranted later)
No validation layer yet for LLM/DSL-generated graphs (primitive indices, capability names) — designed for, not built
Only one platform type and one environment exist — abstraction boundaries are unvalidated by a second real implementation
No multi-agent test yet, despite World/Agent architecture supporting it in principle
The actual thesis comparison (structured vs. unstructured mission execution on reliability/adaptability/coordination/oversight) hasn't started

Assessment: solid, working foundation consistent with the thesis direction — genuine architectural validation happened today, but this is infrastructure, not yet evidence for the thesis claim itself.




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