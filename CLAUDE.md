# MTOFR_SIM

Simulator for platform-agnostic mission-type orders. Pure Python (numpy/scipy/matplotlib), no ROS/networking/async libs yet.

## Architecture (see `notes.md` for full history/rationale)

Three layers per platform, strictly one-directional in what each knows about:
- **Planner** (not built yet) — will write mission graphs, query capabilities via `backseater.capabilities()`.
- **Backseater** (`backseater/backseater.py`) — platform-agnostic. Holds the mission graph, relays typed capability requests to its Frontseater, never touches physical state. Exposes `capabilities()` as a passthrough to its Frontseater's registry — the real query path a planner uses instead of assuming what a platform can do. Exposes `status()` as a read-only snapshot (active node, blocked flag, per-primitive type/status/handle) — the query path a visualization tool uses instead of reaching into private state. Resolves Knowledge-id params (see below) and validates them against the platform's `Capability` before actuating; halts the mission gracefully (like an unsupported capability) on bad/unknown ids.
- **Frontseater** (e.g. `world/ground_plane/frontseater.py`) — platform-specific planning/control brain (MPC, capability implementations). Talks to its Hardware only through `send_controls`/`read_state`. Builds its own `CapabilityRegistry` declaratively in `__init__` and returns it from `capabilities()` — there is no separate central capability manifest; a planner learns what a platform can do only by querying that platform's own backseater.
- **Hardware** (e.g. `world/ground_plane/hardware.py`) — MCU/actuator-equivalent. Owns `WorldState`, pure `calculate_dynamics`. `read_state()` goes through a `PerfectSensor` stub — the seam for a future noisy sensor model.

`World` ticks: `backseater.update()` → `frontseater.update()` → `environment.step_dynamics_all(hardware)`.

Mission graph shape: `{"nodes": {id: {"primitives": {name: {"type", "params"}}}}, "edges": {id: [{"conditions": [...], "to": ...}]}, "start": id}`. Multiple primitives can be concurrently active *within* one node; only one node is active at a time (not yet a true concurrent automaton — see build order).

**Capability registry** (`capability/capability.py`): `ParamSpec` (name, `type`, plaintext description, `is_knowledge_ref` flag) + `Capability` (`ipl_type`, description, `params`, `validate()`, `describe()`) + `CapabilityRegistry` (keyed by `ipl_type`; `.get()`, `.all()`, `.describe()`). A primitive's `"type"` in the mission graph must match a `Capability.ipl_type`, and that same string is what gets passed straight through to `Frontseater.actuate()` — no separate internal capability name. Params that reference a known place/entity (e.g. `move_to`'s `target`) are Knowledge ids (`str`) in the mission graph; the matching `ParamSpec` has `is_knowledge_ref=True` and types itself as the Knowledge entry class (e.g. `Location`) rather than a primitive type, so `Capability.validate()`'s single `isinstance(value, spec.type)` check covers both primitive and knowledge-object params the same way. The Backseater resolves the id via `Knowledge.get()` before validating/actuating.

**Knowledge** (`knowledge/knowledge.py`): `Knowledge` is a typed id -> entry store (one instance per backseater, exposed as `backseater.knowledge`). Every entry type must subclass `KnowledgeEntry` and implement `describe()` (an ABC-enforced contract, mirroring `Capability`/`ParamSpec`'s self-description) so a planner/human can understand a platform-specific entry type without reading source. `Location` is the only built-in entry type so far; platforms/systems are expected to define their own. `Knowledge.all()` returns every entry regardless of type — the query path a visualization tool uses to browse a platform's full knowledge.

**Visualization** (`viz/`): `EnvironmentViewer` (`viz/base.py`) is the ABC an environment's spatial viewer implements — `configure_ax`/`render` draw onto a matplotlib `Axes` the viewer doesn't own, so it can be embedded rather than owning its own window. Each environment provides its own viewer under `world/<environment_name>/viz/` (e.g. `world/ground_plane/viz/plane_plotter.py`'s `PlanePlotter`), mirroring the Frontseater/Hardware per-environment split. `MissionGraphViewer` (`viz/mission_graph_view.py`) draws a mission graph (active node highlighted, hover for details) onto an `Axes` the same way, laid out via `compute_graph_layout()` — a deterministic force-directed (Fruchterman-Reingold-style) layout, not a columnar one, so a cycle's nodes spread into a polygon (e.g. a triangle for 3 nodes) instead of a straight row whose cycle-closing edge would have to curve around intervening nodes. Each edge's arrowhead is drawn at its midpoint rather than at the target node's coordinates — an arrowhead placed exactly at the target would render underneath that node's marker (drawn afterward, on top) and be invisible. Hover hit-testing happens in display (pixel) space rather than data space, since node/edge markers are a fixed size in points regardless of the current view — a data-unit tolerance would drift out of sync with the actual on-screen marker size across window resizes, pans, and zooms. `MissionDashboard` (`viz/dashboard.py`) is the top-level Tkinter tool: a platform dropdown, the embedded `EnvironmentViewer`, the mission graph, and a combined capability-status/knowledge panel switched by a selector — platform- and environment-agnostic, driven only through `World`/`Backseater`/`Knowledge`'s public query methods. It also owns the sim's pause state (`is_paused()`), which `main.py`'s loop checks before calling `world.step()`.

## Remaining build order (from `notes.md`, steps 1–2 done)

3. Minimal single-platform planner that queries capabilities via `backseater.capabilities()` and emits the mission graph (replacing the hardcoded dicts in `main.py`).
4. Real comms boundary with simulated delay, planner↔backseater and backseater↔frontseater. Make `poll_status` able to actually return `"timeout"`.
5. Staleness/timeout semantics on mission-graph edge conditions.
6. True concurrent active nodes (not just concurrent primitives within one node).
7. Second platform + cross-platform dependent edges + planner-level reconciliation on reconnect; comms-blackout stress test.
8. Object/world-state/OPORD layer (object lists, confidence, OPORD parsing) — lowest priority.

Tests land alongside each step above, in `tests/` (stdlib `unittest` — no test framework dependency added; pytest is not installed).

## Process

For any non-trivial feature or change (not one-line fixes):

1. **Interview first.** Ask clarifying questions throughout — before planning, and again whenever a decision comes up mid-implementation that the user hasn't already settled (e.g. naming, scope, library choices). Don't guess on ambiguous or high-blast-radius decisions.
2. **Plan, then get approval before writing code.** Produce a checklist of the concrete steps (tracked live, e.g. via TodoWrite), then summarize the proposed changes and wait for explicit approval/discussion before implementing anything.
3. **Implement incrementally**, checking items off the plan as they land.
4. **Test as you go, not after.** Write unit tests alongside each change, not as a separate deferred phase.
5. **Backfill missing coverage.** While touching a file, also add tests for previously-untested code nearby if it has none — pick a reasonable strategy for how much to cover (this project has no fixed rule for "how many tests," so judge case by case) rather than asking each time.
6. **Verify before handing back.** Run the full test suite and do a smoke test of the actual behavior (not just "tests pass") before reporting anything as done.
7. **Stop and wait for feedback** at the end of a batch of changes rather than continuing on to unrequested follow-on work.

## Coding style

- **No abbreviations in identifiers** — `environment` not `env`, `hardware_instance` not `hw`, `distance` not `dist`. Full words even when a term is used constantly. (Exception: pre-existing math/physics conventions like `dt`, `vx`, `vy`, `vtheta` stay as-is.)
- Module docstring is a single line: `"""Defines a world"""`.
- Class docstrings are 1–3 sentences; give a very brief overview of what something does, what the interface to work with it is, and any major *why* decisions.
- Docstrings on every function, primarily 1 line.
- Inline comments justify non-obvious decisions (`# persistent, not a task`, `# warm-start cache`), never restate the code.
- Type hints on public method signatures and dataclass-like fields; not enforced everywhere, not obsessive.
- ABCs (`abc.ABC`/`@abstractmethod`) define the layer interfaces (`Hardware`, `Frontseater`, `Environment`); concrete platform code lives under `world/<environment_name>/`.
- Debug prints are tagged by layer: `print(f"[Backseater] ...")`, `[Frontseater]`, `[World]`. Each layer takes a `debug: bool = False` constructor flag gating its own prints — off by default; a caller (e.g. `main.py`'s `DEBUG` constant) opts in per layer.
- Separate major sections in files with `#==========# Note #==========#` and major sections in classes/objects/functions with `#=====# Note #=====#`.  For minor sections, replace the `=` with `-`.

## Additional Rules
- Do not add yourself as a git collaborator, and do not use any git tools
- Especially, **do not add or commit any files to git**