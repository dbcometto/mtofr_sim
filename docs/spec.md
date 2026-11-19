# Specification

MTOFR_SIM simulates platform-agnostic mission-type orders for robots.  It is pure Python (numpy, scipy, matplotlib, pyyaml, Tkinter, and `ollama` for the local LLM), with no ROS, networking, or async libraries yet.

**Experiment plan**: compare human teleoperation (possibly a convoy system) to autonomy for logistics tasks, in sim and on hardware.  A human commander must accomplish pick-up/drop-off missions that arrive in a scripted order, and task performance is measured and analyzed.  The simulator carries the analysis; a hardware demo (F1Tenth-class) would reinforce it.

Design history is in `notes.md`; build order, open items, and known issues are in `roadmap.md`.



## Layout
- `main.py`: entry point (`.venv\Scripts\python.exe main.py`).  Config constants at the top (`DT`, `ENABLE_HEADLESS`, `DEBUG`, `ACTIVE_MISSION_SET`).  All setup is under `if __name__ == "__main__":` because Windows "spawn" re-imports the script in every MPC worker process.
- `src/mtofr/`: the package, an editable install.
  - `backseater/`: `Backseater`.
  - `database/`: `knowledge.py`, `knowledge_types.py`, `platform_keyed.py`, all re-exported from `mtofr.database`.
  - `capability/`: `ParamSpec`, `Capability`, `CapabilityRegistry`, binding checks.
  - `condition/`: the edge-condition parser.
  - `clock/`: `Clock`.
  - `maps/`: `GroundMap` plus one folder per map (`blank`, `simple_village`).
  - `viz/`: dashboard and viewers.
  - `world/`: `base.py` (`WorldState`, `PerfectSensor`, `Hardware`, `Frontseater`, `Environment` ABCs), `world.py` (`World`), `platform.py` (`Platform`, `PlatformSpec`), plus one folder per environment.
  - `missions.py`: example mission graphs and mission sets.
- `tests/`: stdlib `unittest`, flat (`.venv\Scripts\python.exe -m unittest discover -s tests`).
- `scripts/mpc_profile.py`: tick-time and MPC-iteration profiler (not part of the suite).
- `mission_library/`: saved mission-graph JSON files (mission editor Save/Load).
- `llm/ollama/`: start/stop scripts for the local LLM service (see `llm_setup.md`).
- `docs/`: these documents.



## Platform Layers
Each platform is a Hardware → Frontseater → Backseater stack, the layers calling each other directly as separate processes would on a real robot.
- **Backseater** (`backseater/backseater.py`): platform-agnostic.  Holds the mission graph and the active node, evaluates edges, and hands the active node's primitives to its Frontseater.  Never touches physical state.  It owns the platform's identity (`platform_id` cascades to Frontseater and then Hardware), its `Clock`, its privilege level, and its three databases.
  - `capabilities()`: passthrough to the Frontseater's registry; the only way to learn what a platform can do.
  - `status()`: read-only snapshot of the active node, blocked flag, and per-primitive capability/status/inputs.  Status text comes fresh from `Frontseater.describe_status()`.
  - `query(database_name, key)` / `publish(database_name, key, value, timestamp=None)` across `"knowledge"`/`"mission"`/`"platform"`, plus `declare_knowledge_key()`.  A `"mission"` publish always goes through `write_mission()`.
  - `_check_binding_types()`: at bind time, each bound key must be declared with the field's exact `ParamSpec` type, otherwise the mission halts (blocked) without crashing.
- **Frontseater** (`world/base.py` ABC): the only bespoke part of each platform (planning/control, capability implementations).  Talks to Hardware only via `send_controls`/`read_state`, and reaches its Backseater via `frontseater.backseater`.
  - `capabilities()`: builds its own `CapabilityRegistry`.
  - `set_active_primitives(primitives)`: called only when the active node's `{name: {"capability", "inputs", "outputs"}}` dict changes (by identity).  The Frontseater diffs it (start new, stop gone, leave unchanged) and decides how "running" works.
  - `describe_status() -> {"overall", "primitives"}` (abstract, display-only), `compute_controls()`, `begin_update()`/`finish_update()` (lets MPC solves overlap across platforms), `shutdown()` (required).
  - `default_mission_graph()`: concrete base gives an inert `"startup"` node.  `Backseater` uses it when given `mission_graph=None`.
  - `attach(world, window_root=None)`: concrete no-op, for setup that needs `World` or the Tk root.
- **Hardware** (`world/base.py` ABC): MCU equivalent; owns `WorldState` and its own dynamics.  One abstract method, `step_dynamics(dt, environment)`, which queries the passive environment.  `read_state()` goes through a `PerfectSensor` stub.  Every subclass declares `environment_type` (an `Environment` class, or `None` = any), with no base default.
- **Platform** (`world/platform.py`): composition root, not a runtime layer.  `PlatformSpec(platform_id, build_frontseater, mission_graph=None, privilege_level=1, clock=None, sync_interval=1.0)` → `Platform` builds the stack and its `KnowledgeDatabase`, exposes `.hardware`/`.frontseater`/`.backseater`/`.knowledge_database`, and owns `attach()`/`shutdown()`.  It holds no reference to `World`.



## World and Tick
`World(environment, platforms)` (`world/world.py`) is platform-count-agnostic; `world.platforms` maps platform_id → `Platform`.  `__init__` raises `TypeError` for a platform whose `hardware.environment_type` the environment doesn't satisfy.  Each `step()`:
1. Per platform: `backseater.update()` → `frontseater.begin_update()` (all platforms) → `frontseater.finish_update()`.  Each call is wrapped individually; a platform that faults is skipped for the rest of the tick.
2. Per platform: `hardware.step_dynamics(dt, environment)`, isolated, and run even for a faulted platform (a vehicle keeps coasting).
3. Mesh sync: every backseater runs `sync_with_stale_peers()` against every other backseater (full connectivity assumed).



## Databases
All three belong to the Backseater, are stamped by its `Clock`, and carry `origin_platform_id` per entry (the platform that held the entry at its latest locally converted timestamp, transitively).  Every check happens write-side only, once, at the originating platform; there is no re-verification on receipt.
- **Knowledge** (`KnowledgeDatabase`, `backseater.knowledge_database`): arbitrary keys, each type-locked.  Use `declare(key, type, value, timestamp=None, origin_platform_id=None)` before `get`/`set`; `set` raises on an undeclared key or a wrong type.  `declare()` works at any time.  `set_or_declare()` is the rare bypass mesh sync uses.  Also `timestamp_of`, `origin_of`, and `all()`.  Values may be plain types or `KnowledgeEntry` subclasses (`describe()` required; `Location(x, y)` is the only built-in, in `knowledge_types.py`).
- **Mission** (`MissionDatabase`): platform_id → `mission_graph` dict.  Writes from another platform go through `Backseater.write_mission(mission_graph, writer_platform_id, timestamp=None)`, which applies:
  - a privilege check (skipped for a self-write);
  - a type check;
  - `verify_mission_structure()`: every edge-condition key and primitive binding key must be declared in the graph's `"knowledge"` section, otherwise `MissionStructuralError(ValueError)`;
  - `capability.find_binding_problems()`: every primitive must be bindable by this platform (capability exists, no missing/unknown fields, exact key types).

  Edge reachability is not checked.
- **Platform** (`PlatformDatabase`): platform_id → `PlatformRecord(privilege_level, status: PlatformStatus(status, message), capabilities)`.  Gossiped per platform, and seeded at construction.  `status` and `capabilities` are meant to be self-write-only (not enforced yet).  `privilege_level` may only be changed by a strictly higher-privilege platform.



## Privilege, Mission Change, Sync
- **Privilege**: integer, 0 = highest (reserved), default 1, set by the harness.  A platform may write another's Mission entry only if its level is strictly lower (higher privilege).  Both levels are read from the target's own `PlatformDatabase`, and an unknown writer gets `PermissionError`.  Runtime reassignment is not implemented.
- **Mission change** (`_detect_mission_change()`, top of `update()`): when this platform's own Mission entry is a new object, it:
  1. stops the old primitives;
  2. resets the new graph's knowledge keys to their declared defaults;
  3. swaps the graph and the parsed conditions, and clears blocked;
  4. activates the new start node in the same tick.

  This works for mesh-synced missions too.
- **Mesh sync** (`Backseater.sync_with(peer)`): reconciles Knowledge, Mission, and Platform in both directions, last-write-wins by locally converted timestamp.  Pulled timestamps are converted (`Clock.to_local()`), never re-stamped.  Received entries bypass the write gates.
  - Symmetric and idempotent, so either side may initiate.
  - `sync_with_stale_peers(peers)` only syncs peers older than `sync_interval`.
  - A per-pair checksum skips unchanged pairs.
- **Clock** (`clock/clock.py`): wall time plus the platform's own offset, plus a per-peer offset table filled by each sync handshake.  There is no shared clock.



## Mission Graphs
- Shape: `{"knowledge": {key: {"type", "value"}}, "nodes": {id: {"primitives": {name: {"capability", "inputs", "outputs"}}}}, "edges": {id: [{"condition": [tokens], "to": id}]}, "start": id}`.  One node is active at a time; its primitives run concurrently.
- `"inputs"`/`"outputs"` map a capability's field names to Knowledge keys, never literals.  They are the initial binding; a running capability may `query()`/`publish()` anything.
- **Conditions** (`condition/condition.py`): pre-tokenized boolean expressions over Knowledge keys (e.g. `["(", "ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9, ")", "or", "ugv1/target_found", "is", "not", None]`).  `parse_condition()` (recursive descent, no `eval`) builds a tree of `Comparison`/`IsNone`/`And`/`Or`/`Not`, each with `evaluate(knowledge)` and `keys()`.  Precedence is `not` > `and` > `or`.  Primitive status never drives transitions; capabilities write Knowledge.
- **Capabilities** (`capability/capability.py`): `ParamSpec(name, type, description)` describes fields and drives the binding checks; it never resolves values.  Its `describe()` includes a `KnowledgeEntry` type's own `describe()`, so a human or LLM can read what a field means.  `Capability(ipl_type, description, inputs, outputs)` and `CapabilityRegistry` (`.get`, `.all`, `.describe`).  A primitive's `"capability"` equals an `ipl_type`.
- **Mission sets** (`missions.py`): graphs are named `mission_<set>_<platform_id>`.  `MissionSet` (`SPLIT`, `WAIT`, `VILLAGE`, `VILLAGE_DEFAULT`) maps through `MISSION_SETS` to a `MissionSetConfig(map_name, platforms: list[PlatformSpec])`, and duplicate ids raise.  A spec without a graph boots its Frontseater's default.



## Environments, Maps, Platform Types
- Each environment lives in `world/<environment_name>/`: `env.py`, the Hardware base its vehicles subclass (`hardware.py`), and its viewer (`viz/`).  Each platform type lives in `world/<environment_name>/platforms/<type>/`, or in `world/anywhere/platforms/<type>/` if it needs no environment (built on `StationaryHardware`).  Each exports a `PlatformSpec` factory.
- **Ground plane** (`world/ground_plane/`):
  - `GroundPlaneEnv(ground_map=None)` is passive and answers only `speed_multiplier_at(x, y)` and `is_blocked(x, y)`.  With no map it is unbounded and has no effect.
  - `GroundPlaneHardware` (`environment_type = GroundPlaneEnv`, abstract pure `calculate_dynamics(state, controls, dt, max_speed_multiplier=1.0)`): its default `step_dynamics` scales max speed by the multiplier at the true position, and rejects a step into a blocked cell (velocity zeroed).
- **Bicycle UGV** (`world/ground_plane/platforms/bicycle_ugv/`): `bicycle_ugv(platform_id, start_x, start_y, mission_graph=None, privilege_level=1)`.
  - `BicycleHardware` is a kinematic bicycle (`dynamics.bicycle_step()`, shared with the MPC).
  - `BicycleFrontseater` is the reference Frontseater, a plain if/elif over its capabilities:
    - `move_to` (`target`, `tolerance` → `arrived`; re-queries each tick);
    - `avoid` (`point`, `radius` → `registered`);
    - `stopwatch` (→ `elapsed_time` in sim seconds since start; never completes).
  - Its default mission loiters on `stopwatch`.
  - MPC (`mpc.solve_mpc`, SLSQP, `maxiter` 20, warm-started) runs in one persistent worker process per platform.  The MPC knows nothing about terrain.
- **Stationary** (`world/anywhere/hardware.py`): `StationaryHardware` (`environment_type = None`) never moves.
- **Maps** (`maps/ground_map.py`): `GroundMap.load(folder)` reads `<name>.yaml` plus `_cosmetic`/`_traversability`/`_regions` PNGs.
  - World (0, 0) is the image center, +y up, so sampling flips rows.
  - Traversability maps a hex color to `TraversabilityType(name, blocking, speed_multiplier)`.  A pixel snaps to the nearest declared color; an unmatched in-bounds pixel is passable, and off-map is blocked.
  - `RegionType(name, center_x, center_y)` is display-only.



## Visualization
- `EnvironmentViewer` (`viz/base.py`): ABC whose `configure_ax`/`render` draw onto a caller-owned Axes.  `render()` takes `show_traversability`/`show_regions`; the class has a `background_color`.
- `PlanePlotter` (`world/ground_plane/viz/`):
  - draws platforms as dots with a fixed on-screen heading marker;
  - draws the map's cosmetic image with toggleable overlays and a combined legend;
  - uses a gray off-map background.
- `MissionGraphViewer` (`viz/mission_graph_view.py`):
  - deterministic force-directed `compute_graph_layout()`, cached by `id(graph)` with a strong reference;
  - arrowheads at edge midpoints, and opposing edges curved apart by a quadratic bezier;
  - hover hit-testing in display pixels, with tooltips titled `Node:`/`Edge:`.
- `PlatformOverviewViewer`: one row per platform (`platform_id: "active_node"`); hover shows primitives, and a click selects the platform.
- `MissionDashboard` (`viz/dashboard.py`, Tkinter):
  - a platform dropdown that defaults to "Mission Overview";
  - the environment view with overlay checkboxes, scroll-zoom, and drag-pan;
  - the "Mission Overview" panel (platform list, or one platform's graph with an edge-label toggle and a back button);
  - a capability/knowledge panel, defaulting to Knowledge (Name/Type/Value), which stays empty in overview mode;
  - the pause state (`is_paused()`).

  `main.py` drives it cooperatively rather than with `mainloop()`.



## Interface Platform and Mission Editor
- `interface(...)` (`world/anywhere/platforms/interface/`, privilege 0): `MissionEditorFrontseater` + `ConsoleHardware` (a `StationaryHardware`, placed on the map).
  - Its one capability, `show_interface`, opens or closes the editor window.  Its default graph runs that capability unconditionally.
  - Editing itself is not a capability.
  - `attach()` installs the window factory (`_NullWindow` when headless).
- `MissionEditorWindow` (`mission_editor/window.py`): a Toplevel on the dashboard's root.
  - It edits one draft at a time, loaded from a live platform (deep-copied), from a file (`serialization.py`: JSON with a type-name registry), or blank.
  - Every mutation goes through `_set_draft()`, using pure `graph_draft.py` helpers that return new dicts.  This gives undo/redo (`UNDO_HISTORY_LIMIT`, Ctrl+Z/Y bound on the window).
  - Validate, then Push through `write_mission()`.  The editor is just another writer.
  - Tabs:
    - **Live Control** (default): the target's Knowledge, edited live via `set()` and refreshed each second.
    - **Editor**: resizable panes of Nodes+Primitives | Edges | Knowledge, with Add/Edit/Remove and double-click editing.
    - **Graph**: Draft/Live preview.
  - A Console logs every action, and warns when the push target differs from the draft's source.
  - Conditions are typed as raw token literals (`ast.literal_eval` + `parse_condition()`).
  - Knowledge value forms come from `constructor_fields()` introspection, so a new `KnowledgeEntry` type needs one registry line.
  - Renaming a key cascades to its bindings and conditions.  A token counts as a key when the next token is a comparison operator or `"is"`.



## LLM Assistant
- Ollama runs `qwen3.5:4b` locally on the CPU (setup: `llm_setup.md`).  Settings are in `world/anywhere/platforms/interface/agent/config.py`: model, `NUM_CTX`, `THINK`, `TEMPERATURE`, `MAX_REPLY_TOKENS`, `MAX_NUDGES`, `MAX_ITERATIONS`, `KEEP_ALIVE`.
- `agent/agent.py`: the streaming tool-call loop.  The caller injects tools and `run_tool`; `should_stop` serves the Stop button; it chains tool calls and logs per-call timings.
- `mission_editor/assistant_window.py`: opened by the editor's "Assistant...".
  - A chat with its own target dropdown, shared with the editor.
  - An "Enable thinking" toggle (only `think=`; thinking is always displayed).
  - A live wait counter and progress bar.
  - Turns run on a worker thread, with events marshalled over a queue.  One user message is one undo step.
- `assistant_tools.py`: 14 tools, 1:1 with the `graph_draft.py` mutators.  `add_primitive`/`edit_primitive` refuse unbindable primitives, with the fix in the error.
- `assistant_prompt.py`: the system prompt (hand-edited by the user) plus the per-turn message.  That message is SITUATION (target, WORLD frame/map/regions/terrain/position and live active node as information only, capabilities, draft) followed by MISSION (the request).
- `assistant_session.py`: history keeps only requests and final replies.  `_detect_stall` nudges a reply that has no real tool calls (calls typed as text, truncated, or announced but not done).
