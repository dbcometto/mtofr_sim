# Notes


## Status 12 Aug 26 (mission visualization tool polish)
(Written by Claude)

Follow-up polish pass on the mission visualization tool after initial user feedback, fixing several real bugs rather than just cosmetics:

- **Mission graph layout replaced entirely**: `compute_layered_layout()` (BFS-column layout) is gone, replaced by `compute_graph_layout()` — a deterministic force-directed (Fruchterman-Reingold-style) layout (every node pair repels, every edge attracts, fixed iterations with linear cooling; nodes start evenly spaced on a circle rather than randomly, so the same graph always lays out the same way). The columnar layout put every node in a cycle on one straight row, so a cycle-closing edge had to curve over/around the intervening nodes to stay visible — and that curve's rendered peak didn't match the stored hover point, making it impossible to hover over. The force-directed layout naturally spreads a 3-node cycle into a triangle, so every edge (including the cycle-closer) is a short straight line: no more curve-vs-hover mismatch, and no more curve-drawing code needed at all.
- **Node/edge clipping at small window sizes fixed**: matplotlib's autoscale margins are a percentage of the data range, which collapsed to nearly nothing for graphs where a whole row of nodes shared one y-value — clipping node markers and edge labels at small window sizes. Fixed by computing explicit axis limits with fixed padding around the node layout instead of relying on autoscale, plus `clip_on=False` on every node/edge/label artist as a backstop.
- **Hover made resize/pan/zoom-safe**: node and edge markers are a fixed size in *points* (screen space) regardless of the current view, but hover hit-testing used to compare against a tolerance in *data* units — so it silently drifted out of sync with the actual on-screen marker size whenever the window resized (changing the data-to-pixel ratio). `MissionGraphViewer` now hit-tests in *display* (pixel) space, converting stored data positions via `ax.transData` and comparing against a tolerance derived from the marker's real point size (via the figure's DPI) — this stays correct across resize, pan, and zoom.
- **Hover tooltip now stays on-screen**: it flips its offset toward the panel's interior (using the canvas's actual pixel dimensions) whenever the anchor point is near the right/top edge, instead of always growing right/up and running off the canvas.
- **Dashboard visual pass**: environment/mission-graph/capability-knowledge panels are now `ttk.LabelFrame`s with visible borders instead of bare, unbordered frames; combobox text-on-white-on-white was a `ttk` gotcha (the dropdown's popup list is a plain Tk `Listbox`, invisible to `ttk.Style` — needs `option_add` on top of the style config); environment view now fills its panel and has a working pan/zoom toolbar (`NavigationToolbar2Tk`), with the dashboard preserving the current view limits across per-tick redraws so a user's pan/zoom doesn't reset every frame; Knowledge panel is now three columns (Type/Name/Value) instead of one repr string; edge hover text now includes the source/target node ids, not just the bare condition.
- **Simulator/visualizer lag desync fixed**: previously the dashboard only refreshed once per outer loop iteration in `main.py`, so a catch-up burst (several `world.step()` calls back-to-back after falling behind wall-clock) rendered nothing until the whole burst finished, then jumped to the final state. It now refreshes after every individual step during a catch-up burst. (Not fixed, and out of scope for this pass: a single unusually slow computation — e.g. one slow MPC solve — still freezes the UI for its duration, since Tk can only be pumped between Python calls, not during one; that would need running the sim on a separate thread.)
- **Edge arrowheads were invisible**: `ax.annotate()` was drawing each edge's arrowhead exactly at the target node's coordinates, which sat completely hidden underneath that node's marker (drawn afterward, on top, per the fix above). Split into a plain full-length line plus a separate short arrowhead centered at the edge's midpoint — visible regardless of node overlap, at the user's suggestion.

Tests: `test_mission_graph_view.py` rewritten around the new layout function's guarantees (unique positions, cycle non-collinearity, determinism) instead of columnar assumptions; hover tests updated to use display-space coordinates; added a regression test pinning the arrowhead to the midpoint. 90 tests total.

Known limitation, deferred: `compute_graph_layout()`'s force simulation is O(n^2) per iteration and untested at scale — fine for the small missions built so far, but layout quality/performance with many more nodes and cycles is an open question for whenever a mission graph grows large enough to matter.

This closes out the mission visualization tool as a distinct piece of work (the "2.5" step from the previous entry) — remaining open item is still step 3 below, untouched throughout this and the previous entry.


## Status 12 Aug 26 (mission visualization tool)
(Written by Claude)

Built the mission status visualization tool discussed as the "2.5" step between the capability registry (step 2) and the planner (step 3): a platform-agnostic Tkinter dashboard, replacing the old standalone `PlanePlotter` window.

- New `viz/base.py`: `EnvironmentViewer` ABC (`configure_ax`/`render` draw onto a caller-owned `Axes`) so a spatial viewer can be embedded instead of owning its own window. `plane_plotter.py` moved from the generic `viz/` package to `world/ground_plane/viz/plane_plotter.py` and now implements this interface, mirroring the existing Frontseater/Hardware per-environment split — every environment is expected to supply its own viewer the same way.
- New `viz/mission_graph_view.py`: `compute_layered_layout()` (BFS-column layout, no graph-layout dependency needed at this size) plus `MissionGraphViewer`, which draws nodes/edges onto an `Axes`, highlights the active node, and tracks node/edge positions for hover lookup. Edges whose target is more than one column away (e.g. a mission cycle closing back several nodes) are bowed out via `connectionstyle="arc3,rad=..."` — a straight line for those was rendering directly underneath an intervening node's marker and disappearing, which looked like the edge was silently missing.
- New `viz/dashboard.py`: `MissionDashboard`, one Tkinter window built from a platform dropdown, the embedded `EnvironmentViewer` (every platform drawn, selected one highlighted), the mission graph (with an edge-label toggle and a cursor-following hover tooltip for both nodes and edges), and a single capability-status/knowledge panel switched via a selector — not two separately-stacked panels. Also owns the sim's pause state (`is_paused()` / a Pause button), which `main.py`'s loop checks before calling `world.step()`, while still refreshing the dashboard on every tick so it stays responsive while paused. Dark-gray `ttk` theme throughout; `Treeview` panels get real scrollbars plus a mouse-wheel binding (true pixel-smooth scrolling isn't feasible with `ttk.Treeview`'s fixed row height without a custom canvas, so this is row-based, not pixel-smooth).
- `Backseater` gained `status()` — a read-only snapshot (active node, blocked flag, per-primitive type/status/handle) — so the dashboard (or any future consumer) can introspect mission progress without reaching into private state, the same query-path philosophy as `capabilities()`.
- Renamed the `Memory` concept to `Knowledge` everywhere, at the user's request after discussing dashboard panel naming (the panel browsing a platform's known locations/entities was going to be relabeled, which raised the question of whether the whole concept should be renamed to match): `memory/memory.py` -> `knowledge/knowledge.py`, `Memory`/`MemoryEntry` -> `Knowledge`/`KnowledgeEntry`, `backseater.memory` -> `backseater.knowledge`, `ParamSpec.is_memory_ref` -> `is_knowledge_ref`, and all docs/tests updated to match. Pure rename, no behavior change.
- `main.py`'s two test missions had their node ids renamed from `n1`/`n2`/`n3` to descriptive names (e.g. `head_east`, `loop_west`, `return_southeast`) for readability in the new mission graph panel.
- Debug prints across `Backseater`/`BicycleFrontseater` are now gated behind a `debug: bool = False` constructor flag (matching `World`'s existing flag) instead of always firing — off by default, wired up via a `DEBUG` constant in `main.py`'s config section. The prints themselves are unchanged, just opt-in.
- 84 tests total (up from 67), covering all of the above; `main.py` smoke-tested with the dashboard running.

Still left off at step 3 (the minimal single-platform planner) — untouched this session.


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