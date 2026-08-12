# MTOFR_SIM

Simulator for platform-agnostic mission-type orders. Pure Python (numpy/scipy/matplotlib), no ROS/networking/async libs yet.

## Architecture (see `notes.md` for full history/rationale)

Three layers per platform, strictly one-directional in what each knows about:
- **Planner** (not built yet) — will write mission graphs, query capabilities via `backseater.capabilities()`.
- **Backseater** (`backseater/backseater.py`) — platform-agnostic. Holds the mission graph, relays typed capability requests to its Frontseater, never touches physical state. Exposes `capabilities()` as a passthrough to its Frontseater's registry — the real query path a planner uses instead of assuming what a platform can do. Resolves Memory-id params (see below) and validates them against the platform's `Capability` before actuating; halts the mission gracefully (like an unsupported capability) on bad/unknown ids.
- **Frontseater** (e.g. `world/ground_plane/frontseater.py`) — platform-specific planning/control brain (MPC, capability implementations). Talks to its Hardware only through `send_controls`/`read_state`. Builds its own `CapabilityRegistry` declaratively in `__init__` and returns it from `capabilities()` — there is no separate central capability manifest; a planner learns what a platform can do only by querying that platform's own backseater.
- **Hardware** (e.g. `world/ground_plane/hardware.py`) — MCU/actuator-equivalent. Owns `WorldState`, pure `calculate_dynamics`. `read_state()` goes through a `PerfectSensor` stub — the seam for a future noisy sensor model.

`World` ticks: `backseater.update()` → `frontseater.update()` → `environment.step_dynamics_all(hardware)`.

Mission graph shape: `{"nodes": {id: {"primitives": {name: {"type", "params"}}}}, "edges": {id: [{"conditions": [...], "to": ...}]}, "start": id}`. Multiple primitives can be concurrently active *within* one node; only one node is active at a time (not yet a true concurrent automaton — see build order).

**Capability registry** (`capability/capability.py`): `ParamSpec` (name, `type`, plaintext description, `is_memory_ref` flag) + `Capability` (`ipl_type`, description, `params`, `validate()`, `describe()`) + `CapabilityRegistry` (keyed by `ipl_type`; `.get()`, `.all()`, `.describe()`). A primitive's `"type"` in the mission graph must match a `Capability.ipl_type`, and that same string is what gets passed straight through to `Frontseater.actuate()` — no separate internal capability name. Params that reference a known place/entity (e.g. `move_to`'s `target`) are Memory ids (`str`) in the mission graph; the matching `ParamSpec` has `is_memory_ref=True` and types itself as the Memory entry class (e.g. `Location`) rather than a primitive type, so `Capability.validate()`'s single `isinstance(value, spec.type)` check covers both primitive and memory-object params the same way. The Backseater resolves the id via `Memory.get()` before validating/actuating.

**Memory** (`memory/memory.py`): `Memory` is a typed id -> entry store. Every entry type must subclass `MemoryEntry` and implement `describe()` (an ABC-enforced contract, mirroring `Capability`/`ParamSpec`'s self-description) so a planner/human can understand a platform-specific entry type without reading source. `Location` is the only built-in entry type so far; platforms/systems are expected to define their own.

## Remaining build order (from `notes.md`, steps 1–2 done)

3. Minimal single-platform planner that queries capabilities via `backseater.capabilities()` and emits the mission graph (replacing the hardcoded dicts in `main.py`).
4. Real comms boundary with simulated delay, planner↔backseater and backseater↔frontseater. Make `poll_status` able to actually return `"timeout"`.
5. Staleness/timeout semantics on mission-graph edge conditions.
6. True concurrent active nodes (not just concurrent primitives within one node).
7. Second platform + cross-platform dependent edges + planner-level reconciliation on reconnect; comms-blackout stress test.
8. Object/world-state/OPORD layer (object lists, confidence, OPORD parsing) — lowest priority.

Tests land alongside each step above, in `tests/` (stdlib `unittest` — no test framework dependency added; pytest is not installed).

## Coding style

- **No abbreviations in identifiers** — `environment` not `env`, `hardware_instance` not `hw`, `distance` not `dist`. Full words even when a term is used constantly. (Exception: pre-existing math/physics conventions like `dt`, `vx`, `vy`, `vtheta` stay as-is.)
- Module docstring is a single line: `"""Defines a world"""`.
- Class docstrings are 1–3 sentences; give a very brief overview of what something does, what the interface to work with it is, and any major *why* decisions.
- Docstrings on every function, primarily 1 line.
- Inline comments justify non-obvious decisions (`# persistent, not a task`, `# warm-start cache`), never restate the code.
- Type hints on public method signatures and dataclass-like fields; not enforced everywhere, not obsessive.
- ABCs (`abc.ABC`/`@abstractmethod`) define the layer interfaces (`Hardware`, `Frontseater`, `Environment`); concrete platform code lives under `world/<environment_name>/`.
- Debug prints are tagged by layer: `print(f"[Backseater] ...")`, `[Frontseater]`, `[World]`.
- Separate major sections in files with `#==========# Note #==========#` and major sections in classes/objects/functions with `#=====# Note #=====#`.  For minor sections, replace the `=` with `-`.