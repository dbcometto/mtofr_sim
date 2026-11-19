# Specification

MTOFR_SIM simulates platform-agnostic mission-type orders for robots.  It is pure Python (numpy, scipy, matplotlib, pyyaml, Tkinter, and `ollama` for the local LLM), with no ROS, networking, or async libraries yet.

**Experiment plan**: compare human teleoperation (possibly a convoy system) to autonomy for logistics tasks, in sim and on hardware.  A human commander must accomplish pick-up/drop-off missions that arrive in a scripted order, and task performance is measured and analyzed.  The simulator carries the analysis; a hardware demo (F1Tenth-class) would reinforce it.

Design history is in `notes.md`; build order, open items, and known issues are in `roadmap.md`.



## Layout
- `main.py`: entry point (`.venv\Scripts\python.exe main.py`).  Config constants at the top (`DT`, `ENABLE_HEADLESS`, `DEBUG`, `ACTIVE_SCENARIO`).  It is environment-agnostic: the scenario builds the environment and its viewer.  All setup is under `if __name__ == "__main__":` because Windows "spawn" re-imports the script in every MPC worker process.
- `src/mtofr/`: the package, an editable install.  Its packages are layered; each imports only from the layers above it in this list, and each `__init__` docstring states its rule.
  1. `core/`: platform-, environment-, and mission-agnostic.  `state.py` (`State`), `sensor.py` (`Sensor`, `PerfectSensor`), `hardware.py` (`Hardware`), `environment.py` (`Environment`), `clock.py` (`Clock`), `capability.py` (`ParamSpec`, `Capability`, `CapabilityRegistry`).
  2. `database/`: `knowledge.py`, `knowledge_types.py`, `platform_keyed.py`, all re-exported from `mtofr.database`.
  3. `mission/`: what a mission is.  `graph.py` (the shape, as TypedDicts), `condition.py`, `validation.py`, `serialization.py`.
  4. `platform/`: the mission-aware brain layers and their assembly.  `frontseater.py`, `backseater.py`, `platform.py` (`Platform`, `PlatformSpec`).
  5. `viz/`: environment-agnostic dashboard and viewers.  `MissionDashboard` takes `World` duck-typed, so viz never imports environments.
  6. `environments/`: `world.py` (`World`), one folder per environment, and `anywhere/` for platforms that need none.
  7. `scenarios/`: one file per scenario, plus the `Scenario` enum and `SCENARIOS` registry.
- `tests/`: stdlib `unittest`, flat (`.venv\Scripts\python.exe -m unittest discover -s tests`).
- `scripts/mpc_profile.py`: tick-time and MPC-iteration profiler (not part of the suite).
- `mission_library/`: saved mission-graph JSON files (mission editor Save/Load).
- `llm/ollama/`: start/stop scripts for the local LLM service (see `llm_setup.md`).
- `docs/`: these documents.



## Platform Layers
Each platform is a Hardware → Frontseater → Backseater stack, the layers calling each other directly as separate processes would on a real robot.
- **Backseater** (`platform/backseater.py`): platform-agnostic.  Holds the mission graph and the active node, evaluates edges, and hands the active node's capability requests to its Frontseater.  Never touches physical state.  It owns the platform's identity (`platform_id` cascades to Frontseater and then Hardware), its `Clock`, its privilege level, and its three databases.
  - `capabilities()`: passthrough to the Frontseater's registry; the only way to learn what a platform can do.
  - `status()`: read-only snapshot of the active node, blocked flag, and per-request capability/status/inputs (under `"capabilities"`).  Status text comes fresh from `Frontseater.describe_status()`.
  - `query(database_name, key)` / `publish(database_name, key, value, timestamp=None)` across `"knowledge"`/`"mission"`/`"platform"`, plus `declare_knowledge_key()`.  A `"mission"` publish always goes through `write_mission()`.
  - Bind check, each tick before handing off: `mission.validation.find_capability_problems()` against the live `KnowledgeDatabase.types()`, the same check the editor runs against a graph's declarations.  Any problem halts the mission (blocked) without crashing.
- **Frontseater** (`platform/frontseater.py` ABC): the only bespoke part of each platform (planning/control, capability implementations).  Talks to Hardware only via `send_controls`/`read_state`, and reaches its Backseater via `frontseater.backseater`.
  - `capabilities()`: builds its own `CapabilityRegistry`.
  - `set_active_capabilities(capability_requests)`: called only when the active node's `{name: {"capability", "inputs", "outputs"}}` dict changes (by identity).  The Frontseater diffs it (start new, stop gone, leave unchanged) and decides how "running" works.
  - `describe_status() -> {"overall", "capabilities"}` (abstract, display-only), `compute_controls()`, `begin_update()`/`finish_update()` (lets MPC solves overlap across platforms), `shutdown()` (required).
  - `default_mission_graph()`: concrete base gives an inert `"startup"` node.  `Backseater` uses it when given `mission_graph=None`.
  - `attach(world, window_root=None)`: concrete no-op, for setup that needs `World` or the Tk root.
- **Hardware** (`core/hardware.py` ABC): MCU equivalent; owns a `State` and its own dynamics.  One abstract method, `step_dynamics(dt, environment)`, which queries the passive environment.  `read_state()` goes through a `Sensor` (default `PerfectSensor`, the identity).  Every subclass declares `environment_type` (an `Environment` class, or `None` = any), with no base default.
- **State** (`core/state.py`): a dataclass holding only `t` (s, sim time).  Each environment subclasses it with what it tracks.
- **Platform** (`platform/platform.py`): composition root, not a runtime layer.  `PlatformSpec(platform_id, build_frontseater, mission_graph=None, privilege_level=1, clock=None, sync_interval=1.0)` → `Platform` builds the stack and its `KnowledgeDatabase`, exposes `.hardware`/`.frontseater`/`.backseater`/`.knowledge_database`, and owns `attach()`/`shutdown()`.  It holds no reference to `World`.



## World and Tick
`World(environment, platforms)` (`environments/world.py`) is platform-count-agnostic; `world.platforms` maps platform_id → `Platform`.  `__init__` raises `TypeError` for a platform whose `hardware.environment_type` the environment doesn't satisfy, or whose `hardware.state` isn't the environment's `state_type`.  Each `step()`:
1. Per platform: `backseater.update()` → `frontseater.begin_update()` (all platforms) → `frontseater.finish_update()`.  Each call is wrapped individually; a platform that faults is skipped for the rest of the tick.
2. Per platform: `hardware.step_dynamics(dt, environment)`, isolated, and run even for a faulted platform (a vehicle keeps coasting).
3. Mesh sync: every backseater runs `sync_with_stale_peers()` against every other backseater (full connectivity assumed).



## Databases
All three belong to the Backseater, are stamped by its `Clock`, and carry `origin_platform_id` per entry (the platform that held the entry at its latest locally converted timestamp, transitively).  Every check happens write-side only, once, at the originating platform; there is no re-verification on receipt.
- **Knowledge** (`KnowledgeDatabase`, `backseater.knowledge_database`): arbitrary keys, each type-locked.  Use `declare(key, entry_type, value, timestamp=None, origin_platform_id=None)` before `get`/`set`; `set` raises on an undeclared key or a wrong type.  `declare()` works at any time.  `set_or_declare()` is the rare bypass mesh sync uses.  Also `timestamp_of`, `origin_of`, and `all()`.  Values may be plain types or `KnowledgeEntry` subclasses (`describe()` required; `Location(x, y)` is the only built-in, in `knowledge_types.py`).
- **Mission** (`MissionDatabase`): platform_id → `mission_graph` dict.  Writes from another platform go through `Backseater.write_mission(mission_graph, writer_platform_id, timestamp=None)`, which applies:
  - a privilege check (skipped for a self-write);
  - a type check;
  - `mission.validation.verify_mission_structure()`: every edge-condition key and binding key must be declared in the graph's `"knowledge"` section, otherwise `MissionStructuralError(ValueError)`;
  - `mission.validation.find_binding_problems()`: every capability request must be bindable by this platform (capability exists, no missing/unknown fields, exact key types).

  Edge reachability is not checked.
- **Platform** (`PlatformDatabase`): platform_id → `PlatformRecord(privilege_level, status: PlatformStatus(status, message), capabilities)`.  Gossiped per platform, and seeded at construction.  `status` and `capabilities` are meant to be self-write-only (not enforced yet).  `privilege_level` may only be changed by a strictly higher-privilege platform.



## Privilege, Mission Change, Sync
- **Privilege**: integer, 0 = highest (reserved), default 1, set by the harness.  A platform may write another's Mission entry only if its level is strictly lower (higher privilege).  Both levels are read from the target's own `PlatformDatabase`, and an unknown writer gets `PermissionError`.  Runtime reassignment is not implemented.
- **Mission change** (`_detect_mission_change()`, top of `update()`): when this platform's own Mission entry is a new object, it:
  1. stops the old capability requests;
  2. resets the new graph's knowledge keys to their declared defaults;
  3. swaps the graph and the parsed conditions, and clears blocked;
  4. activates the new start node in the same tick.

  This works for mesh-synced missions too.
- **Mesh sync** (`Backseater.sync_with(peer)`): reconciles Knowledge, Mission, and Platform in both directions, last-write-wins by locally converted timestamp.  Pulled timestamps are converted (`Clock.to_local()`), never re-stamped.  Received entries bypass the write gates.
  - Symmetric and idempotent, so either side may initiate.
  - `sync_with_stale_peers(peers)` only syncs peers older than `sync_interval`.
  - A per-pair checksum skips unchanged pairs.
- **Clock** (`core/clock.py`): wall time plus the platform's own offset, plus a per-peer offset table filled by each sync handshake.  There is no shared clock.



## Missions (`mission/`)
- **Shape** (`graph.py`, the single readable definition): `{"knowledge": {key: {"type", "value"}}, "nodes": {id: {"capabilities": {name: {"capability", "inputs", "outputs"}}}}, "edges": {id: [{"condition": [tokens], "to": id}]}, "start": id}`.  TypedDicts `MissionGraph`/`Node`/`CapabilityRequest`/`Edge`/`KnowledgeDeclaration` document it and type-hint public signatures; graphs stay plain dicts.  One node is active at a time; its capability requests run concurrently.
- `"inputs"`/`"outputs"` map a capability's field names to Knowledge keys, never literals.  They are the initial binding; a running capability may `query()`/`publish()` anything.
- **Conditions** (`condition.py`): pre-tokenized boolean expressions over Knowledge keys (e.g. `["(", "ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9, ")", "or", "ugv1/target_found", "is", "not", None]`).  `parse_condition()` (recursive descent, no `eval`) builds a tree of `Comparison`/`IsNone`/`And`/`Or`/`Not`, each with `evaluate(knowledge)` and `keys()`.  Precedence is `not` > `and` > `or`.  Capability status never drives transitions; capabilities write Knowledge.
- **Validation** (`validation.py`): `verify_mission_structure()` (every referenced key declared) and `find_capability_problems(request, known_types, registry)` / `find_binding_problems(graph, registry)`.  `known_types` is key → type: `declared_types(graph)` for the editor, assistant, and push; `KnowledgeDatabase.types()` for the Backseater's bind check.  Edge reachability is not checked.
- **Serialization** (`serialization.py`): JSON save/load with a type-name registry (`KNOWLEDGE_TYPES_BY_NAME`); a new `KnowledgeEntry` type needs one registry line.
- **Capabilities** (`core/capability.py`): `ParamSpec(name, type, description)` describes fields and drives the binding checks; it never resolves values.  Its `describe()` includes a `KnowledgeEntry` type's own `describe()`, so a human or LLM can read what a field means.  `Capability(ipl_type, description, inputs, outputs)` and `CapabilityRegistry` (`.get`, `.all`, `.describe`).  A capability request's `"capability"` equals an `ipl_type`.



## Scenarios (`scenarios/`)
- One file per scenario (`split.py`, `wait.py`, `village.py`, `village_default.py`), each holding its graphs (named `mission_<scenario>_<platform_id>`) and `SCENARIO = ScenarioConfig(...)`.
- `ScenarioConfig(build_environment, build_viewer, platforms: list[PlatformSpec])` (`base.py`): builders, not instances, so importing scenarios loads no map; duplicate ids raise.  A spec without a graph boots its Frontseater's default.
- `Scenario` (`SPLIT`, `WAIT`, `VILLAGE`, `VILLAGE_DEFAULT`) maps through `SCENARIOS` to its config.



## Environments, Maps, Platform Types
- Each environment lives in `environments/<environment_name>/`: `env.py` (its `Environment`, which declares `state_type`), `state.py` (that `State` subclass), the Hardware base its vehicles subclass (`hardware.py`), `sensors/`, `maps/` if it has any, and its viewer (`viz/`).  Each platform type lives in `environments/<environment_name>/platforms/<type>/`, or in `environments/anywhere/platforms/<type>/` if it needs no environment (built on `StationaryHardware`).  Each exports a `PlatformSpec` factory.
- **Anywhere platforms are placed in the host environment's terms**: `StationaryHardware` holds whatever `State` it's given and only advances `t`; the scenario picks the state type, and `World` checks it.  Future comms range would be an environment query, so core never knows geometry.
- **Ground plane** (`environments/ground_plane/`):
  - `GroundPlaneState(State)`: x, y, theta, vx, vy, vtheta (m, rad, world frame), plus `pose2d()`/`vel2d()`.
  - `GroundPlaneEnv(ground_map=None)` (`state_type = GroundPlaneState`) is passive and answers only `speed_multiplier_at(x, y)` and `is_blocked(x, y)`.  With no map it is unbounded and has no effect.
  - `GroundPlaneHardware` (`environment_type = GroundPlaneEnv`, abstract pure `calculate_dynamics(state, controls, dt, max_speed_multiplier=1.0)`): its default `step_dynamics` scales max speed by the multiplier at the true position, and rejects a step into a blocked cell (velocity zeroed).
  - `sensors/`: home for ground-plane sensors; empty until one is needed.
- **Bicycle UGV** (`environments/ground_plane/platforms/bicycle_ugv/`): `bicycle_ugv(platform_id, start_x, start_y, mission_graph=None, privilege_level=1)`.
  - `BicycleHardware` is a kinematic bicycle (`dynamics.bicycle_step()`, shared with the MPC).
  - `BicycleFrontseater` is the reference Frontseater, a plain if/elif over its capabilities:
    - `move_to` (`target`, `tolerance` → `arrived`; re-queries each tick);
    - `avoid` (`point`, `radius` → `registered`);
    - `stopwatch` (→ `elapsed_time` in sim seconds since start; never completes).
  - Its default mission loiters on `stopwatch`.
  - MPC (`mpc.solve_mpc`, SLSQP, `MPC_MAX_ITERATIONS` 20, warm-started) runs in one persistent worker process per platform.  The MPC knows nothing about terrain.
- **Stationary** (`environments/anywhere/hardware.py`): `StationaryHardware` (`environment_type = None`) never moves.
- **Maps** (`environments/ground_plane/maps/`): `load_map(name)` (None → no map) and `GroundMap.load(folder)`, which reads `<name>.yaml` plus `_cosmetic`/`_traversability`/`_regions` PNGs.
  - World (0, 0) is the image center, +y up, so sampling flips rows.
  - Traversability maps a hex color to `TraversabilityType(name, blocking, speed_multiplier)`.  A pixel snaps to the nearest declared color; an unmatched in-bounds pixel is passable, and off-map is blocked.
  - `RegionType(name, center_x, center_y)` is display-only.



## Visualization
- `EnvironmentViewer` (`viz/base.py`): ABC whose `configure_ax`/`render` draw onto a caller-owned Axes.  `render()` takes `show_traversability`/`show_regions`; the class has a `background_color`.
- `PlanePlotter` (`environments/ground_plane/viz/`, `PlanePlotter.for_environment(env)` for scenarios):
  - draws platforms as dots with a fixed on-screen heading marker;
  - draws the map's cosmetic image with toggleable overlays and a combined legend;
  - uses a gray off-map background.
- `MissionGraphViewer` (`viz/mission_graph_view.py`):
  - deterministic force-directed `compute_graph_layout()`, cached by `id(graph)` with a strong reference;
  - arrowheads at edge midpoints, and opposing edges curved apart by a quadratic bezier;
  - hover hit-testing in display pixels, with tooltips titled `Node:`/`Edge:`.
- `PlatformOverviewViewer`: one row per platform (`platform_id: "active_node"`); hover shows active capabilities, and a click selects the platform.
- `MissionDashboard` (`viz/dashboard.py`, Tkinter):
  - a platform dropdown that defaults to "Mission Overview";
  - the environment view with overlay checkboxes, scroll-zoom, and drag-pan;
  - the "Mission Overview" panel (platform list, or one platform's graph with an edge-label toggle and a back button);
  - a capability/knowledge panel, defaulting to Knowledge (Name/Type/Value), which stays empty in overview mode;
  - the pause state (`is_paused()`).

  `main.py` drives it cooperatively rather than with `mainloop()`.



## Interface Platform and Mission Editor
- `interface(platform_id, initial_state, ...)` (`environments/anywhere/platforms/interface/`, privilege 0): `MissionEditorFrontseater` + `ConsoleHardware` (a `StationaryHardware`, placed at `initial_state`, e.g. a `GroundPlaneState`).
  - Its one capability, `show_interface`, opens or closes the editor window.  Its default graph runs that capability unconditionally.
  - Editing itself is not a capability.
  - `attach()` installs the window factory (`_NullWindow` when headless).
- `MissionEditorWindow` (`mission_editor/window.py`): a Toplevel on the dashboard's root.
  - It edits one draft at a time, loaded from a live platform (deep-copied), from a file (`mission/serialization.py`), or blank.
  - Every mutation goes through `_set_draft()`, using pure `graph_draft.py` helpers that return new dicts.  This gives undo/redo (`UNDO_HISTORY_LIMIT`, Ctrl+Z/Y bound on the window).
  - Validate, then Push through `write_mission()`.  The editor is just another writer.
  - Tabs:
    - **Live Control** (default): the target's Knowledge, edited live via `set()` and refreshed each second.
    - **Editor**: resizable panes of Nodes+Capabilities | Edges | Knowledge, with Add/Edit/Remove and double-click editing.
    - **Graph**: Draft/Live preview.
  - A Console logs every action, and warns when the push target differs from the draft's source.
  - Conditions are typed as raw token literals (`ast.literal_eval` + `parse_condition()`).
  - Knowledge value forms come from `constructor_fields()` introspection (`mission/serialization.py`).
  - Renaming a key cascades to its bindings and conditions.  A token counts as a key when the next token is a comparison operator or `"is"`.



## LLM Assistant
- Ollama runs `qwen3.5:4b` locally on the CPU (setup: `llm_setup.md`).  Settings are in `environments/anywhere/platforms/interface/agent/config.py`: model, `NUM_CTX`, `THINK`, `TEMPERATURE`, `MAX_REPLY_TOKENS`, `MAX_NUDGES`, `MAX_ITERATIONS`, `KEEP_ALIVE`.
- `agent/agent.py`: the streaming tool-call loop.  The caller injects tools and `run_tool`; `should_stop` serves the Stop button; it chains tool calls and logs per-call timings.
- `mission_editor/assistant_window.py`: opened by the editor's "Assistant...".
  - A chat with its own target dropdown, shared with the editor.
  - An "Enable thinking" toggle (only `think=`; thinking is always displayed).
  - A live wait counter and progress bar.
  - Turns run on a worker thread, with events marshalled over a queue.  One user message is one undo step.
- `assistant_tools.py`: 14 tools, 1:1 with the `graph_draft.py` mutators.  `add_capability`/`edit_capability` refuse unbindable capability requests, with the fix in the error.
- `assistant_prompt.py`: the system prompt (hand-edited by the user) plus the per-turn message.  That message is SITUATION (target, WORLD frame/map/regions/terrain/position and live active node as information only, capabilities, draft) followed by MISSION (the request).
- `assistant_session.py`: history keeps only requests and final replies.  `_detect_stall` nudges a reply that has no real tool calls (calls typed as text, truncated, or announced but not done).
