# Specification

MTOFR_SIM simulates platform-agnostic mission-type orders for robots.  It is pure Python (numpy, scipy, matplotlib, pyyaml, Tkinter, and `ollama` for the local LLM), with no ROS, networking, or async libraries yet.

**Experiment plan**: compare human teleoperation (possibly a convoy system) to autonomy for logistics tasks, in sim and on hardware.  A human commander must accomplish pick-up/drop-off missions that arrive in a scripted order, and task performance is measured and analyzed.  The simulator carries the analysis; a hardware demo (F1Tenth-class) would reinforce it.

Design history is in `notes.md`; build order, open items, and known issues are in `roadmap.md`.



## Layout
- `main.py`: entry point (`.venv\Scripts\python.exe main.py`).  Config constants at the top (`DT`, `ENABLE_HEADLESS`, `DEBUG`, `ACTIVE_SCENARIO`, a scenario file name).  It is environment-agnostic: the scenario builds the environment and its viewer.  All setup is under `if __name__ == "__main__":` because Windows "spawn" re-imports the script in every MPC worker process.
- `src/mtofr/`: the package, an editable install.  Its packages are layered; each imports only from the layers above it in this list, and each `__init__` docstring states its rule.
  1. `core/`: platform-, environment-, and mission-agnostic.  `state.py` (`State`), `sensor.py` (`Sensor`, `PerfectSensor`), `hardware.py` (`Hardware`), `environment.py` (`Environment`), `clock.py` (`Clock`), `capability.py` (`ParamSpec`, `Capability`, `CapabilityRegistry`).
  2. `database/`: `knowledge.py`, the `knowledge_types/` package (one file per type), `platform_keyed.py`, all re-exported from `mtofr.database`.
  3. `mission/`: what a mission is.  `graph.py` (the shape, as TypedDicts), `condition.py`, `validation.py`, `serialization.py`.
  4. `platform/`: the mission-aware brain layers and their assembly.  `frontseater.py`, `backseater.py`, `platform.py` (`Platform`, `PlatformSpec`), `common_capabilities.py` (`Stopwatch`).
  5. `viz/`: environment-agnostic dashboard and viewers.  `MissionDashboard` takes `World` duck-typed, so viz never imports environments.
  6. `environments/`: `world.py` (`World`) and one folder per environment.
  7. `scenarios/`: one file per scenario, discovered into `SCENARIOS` by file name.
- `tests/`: stdlib `unittest`, flat (`.venv\Scripts\python.exe -m unittest discover -s tests`).
- `scripts/mpc_profile.py`: tick-time and MPC-iteration profiler (not part of the suite).
- `mission_library/`: saved mission-graph JSON files (mission editor Save/Load).
- `llm/ollama/`: start/stop scripts for the local LLM service (see `llm_setup.md`).
- `docs/`: these documents.  `design.md` is the design philosophy and math behind the architecture.  `checklists.md` covers adding a capability, platform, environment, Knowledge type, or scenario.



## Platform Layers
Each platform is a Hardware → Frontseater → Backseater stack, the layers calling each other directly as separate processes would on a real robot.
- **Backseater** (`platform/backseater.py`): platform-agnostic.  Holds the mission graph and the active node, evaluates edges, and hands the active node's capability requests to its Frontseater.  Never touches physical state.  It owns the platform's identity (`platform_id` cascades to Frontseater and then Hardware), its `Clock`, its privilege level, and its three databases.
  - `capabilities()`: passthrough to the Frontseater's registry; the only way to learn what a platform can do.
  - `status()`: read-only snapshot of the active node, blocked flag, and per-request capability/status/inputs (under `"capabilities"`).  Status text comes fresh from `Frontseater.describe_status()`.
  - `query(database_name, key)` / `publish(database_name, key, value, timestamp=None)` across `"knowledge"`/`"mission"`/`"platform"`, plus `declare_knowledge_key()`.  A `"mission"` publish always goes through `write_mission()`.
  - `knowledge_timestamp(key)` / `knowledge_age(key)`: when a Knowledge value was written (local clock) and how long ago, sync latency included.
  - Bind check, each tick before handing off: `mission.validation.find_capability_problems()` against the live `KnowledgeDatabase.types()`, the same check the editor runs against a graph's declarations.  Any problem halts the mission (blocked) without crashing.
  - `update()` = `_advance_mission()` then `_refresh_own_record()`, which re-publishes its own `PlatformRecord` status (from `status()`) only when it changed.
- **Frontseater** (`platform/frontseater.py`, a concrete base): the only bespoke part of each platform (planning/control, its list of capabilities).  Talks to Hardware only via `send_controls`/`read_state`, and reaches its Backseater via `frontseater.backseater`.  A subclass lists `CAPABILITIES` (Capability classes) and overrides only what it needs; `__init__(hardware, debug=False)`.
  - `capabilities()`: the `CapabilityRegistry` built from `CAPABILITIES`.
  - `set_active_capabilities(capability_requests)`: called only when the active node's `{name: {"capability", "inputs", "outputs"}}` dict changes (by identity).  The base diffs by name: a gone or changed (`!=`) request is stopped, a new or changed one gets a fresh `Capability` instance and is started, and an equal one keeps running.
  - `begin_update()` = `tick_capabilities()` then `begin_controls()`; `finish_update()` = `finish_controls()`.  The default pair sends `compute_controls()` (default: the Hardware's `idle_controls`) synchronously; the bicycle overrides the pair so MPC solves overlap across platforms.
  - `describe_status() -> {"overall", "capabilities"}` (display-only): `"idle"` or `"N capability request(s) active"`, plus each instance's `status()`.
  - `shutdown()`: stops every running capability; an override calls `super().shutdown()` first.
  - `default_mission_graph()`: the base gives an inert `"startup"` node.  `Backseater` uses it when given `mission_graph=None`.
  - `attach(world, window_root=None)`: no-op, for setup that needs `World` or the Tk root.
- **Hardware** (`core/hardware.py` ABC): MCU equivalent; owns a `State` and its own dynamics.  One abstract method, `step_dynamics(dt, environment)`, which queries the passive environment.  `read_state()` goes through a `Sensor` (default `PerfectSensor`, the identity).  Every subclass declares `environment_type` (an `Environment` class, or `None` = any), with no base default.  `idle_controls` (default `{}`) seeds the pending controls.
- **State** (`core/state.py`): a dataclass holding only `t` (s, sim time).  Each environment subclasses it with what it tracks.
- **Platform** (`platform/platform.py`): composition root, not a runtime layer.  `PlatformSpec(platform_id, build_frontseater, mission_graph=None, privilege_level=1, clock=None, sync_interval=1.0)` → `Platform` builds the stack and its `KnowledgeDatabase`, exposes `.hardware`/`.frontseater`/`.backseater`/`.knowledge_database`, and owns `attach()`/`shutdown()`.  It holds no reference to `World`.



## World and Tick
`World(environment, platforms)` (`environments/world.py`) is platform-count-agnostic; `world.platforms` maps platform_id → `Platform`.  `__init__` raises `TypeError` for a platform whose `hardware.environment_type` the environment doesn't satisfy, or whose `hardware.state` isn't the environment's `state_type`.  Each `step()`:
1. Per platform: `backseater.update()` → `frontseater.begin_update()` (all platforms) → `frontseater.finish_update()`.  Each call is wrapped individually; a platform that faults is skipped for the rest of the tick.
2. Per platform: `hardware.step_dynamics(dt, environment)`, isolated, and run even for a faulted platform (a vehicle keeps coasting).
3. Mesh sync: every backseater runs `sync_with_stale_peers()` against every other backseater (full connectivity assumed).



## Databases
All three belong to the Backseater, are stamped by its `Clock`, and carry `origin_platform_id` per entry (the platform that held the entry at its latest locally converted timestamp, transitively).  Every check happens write-side only, once, at the originating platform; there is no re-verification on receipt.
- **Knowledge** (`KnowledgeDatabase`, `backseater.knowledge_database`): arbitrary keys, each type-locked.  Use `declare(key, entry_type, value, timestamp=None, origin_platform_id=None)` before `get`/`set`; `set` raises on an undeclared key or a wrong type.  `declare()` works at any time.  `set_or_declare()` is the rare bypass mesh sync uses.  Also `timestamp_of`, `origin_of`, and `all()`.  Values may be plain types or `KnowledgeEntry` subclasses (`describe()` required).
  - Keys are namespaced `namespace/name` (`split_key()`/`join_key()` in `knowledge.py`, split at the last `/`).  A namespace equal to a platform id marks that platform's own fact, which another platform's mission adoption never resets (see Mission change).
  - Types live one per file in `database/knowledge_types/` (built-ins `location.py` `Location(x, y)`, `pose.py` `Pose(x, y, theta)`, and `trajectory.py` `Trajectory(waypoints)`; the base and registry are in `base.py`).  The package imports every module in it.
  - `Trajectory`'s one `str` field is a JSON list of `[x, y]` pairs (m, world frame; `""` is none), parsed into `.points` (a bad one raises `ValueError`).  Plain text, so it needs nothing new in the editors, save/load, sync, or the LLM.
  - Each concrete subclass registers itself by class name in `KNOWLEDGE_TYPES_BY_NAME` (seeded with the scalars) and its reverse `KNOWLEDGE_TYPE_NAMES`; a taken name raises.
- **Mission** (`MissionDatabase`): platform_id → `mission_graph` dict.  Each Backseater self-writes its boot mission at construction, so peers can read it.  Every write goes through `Backseater.write_mission(mission_graph, writer_platform_id, timestamp=None, target_platform_id=None)` (None = this platform), which applies:
  - a privilege check (skipped when the writer is the target);
  - a type check;
  - `mission.validation.verify_mission_structure()`: every edge-condition key and binding key must be declared in the graph's `"knowledge"` section, otherwise `MissionStructuralError(ValueError)`;
  - `mission.validation.find_binding_problems()`: every capability request must be bindable by the target (capability exists, no missing/unknown fields, exact key types), against its own registry or, for a peer, its gossiped `PlatformRecord.capabilities` (refused if unknown).

  Edge reachability is not checked.
- **Platform** (`PlatformDatabase`): platform_id → `PlatformRecord(privilege_level, status, capabilities)`, gossiped so observers see a peer's health and abilities without local access.  `capabilities` is seeded at construction; `status` is `PlatformStatus(status, message, active_node_id, blocked, capability_statuses)`, re-published by `update()` on change.  `publish("platform", ...)` is self-write-only and may not change the platform's own `privilege_level` (only a strictly higher-privilege platform may; not implemented).



## Privilege, Mission Change, Sync
- **Privilege**: integer, 0 = highest (reserved), default 1, set by the harness.  A platform may write another's Mission entry only if its level is strictly lower (higher privilege).  Both levels are read from the writing Backseater's own `PlatformDatabase`, and an unknown writer or target gets `PermissionError`.  Runtime reassignment is not implemented.
- **Mesh push**: `publish("mission", target_id, graph)` writes the target's entry into the writer's own Mission database, with every check done there; sync delivers it, and the target's mission-change detection adopts it.  The web UI pushes this way.  The Tk editor still calls the target's `write_mission()` directly (a sim-only shortcut).
- **Mission change** (`_detect_mission_change()`, top of `update()`): when this platform's own Mission entry is a new object, it:
  1. stops the old capability requests;
  2. resets the new graph's knowledge keys to their declared defaults, except a key in another known platform's namespace (`split_key()`, e.g. `ugv1/pose` in ugv2's mission).  That key is the peer's own fact: a live value is kept, and a missing one gets the default stamped `PEER_PLACEHOLDER_TIMESTAMP` (0.0), so the peer's real value wins every sync;
  3. swaps the graph and the parsed conditions, and clears blocked;
  4. activates the new start node in the same tick.

  This works for mesh-synced missions too.  Because of step 2, a value staged live before a push is overwritten unless it is in another platform's namespace; see the roadmap's "Values a Mission Can't Carry Yet".
- **Mesh sync** (`Backseater.sync_with(peer)`): reconciles Knowledge, Mission, and Platform in both directions, last-write-wins by locally converted timestamp.  Pulled timestamps are converted (`Clock.to_local()`), never re-stamped.  Received entries bypass the write gates.
  - Symmetric and idempotent, so either side may initiate.
  - `sync_with_stale_peers(peers)` only syncs peers older than `sync_interval`.
  - A per-pair checksum skips unchanged pairs.
- **Clock** (`core/clock.py`): wall time plus the platform's own offset, plus a per-peer offset table filled by each sync handshake.  There is no shared clock.



## Missions (`mission/`)
- **Shape** (`graph.py`, the single readable definition): `{"knowledge": {key: {"type", "value"}}, "nodes": {id: {"capabilities": {name: {"capability", "inputs", "outputs"}}}}, "edges": {id: [{"condition": [tokens], "to": id}]}, "start": id}`, plus an optional `"name"` (a label the Backseater and validation ignore).  Editor-only data (node layout, key flags) never goes in the mission graph; see the web editor's `EditorDocument`.  TypedDicts `MissionGraph`/`Node`/`CapabilityRequest`/`Edge`/`KnowledgeDeclaration` document it and type-hint public signatures; graphs stay plain dicts.  One node is active at a time; its capability requests run concurrently.
- `"inputs"`/`"outputs"` map a capability's field names to Knowledge keys, never literals.  They are the initial binding; a running capability may `query()`/`publish()` anything.
- **Conditions** (`condition.py`): pre-tokenized boolean expressions over Knowledge keys (e.g. `["(", "ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9, ")", "or", "ugv1/target_found", "is", "not", None]`).  `parse_condition()` (recursive descent, no `eval`) builds a tree of `Comparison`/`IsNone`/`And`/`Or`/`Not`, each with `evaluate(knowledge)` and `keys()`.  Precedence is `not` > `and` > `or`.  Capability status never drives transitions; capabilities write Knowledge.
- **Validation** (`validation.py`): `verify_mission_structure()` (every referenced key declared), `find_capability_problems(request, known_types, registry)` / `find_binding_problems(graph, registry)`, and `find_condition_problems(condition, known_types)` (a parse error, undeclared keys, or a literal whose type doesn't match the key's, e.g. the string `"true"` against a bool key).  `known_types` is key → type: `declared_types(graph)` for the editor, assistant, and push; `KnowledgeDatabase.types()` for the Backseater's bind check.  Edge reachability is not checked.
- **Serialization** (`serialization.py`): JSON save/load through the self-populating type-name registry (`KNOWLEDGE_TYPES_BY_NAME`, re-exported from `mtofr.database`).
- **Capabilities** (`core/capability.py`):
  - `ParamSpec(name, type, description)` describes fields and drives the binding checks.  Its `describe()` includes a `KnowledgeEntry` type's own `describe()`, so a human or LLM can read what a field means.
  - `Capability` is one class per capability.  Class attributes `ipl_type`, `description`, `inputs`, `outputs` declare it (`describe()` is a classmethod).  One instance per running request, `(frontseater, name, request)`, runs it through `start()`/`tick()`/`stop()`/`status()` (all optional), with `read(field)` (live query of the bound key), `written_at(field)`/`age(field)` (the bound input's write time and age), and `write(field, value)` (publish if bound, else no-op); all raise `KeyError` for an undeclared field.
  - `CapabilityRegistry` holds the classes (`.get`, `.all`, `.describe`).  A capability request's `"capability"` equals an `ipl_type`.
  - Shared capabilities: `Stopwatch` (`platform/common_capabilities.py`), `SensePose` (`environments/ground_plane/capabilities.py`).



## Scenarios (`scenarios/`)
- One file per scenario (`split.py`, `wait.py`, `village.py`, `village_default.py`), each holding its graphs (named `mission_<scenario>_<platform_id>`) and `SCENARIO = ScenarioConfig(...)`.
- `ScenarioConfig(build_environment, build_viewer, platforms: list[PlatformSpec])` (`base.py`): builders, not instances, so importing scenarios loads no map; duplicate ids raise.  A spec without a graph boots its Frontseater's default.
- `SCENARIOS` maps each file name (every module but `base`) to its `SCENARIO`; `main.py`'s `ACTIVE_SCENARIO` is that name (e.g. `"village_default"`).



## Environments, Maps, Platform Types
- Each environment lives in `environments/<environment_name>/`: `env.py` (its `Environment`, which declares `state_type`), `state.py` (that `State` subclass), the Hardware base its vehicles subclass (`hardware.py`), `sensors/`, `maps/` if it has any, and its viewer (`viz/`).  Each platform type lives in `environments/<environment_name>/platforms/<type>/` and exports a `PlatformSpec` factory.  `Hardware.environment_type = None` (any environment) is still supported by `World`, but no platform uses it.
- **Ground plane** (`environments/ground_plane/`):
  - `GroundPlaneState(State)`: x, y, theta, vx, vy, vtheta (m, rad, world frame), plus `pose2d()`/`vel2d()`.
  - `GroundPlaneEnv(ground_map=None)` (`state_type = GroundPlaneState`) is passive and answers only `speed_multiplier_at(x, y)` and `is_blocked(x, y)`.  With no map it is unbounded and has no effect.
  - `GroundPlaneHardware` (`environment_type = GroundPlaneEnv`, abstract pure `calculate_dynamics(state, controls, dt, max_speed_multiplier=1.0)`): its default `step_dynamics` scales max speed by the multiplier at the true position, and rejects a step into a blocked cell (velocity zeroed).
  - `sensors/`: `GroundMapSensor.read(environment) -> GroundMap | None`, the perfect map sensor (it reports `environment.ground_map`).  It isn't a `core.Sensor`, which maps State to State.
- **Bicycle UGV** (`environments/ground_plane/platforms/bicycle_ugv/`): `bicycle_ugv(platform_id, start_x, start_y, mission_graph=None, privilege_level=1)`.
  - `BicycleHardware` is a kinematic bicycle (`dynamics.bicycle_step()`, shared with the MPC).
  - `BicycleFrontseater` is the reference Frontseater, `CAPABILITIES = (MoveTo, FollowTrajectory, Follow, Avoid, Stopwatch, SensePose)`:
    - `move_to` (`bicycle_ugv/capabilities.py`; `target`, `tolerance` → `arrived`; re-reads each tick and sets `navigation_target`, which the MPC chases);
    - `follow_trajectory` (`bicycle_ugv/capabilities.py`; `trajectory`, `tolerance`, `loop` → `arrived`): sets `navigation_target` to each waypoint in turn, advancing within `tolerance`.  After the last one it holds there with `arrived` true, or with `loop` starts over (never arrived).  A changed trajectory restarts at its first waypoint;
    - `follow` (`bicycle_ugv/capabilities.py`; `leader_pose`, `following_distance` → `distance`; never completes): convoy following after Cometto et al.  Each tick it:
      - dead-reckons the synced leader pose forward by its `age()`, at a speed and yaw rate estimated across successive samples (`extrapolate_pose()`);
      - sets `navigation_target` to the offhooked `Pose` (`offhook_target()`: back d/2 along the leader's heading, then d/2 along its own; the heading is its own);
      - idles while that point is behind it ("waiting"), or while the pose is older than `STALE_POSE_TIMEOUT` ("leader pose stale");
    - `avoid` (`bicycle_ugv/capabilities.py`; `point`, `radius` → `registered`; `add_avoid_region()` at start);
    - `stopwatch` (→ `elapsed_time` in sim seconds since start; never completes);
    - `sense_pose` (→ `pose`, the sensed `Pose` from `read_state()`, every tick; never completes).
  - Its default mission loiters on `stopwatch` and runs `sense_pose` bound to `<platform_id>/pose`, so pose gossips by default.  A pushed mission without `sense_pose` stops that.
  - MPC (`mpc.solve_mpc`, SLSQP, `MPC_MAX_ITERATIONS` 20, warm-started) runs in one persistent worker process per platform.  The MPC knows nothing about terrain.  A `Location` target is reached (bearing, effort, and distance cost); a `Pose` target is tracked with the paper's `TRACKING_*` weights, W_s = diag(1, 1, 0.1) and W_a = diag(0.2, 0.7).  Avoid-regions apply to both.
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
- `MissionGraphViewer` (`viz/mission_graph_view.py`, which also owns `GRAPH_PLOT_BACKGROUND` for every graph view):
  - deterministic force-directed `compute_graph_layout(graph, pinned_positions=None)`.  Pinned nodes stay put and only the rest are placed.  It is cached by `(id(graph), pins)` with a strong reference, bounded by `LAYOUT_CACHE_LIMIT`;
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



## Interface Platform and Mission Editors
- `interface(platform_id, initial_state, ..., build_panels=default_panels)` (`environments/ground_plane/platforms/interface/`, privilege 0): `MissionEditorFrontseater` + `ConsoleHardware`.
  - `ConsoleHardware` (`environment_type = GroundPlaneEnv`) is a fixed ground station at `initial_state` (a `GroundPlaneState`) that ignores controls.  Its `step_dynamics` advances `t` and refreshes its `GroundMapSensor` reading, which `read_map()` returns (None before the first step).
  - Two capabilities (`interface/capabilities.py`): `ShowInterface` opens or closes the Tk editor window, and `ServeWebInterface` starts or stops the web UI (a start failure shows in its status) and, each tick, runs the `WebHost`'s tick.  The default graph runs only `serve_web_interface`.
  - Editing itself is not a capability.
  - `attach()` installs the Tk window factory (`_NullWindow` when headless).  The web UI needs neither `World` nor Tk.
- **Web UI** (`interface/web/`), the hardware-portable one: it reads and writes only through the interface's own Backseater.
  - `WebInterfaceServer` (stdlib `ThreadingHTTPServer`, `WEB_HOST`/`WEB_PORT` in `web/config.py`, default `127.0.0.1:8765`) serves a vanilla-JS page and a JSON API in front of one `WebHost`.  A start failure (port taken) shows in `describe_status()`.
  - Threading: `WebHost.on_tick(backseater, ground_map)` runs on the sim thread from `ServeWebInterface.tick()`, which passes `hardware.read_map()`.  It runs every queued write (outcomes go to the console of the window that queued it), then captures an `InterfaceView` (frozen copies of all three databases, plus the sensed `ground_map`).  Server threads only read the latest view and queue writes, so while the sim is paused, reads hold still and writes wait.
  - Per-window sessions: the page keeps an id in `sessionStorage` and sends it as `X-Session-Id` (400 if missing or malformed).  `WebHost(own_platform_id, build_panels)` builds fresh panels for each session, so each window has its own Target, draft, undo history, and console over the one shared view.  A session survives a reload, expires after `SESSION_IDLE_TIMEOUT`, and is capped at `MAX_SESSIONS`.
  - Panels (`web/panel.py`): a `WebPanel` has `name`, `title`, `script_path` (its JS half, which calls `mtofr.registerPanel(name, mount)`), `state(context)`, and `commands()`.  `PanelContext(view, target_platform_id, submit, log, editor_store)`.  `api.command()` resolves after the resulting state is applied.
    - Optional `asset(asset_name, view) -> (bytes, content type) | None`, served at `GET /panels/<name>/assets/<file>`.  It is session-free (an `<img>` can't send the header), so the server calls it on the `WebHost`'s catalog panel.
    - A static registry: `default_panels()` gives Graph, Live Control, then World Viewer.  The table Editor tab is off for now (a NOTE in `panels/__init__.py`), but its `EditorPanel` still holds the window's draft.
    - A custom panel is a `WebPanel` subclass plus its script.
  - **Enter** (page-wide, `app.js`): in a field it blurs the field, which commits it.  With nothing focused, it presses the `[data-primary]` button of the open dialog, or of the last-used `[data-enter-scope]` container.  The header shows the time since the last sync with the Target.
  - **Live Control**: every Knowledge key the interface holds (the whole mesh), with origin, write age, and the time since the interface last synced with the origin.  Edits are published through the interface's Backseater, cast by `assistant_tools.as_knowledge_value()`.  Pending rows are italic:
    - a value queued until the next tick;
    - a key some known mission declares that hasn't arrived yet.
  - **The draft** (`EditorPanel`): one `DraftHistory` of `EditorDocument`s per window (`mission_editor/editor_document.py`).
    - **The document** is the mission graph plus editor-only data: the node `layout`, `unset_keys` and `following_keys`.  Only the graph is ever pushed.
    - **Edits** go through `DraftToolbox.run()` with `require_bindable=False`: incomplete capability requests are allowed while drafting, and are reported instead.
    - **`edit_batch`** runs several steps as one atomic undo step.  It also takes the editor-only steps `move_nodes`, `move_edge`, `declare_key`, `set_key_flags`, `set_mission_name` and `retarget`, none of which are assistant tools.
    - **`state`** carries:
      - `problems`: `requests` (node → request), `edges`, `keys` (unset) and `graph`;
      - `edge_rows`: each condition as builder rows, from `encoding.condition_rows()`, or null;
      - `target`, `name` and `draft_namespace`.
    - **Validate and Push** refuse an unbindable request, a mistyped condition, an unset key, or a missing start node.
    - **Unset keys:** a key made by "+ New key…" has no value until the operator sets one, so a default like Location(0, 0) can never pass for real.
    - **Namespaces:** a key whose namespace was left at the default (the Target) follows the Target, but only through the explicit "Retarget keys" button; a Target change alone renames nothing.
    - **Load, save and the store:**
      - Load Live comes from the gossiped Mission entry.
      - Files carry an `"editor"` section, which plain loaders ignore.
      - Push records the editor data in `WebHost.editor_store` (mission name → sidecar, in memory, shared by all windows), and Load Live of that name restores it.
    - The toolbar (mission name, Retarget) and shared forms, including the condition builder, are in `static/draft_tools.js`.
  - **Graph** (the first tab, opening in Live mode): `[Knowledge panel | canvas | inspector]`, the side panels collapsing by their arrows.  `GraphPanel` delegates every command to its `EditorPanel`.  `draft_layout` is `compute_graph_layout(graph, document.layout)`.
    - **Knowledge panel:** the draft's keys, showing the dimmed namespace, then name, type and value.
      - Unset keys are italic with ⚠, and keys bound by the selected node are highlighted.
      - Hover shows ✎/✕, and double-click edits inline (Namespace, Name, Type, value; Save is primary).
      - In Live mode it shows the live mission's keys with their mesh values.
    - **Inspector and popover** (the popover opens on double-click or the node's pencil): capability requests are edited inline (name, capability, one binding select per field).
      - A binding select offers the declared keys (matching type first) and "+ New key…", which declares an unset `ns/field` and binds it in one step.
      - The edge editor uses the condition builder: rows of `[not] key operator value`, with operators chosen by the key's type and typed literals, under all/any. "Advanced" switches to raw tokens.
    - **Canvas:**
      - ⚠ on nodes and edges with problems.
      - Priority badges (1st, 2nd, …) only where a node has two or more outgoing edges.
      - Halos under every edge, so crossings show gaps.
      - A selected edge marks its origin and recipient nodes in different colors, and a drawn edge's drop-target node lights up.
    - **Gestures:** drag a node's port to draw an edge (onto blank space adds a node); drag a selected edge's end handle to re-route it; double-click blank space to add a node; box-select and group-move; right-click menu; Delete, Ctrl+A, F, Escape, Ctrl+Z/Y.
    - **Live mode** shows the Target's gossiped mission (laid out from the store when its name is known), `PlatformStatus` and last-sync age, read-only.
  - **World Viewer** (`WorldViewerPanel`, `static/panels/world_viewer.js`): the view's `ground_map` drawn in world coordinates (SVG, +y up), with a marker and heading for every `Pose` in Knowledge (each platform's `sense_pose` output).
    - **Map:** the layers (`MAP_LAYER_ASSETS`: cosmetic, plus toggleable traversability and regions overlays) are PNG assets, encoded once per map.  The state carries the map's extent and a version, so the browser refetches only when the map changes.  It has wheel zoom, drag pan, and Fit.
    - **Trajectory drawer:** with Draw on, a click adds a waypoint, a drag moves one, and a right-click deletes one, with Undo point and Clear.  It produces `Trajectory` text (Copy) and redraws from pasted text (Load).  Browser-only: the panel has no commands, and the operator pastes the text into a value in Live Control or the Graph editor.
- **Tk editor**: `MissionEditorWindow` (`mission_editor/window.py`), a Toplevel on the dashboard's root.  A sim-only direct path: it reads `World` and writes peers' Backseaters itself.
  - It edits one draft at a time, loaded from a live platform (deep-copied), from a file (`mission/serialization.py`), or blank.
  - Every mutation goes through `_set_draft()`, using pure `graph_draft.py` helpers that return new dicts, recorded in a `DraftHistory` (`mission_editor/draft_history.py`, shared with the web Editor) for undo/redo (`UNDO_HISTORY_LIMIT`, Ctrl+Z/Y bound on the window).
  - Validate, then Push through the target's `write_mission()`.  The editor is just another writer.
  - Tabs:
    - **Live Control** (default): the target's Knowledge, edited live via `set()` and refreshed each second.
    - **Editor**: resizable panes of Nodes+Capabilities | Edges | Knowledge, with Add/Edit/Remove and double-click editing.
    - **Graph**: Draft/Live preview.
  - A Console logs every action, and warns when the push target differs from the draft's source.
  - Conditions are typed as raw token literals (`ast.literal_eval` + `parse_condition()`).
  - Knowledge value forms come from `constructor_fields()` introspection (`mission/serialization.py`).
  - Renaming a key cascades to its bindings and conditions.  A token counts as a key when the next token is a comparison operator or `"is"`.



## LLM Assistant
- Ollama runs `qwen3.5:4b` locally on the CPU (setup: `llm_setup.md`).  Settings are in `environments/ground_plane/platforms/interface/agent/config.py`: model, `NUM_CTX`, `THINK`, `TEMPERATURE`, `MAX_REPLY_TOKENS`, `MAX_NUDGES`, `MAX_ITERATIONS`, `KEEP_ALIVE`.
- `agent/agent.py`: the streaming tool-call loop.  The caller injects tools and `run_tool`; `should_stop` serves the Stop button; it chains tool calls and logs per-call timings.
- `mission_editor/assistant_window.py`: opened by the editor's "Assistant...".
  - A chat with its own target dropdown, shared with the editor.
  - An "Enable thinking" toggle (only `think=`; thinking is always displayed).
  - A live wait counter and progress bar.
  - Turns run on a worker thread, with events marshalled over a queue.  One user message is one undo step.
- `assistant_tools.py`: 14 tools, 1:1 with the `graph_draft.py` mutators.  `add_capability`/`edit_capability` refuse unbindable capability requests, with the fix in the error.
- `assistant_prompt.py`: the system prompt (hand-edited by the user) plus the per-turn message.  That message is SITUATION (target, WORLD frame/map/regions/terrain/position and live active node as information only, capabilities, draft) followed by MISSION (the request).
- `assistant_session.py`: history keeps only requests and final replies.  `_detect_stall` nudges a reply that has no real tool calls (calls typed as text, truncated, or announced but not done).
