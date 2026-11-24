# Notes

Paths are as they were when each note was written; notes 33, 36, 37, and 40 record the moves.

## 47 - 2026-11-24: Streamlined capabilities, platforms, and registration
- Acted on note 45's friction (user's scope: items 1-4 and 6; actuation arbitration and environment leaks stay open).
- `Capability` (`core/capability.py`) is now one class (user's naming): class attributes declare it, and `start()`/`tick()`/`stop()`/`status()` run it, one instance per running request.
  - The I/O is `read(field)`/`write(field, value)` (user's choice over attribute magic); an unbound output is a no-op.
  - `CapabilityRegistry` holds the classes, so validation, gossip, the web UI and the assistant needed no change.
- The `Frontseater` base owns the lifecycle: `CAPABILITIES`, the request diff, ticking before controls (`begin_update()` = `tick_capabilities()` + `begin_controls()`), the default `describe_status()`, and `shutdown()` (fixes the known issue).
  - **Behavior change:** a same-named request with different bindings is now restarted (an equal one still keeps running).
  - `Hardware.idle_controls` seeds pending controls, and is the base `compute_controls()`.
- Capabilities moved out of the Frontseaters, so they can be reused: `Stopwatch` (`platform/common_capabilities.py`), `SensePose` (`environments/ground_plane/capabilities.py`), `MoveTo`/`Avoid` (`bicycle_ugv/capabilities.py`), and `ShowInterface`/`ServeWebInterface` (`interface/capabilities.py`).
  - The web UI's tick is now `ServeWebInterface.tick()`.
- Registration: `knowledge_types` is a package with one file per type, and each `KnowledgeEntry` subclass self-registers (user request).  Scenarios are discovered by file name, so the `Scenario` enum is gone and `ACTIVE_SCENARIO` is a string.

## 46 - 2026-11-24: Web UI checkpoint; values a mission can't carry yet
- The web UI (notes 41-44) is working and is the primary interface.  What remains is its open items in `roadmap.md`, not new features.
- Design gap found, deferred to future work.  Example: a trajectory drawn in a drawer panel, followed by a `follow_trajectory` capability, can't be specified:
  - Adoption resets every declared key to its default (`_declare_knowledge_keys()`), so a value staged live before a push is overwritten.  The reset itself is right for flags like `arrived`.
  - Only the editor writes draft values; other panels can't contribute one.
  - `KnowledgeEntry` encoding covers flat scalar constructor fields only, so a waypoint list or an image has no form.  Sync checksums `repr()` every value, and the web state resends every value each poll, which doesn't scale to large values.
- Directions to weigh when it's picked up (none chosen yet):
  - a per-key "keep live value" adoption flag;
  - panels registered as typed value editors that write into the draft;
  - per-type JSON encode/decode with hashed checksums and on-demand fetch, or content-addressed blobs for constrained comms.

## 45 - 2026-11-24: Extension checklists
- Added `docs/checklists.md`: step-by-step checklists for a new capability, platform (Hardware + Frontseater), environment, and Knowledge type, as the code stands today.
- Each step marks its friction, and a closing summary groups the friction against the target (capabilities about as easy as ROS callbacks, timers, and pub/sub).  It is the input for build order step 9's streamlining, so it proposes no solutions.
- Found while writing: `shutdown()` is required by `Platform.shutdown()` but missing from the `Frontseater` ABC (now a known issue).

## 44 - 2026-11-24: Editor document, incomplete requests, condition builder, knowledge panel
- Reverted note 43's layout-in-graph (user review): mission graphs carry no editor-only data, only a new optional `"name"`.
  - Layout, unset flags and following flags live in `EditorDocument` (`mission_editor/editor_document.py`), undone with the draft, in a saved file's `"editor"` section, and in `WebHost.editor_store` (name → sidecar) so Load Live restores a pushed mission's layout.
  - `compute_graph_layout()` takes `pinned_positions` as an argument.
  - Accepted trade-off: the Tk dashboard and preview are auto-laid-out again.
- Incomplete capability requests are allowed while drafting (`DraftToolbox(require_bindable=False)` in the web editor; the assistant stays strict).  They show ⚠ on the node and the request, and Validate and Push still refuse them.
- Safety (user review):
  - "+ New key…" declares an unset placeholder that blocks Validate and Push until the operator sets a value, so a default Location(0, 0) can't send a vehicle to the origin.
  - Retargeting default-namespace keys is an explicit button, never a side effect of switching the Target (which is also used just to look).
  - Priority badges stay where there's a choice (two or more outgoing edges), since check order is behavior.
- `find_condition_problems()` flags literal/key type mismatches, which catches the JSON-editor trap of `"true"` being a string.  The graph editor's condition builder (key, operator by type, typed value; all/any rows; raw-token fallback) avoids the trap entirely.
- UI:
  - an always-visible Knowledge panel with inline editing and a Namespace field (default: the Target);
  - arrow handles collapse both side panels;
  - Enter blurs a field, or presses the primary button when nothing is focused;
  - crossing gaps come from halos;
  - origin and recipient highlights, and a drop-target highlight while drawing;
  - Live Control shows pending rows in italics and sync ages; the header shows the Target's sync age.
- The Graph tab is first and opens in Live mode, followed by Live Control.  The table Editor tab is turned off for now (user's call).
- Mission-declared Knowledge keys now record their declaring platform as origin (it was `None`).

## 43 - 2026-11-24: Graphical editor, per-window sessions
- The Graph tab became a full graphical editor of the window's draft (the same draft as the table Editor), drawn client-side in vanilla SVG.  The server-side matplotlib SVG (`web/render.py`) is gone.  Live mode shows the Target's mission read-only.
- Node positions live in the mission graph: an optional top-level `"layout": {node_id: [x, y]}` that the Backseater and validation ignore.  This gives undoable moves, layouts in saved and pushed missions, and the dashboard and Tk preview show the author's layout.  `compute_graph_layout()` pins stored nodes and places only the rest; its cache is now bounded (`LAYOUT_CACHE_LIMIT`).
- Gestures:
  - drag from a node's port to draw an edge (onto blank space: a new node plus the edge);
  - drag a selected edge's end handle to re-route it;
  - double-click blank space to add a node;
  - box-select and group-move;
  - right-click menu; Delete, Ctrl+A, F, Escape.
- Editing UI: a hideable docked inspector plus a popover (double-click, or the selected node's pencil), sharing one item editor.  An open editor is never rebuilt while it has the keyboard.
- `EditorPanel.edit_batch` runs steps on a scratch draft and commits them as one undo step, only if every step succeeds.  It also accepts the editor-only layout steps `move_nodes`/`move_edge`, which aren't assistant tools.  `GraphPanel` delegates every command to its `EditorPanel`.
- `graph_draft.edit_edge` now keeps an edge's priority when its source is unchanged (before, it re-appended the edge).  `move_edge` reorders; the table Editor gained Up/Down.
- Per-window sessions: the page keeps an id in `sessionStorage` and sends it as `X-Session-Id`.  `WebHost` builds fresh panels per session, so each window has its own Target, draft, undo, and console, over one shared view.  Sessions expire after `SESSION_IDLE_TIMEOUT` and are capped at `MAX_SESSIONS`.
- `static/draft_tools.js` holds the toolbar and sub-forms both editors share.  `api.command()` now resolves after the resulting state is applied, and an older poll reply can't overwrite it.

## 42 - 2026-11-24: Web UI capability (first cut)
- Goal: an operator UI that routes only through the interface platform's own Backseater (reads from its databases, pushes as mesh writes), so it carries over to hardware unchanged.  The Tk editor stays as-is, now documented as a sim-only direct path (it reads `World` and calls the target's `write_mission()`).
- `serve_web_interface` capability beside `show_interface`; the interface's default mission runs only the web UI.  The frontseater matches requests by capability type, not request name.  A server start failure (port taken) is reported in `describe_status()`, not raised.
- Stack: stdlib `ThreadingHTTPServer` and vanilla JS, with no new dependencies.  Host is configurable (`WEB_HOST`, default localhost).  Files go through browser upload/download.
- Threading: no World lock.  `WebHost.on_tick()` runs from the interface Frontseater's `begin_update()` (sim thread): it runs queued writes, then captures an `InterfaceView`.  Server threads only read the view and queue writes, so a paused sim freezes reads and holds writes, with no deadlock.
- Panels are whole UI modules (Python `WebPanel` with `state()`/`commands()`, plus a JS half calling `registerPanel`), from a static registry (`interface(..., build_panels=default_panels)`).  The built-in Live Control, Editor, and Graph tabs are themselves panels.  Panels see only the view and the write queue, never World.
- The Editor runs every edit through `DraftToolbox`, the assistant's command layer, so unbindable requests are refused at edit time and conditions are JSON tokens.  Undo/redo moved to a shared `DraftHistory` used by both editors.
- Graph renders server-side SVG (`MissionGraphViewer` on a standalone `Figure`); `GRAPH_PLOT_BACKGROUND` moved to `mission_graph_view.py` so the web side never imports the TkAgg dashboard.
- `serialization.py` gained dict-level `encode_mission_graph`/`decode_mission_graph`, and `assistant_tools.as_knowledge_value` became public (Live Control casts form text through it).

## 41 - 2026-11-24: Live PlatformRecord, mesh push, Pose
- `PlatformRecord` now does its intended job (the merged Capabilities and Status databases, note 21): `capabilities` is seeded at construction, and `PlatformStatus` grew `active_node_id`, `blocked`, and `capability_statuses` (`Backseater.status()`'s fields).  `update()` = `_advance_mission()` + `_refresh_own_record()`, which re-publishes only on change.
- Self-write-only is enforced: `publish("platform", ...)` refuses another platform's record and changes to its own privilege level.  Sync still bypasses (write-side-only rule).
- Boot missions are self-written into `mission_database`, so a peer can read what a platform runs before anyone pushes to it.
- Mesh push: `write_mission(..., target_platform_id=None)`, reached by `publish("mission", target, graph)`.  Privilege is compared from the writer's own `PlatformDatabase`, and bindings are checked against the target's gossiped capabilities (refused if unknown).  The graph lands in the writer's Mission database; sync delivers it and the target's mission-change detection adopts it.
- Pose: `Pose(x, y, theta)` Knowledge type, plus a `sense_pose` capability on the bicycle UGV publishing the sensed pose (`read_state()`) every tick.  The default mission binds it to `<platform_id>/pose`, which needed the Backseater to cascade `platform_id` before building the default graph.  A pushed mission without `sense_pose` stops that platform's pose gossip.

## 40 - 2026-11-19: Layered packages; primitive → capability request
- Layers, each importing only from those above it: `core/` (`State`, `Sensor`/`PerfectSensor`, `Hardware`, `Environment`, `Clock`, capabilities; platform-, environment-, and mission-agnostic) → `database/` → `mission/` → `platform/` (`Frontseater`, `Backseater`, `Platform`) → `viz/` → `environments/` (was `world/`; `World` plus one folder per environment) → `scenarios/`.
- Why `platform/` sits above `mission/`: with the Backseater in `core`, `core` needed `mission` and `mission` needed `core.capability`, a cycle.  The Frontseater moved with it since its contract is mission primitives.  `viz/` sits below `environments/` because every real import points environments → viz; `MissionDashboard` takes `World` duck-typed.
- `world/base.py` split up.  `WorldState` became `GroundPlaneState(State)` (`environments/ground_plane/state.py`); core `State` holds only `t`.
- Anywhere platforms are placed in the host environment's terms (the Gazebo static-model pattern): `StationaryHardware` keeps any `State` and advances only `t`, `Environment.state_type` is required (no default), and `World` rejects a mismatched state.  `interface()` takes an `initial_state`.  A shared geodetic frame (the GCS pattern) was the alternative, deferred until a multi-environment `World`.
- `mission/` collects the mission definition: `graph.py` (TypedDict shape, the one place to read what a mission is), `condition.py`, `validation.py` (structural check from `platform_keyed.py`, binding checks from `capability.py`), `serialization.py` (from the editor).  The Backseater's duplicate `_check_binding_types` is gone: it runs `find_capability_problems()` against `KnowledgeDatabase.types()`.
- Maps moved to `environments/ground_plane/maps/` (`load_map(name)`); `environments/ground_plane/sensors/` added as the home for ground-plane sensors.
- `missions.py` → `scenarios/`, one file per scenario.  `ScenarioConfig(build_environment, build_viewer, platforms)` replaced `map_name`, so `main.py` is environment-agnostic.  Renames: `MissionSet` → `Scenario`, `MISSION_SETS` → `SCENARIOS`, `ACTIVE_MISSION_SET` → `ACTIVE_SCENARIO`.
- Rename (user request): a node entry is a capability request.  Graph key `"primitives"` → `"capabilities"` (saved `mission_library` files too), `Primitive` → `CapabilityRequest`, `set_active_primitives` → `set_active_capabilities`, `find_primitive_problems` → `find_capability_problems`, assistant tools `add/edit/remove_capability` with `request_name`, status dicts' `"primitives"` → `"capabilities"`.  `SYSTEM_PROMPT` updated at the user's request: term swaps only, plus the worked example's `add_capability(..., request_name=...)` call.

## 39 - 2026-11-19: Code migrated to style.md
- Whole codebase (`src/`, `main.py`, `scripts/`, `tests/`) brought in line with `style.md`; no behavior change.  `style_migration.md` retired.
- Separators mapped by position: file level → major box (7 blank lines after), inside a class/function → semi-major (5), minor (3), substep (2).
- Every function has a docstring, `__init__` and every `test_*` method included (now stated in `style.md`).
- Each module's tunables sit in a top `Config` section; in-function literals became named constants (Tk padding as `PAD_*`, MPC weights and `MPC_MAX_ITERATIONS`, `main.py`'s `MAX_BACKLOG_STEPS`).  Mission coordinates and test literals stay inline as data.
- Single sources of truth: `DEFAULT_PRIVILEGE_LEVEL`/`DEFAULT_SYNC_INTERVAL` (`backseater.py`, used by `PlatformSpec` and `bicycle_ugv()`); `KEY_FOLLOWER_TOKENS` (`condition.py`, used by `graph_draft`'s key rename); `POINTS_PER_INCH`, `TOOLTIP_RULE`, and display-space hit-testing in `viz/base.py`; `IDLE_CONTROLS` (`bicycle_ugv/hardware.py`); the editor's `GRAPH_PLOT_BACKGROUND` is imported from the dashboard.
- Renames: `KnowledgeDatabase.declare(key, entry_type, ...)` (was `type`, which shadowed the built-in); `main.py`'s `vizualizer` → `visualizer`.  The assistant's knowledge tools keep a `type` parameter on purpose: it is the model-facing argument name (NOTE in `assistant_tools.py`).
- `continue`/`break` rewritten where a condition, `next()`, or if/else read as clearly (`Backseater.update()`'s edge pick, `World.step()`, the MPC worker loop, the agent loop, `main.py`'s loop); small duplicate helpers folded (`graph_draft.edit_edge` = remove + add, the editor's table/button/dialog builders, the dashboard's tooltip setup).
- Known gaps now carry `TODO`s at the code site (MPC worker timeout, `_check_binding_types` duplication, `PlatformDatabase` self-write-only, full-mesh connectivity, region membership).

## 38 - 2026-11-19: Docs and workflow migration
- Adopted the docs layout from another project: a short `CLAUDE.md` importing `docs/proc.md` (process), `docs/style.md` (code style), `docs/spec.md` (architecture), and `docs/roadmap.md` (build order, open items, known issues); this file holds the history.
- The old root `notes.md` (dated "Status" entries) was condensed into notes 1-37 and deleted; the old `CLAUDE.md` architecture moved to `spec.md`, its build order to `roadmap.md`, its process and style rules to `proc.md`/`style.md`.
- Decisions: tests written whenever worthwhile (the other project's "no tests" default dropped); `style.md`'s four-tier separators and other rules adopted, with the code migrated later per `docs/style_migration.md`; no `to_hardware.md` until a hardware version exists.
- `style.md` gained this repo's rules (layer-tagged debug prints, type hints on public signatures, the test-teardown rule); rule 6 relaxed to allow common short forms (`env`, `dist`) but not cryptic ones.
- `ollama` added to `pyproject.toml`'s dependencies.  Moving `pyproject.toml` + `src/` into `mtofr/` (so the README's `pip install -e ./mtofr` works) is deferred, listed in `roadmap.md`.
- `docs/llm_setup.md` brought current (`llm_config.yaml` is gone; the client exists).

## 37 - 2026-11-19: Platform types live under their environment
- Reverses note 36's "compatible with, not owned by": a bicycle UGV can only live in the ground plane, and the code already implied it (`max_speed_multiplier` sat on the base `Hardware` though only `GroundPlaneEnv` passed it; nothing stopped a platform being placed in an environment it can't live in).
- Rule: a platform type lives in `world/<environment_name>/platforms/<type>/`, next to that environment's `env.py` and Hardware base (`world/<environment_name>/hardware.py`); one needing no environment lives in `world/anywhere/platforms/<type>/` on `StationaryHardware`.  `Platform`/`PlatformSpec` moved up to `world/platform.py`; `world/platforms/` is gone.
- Base `Hardware` has one abstract method, `step_dynamics(dt, environment)`; every subclass declares `environment_type` (an Environment class, or `None` = any), deliberately with no base default so forgetting it is an error.
- Dynamics belong to the vehicle: `Environment` is passive (`GroundPlaneEnv` answers `speed_multiplier_at`/`is_blocked`, steps nothing); `GroundPlaneHardware` holds the old wheeled-vehicle terrain response, using ground-truth state.  A UAV or tracked vehicle would respond differently.
- `ConsoleHardware` is a docstring-only `StationaryHardware` subclass; the interface platform keeps a map position (a placeable ground station, since comms range will matter) rather than a separate position-less environment, which would have needed a multi-environment World.
- `World.__init__` raises `TypeError` for a platform its environment can't host; `World.step()` runs `step_dynamics` per platform, isolated, even when its brain faulted that tick (a real vehicle keeps coasting).  `main.py` shuts platforms down if setup fails after they're built, so no MPC workers are orphaned.
- Open: `WorldState` is still 2D in the base layer; a 3D environment would need its own state type.

## 36 - 2026-11-19: Platform object; World owns platforms
- A "platform" used to exist only by convention, spread over `missions.py` builder closures, three parallel id-keyed dicts in `MissionSetConfig`, `main.py`'s stack-building loop, an `isinstance(MissionEditorFrontseater)` special case, and a `World` that held only backseaters.
- `PlatformSpec` (id, `build_frontseater`, `mission_graph`, `privilege_level`, `clock`, `sync_interval`) and `Platform` (builds the stack + `KnowledgeDatabase`, exposes each layer, owns `attach()`/`shutdown()`).  Each platform type exports a spec factory (`bicycle_ugv(...)`, `interface(...)`, the latter privilege 0).  `MissionSetConfig` is `map_name` + `platforms: list[PlatformSpec]`.
- New no-op `Frontseater.attach(world, window_root=None)`; the editor overrides it to install its window factory, so `main.py` no longer special-cases a platform type.
- `World(environment, platforms)` replaced `World(environment, backseaters)`, no compatibility shim.
- Decisions: Platform is assembly/lifecycle only, not a runtime layer (layers still call each other directly, like separate processes on a robot; it's the per-robot launch file).  Platforms hold no reference to World, so a Platform still means something on hardware where comms replaces World's mesh sync.  World drives each phase across all platforms (no `Platform.step()`), since the `begin_update()`/`finish_update()` split exists so MPC solves overlap.
- Bicycle UGV files moved to `world/platforms/bicycle_ugv/`, interface files to `world/platforms/interface/` (plain filesystem moves, so git sees delete + untracked).

## 35 - 2026-10-01: LLM assistant, state at end of day
- Built (build order step 7, first cut): `agent/agent.py` (streaming tool-call loop, `should_stop`, thinking kept within a turn, stall nudges up to `MAX_NUDGES`, `MAX_REPLY_TOKENS` cap, per-call timings) and `agent/config.py` (`qwen3.5:4b`, `NUM_CTX` 8192, `MAX_ITERATIONS` 12).  Toy tools and the CLI were deleted.
- Observed on CPU: ~4-5 tok/s, ~4.3k prompt tokens per call.  A two-leg mission took ~5 min for the first turn, ~11 min with three correction turns.  Reliable: tool-call syntax, `Location` values, bindings, recovery from tool errors.  Unreliable: setting/reusing the start node, announce-then-stop, rambling when confused, copying the prompt example.
- Open items moved to `roadmap.md` (chiefly a post-turn graph check fed back to the model).
- Working agreements: edits go through the edit tools so the user sees diffs; no tests asserting system-prompt wording; the user runs the real-model tests; don't touch the user's hand-edited prompt unasked.

## 34 - 2026-10-01: LLM assistant window for the mission editor
- "Assistant..." opens `AssistantWindow`, a chat whose LLM edits the same draft as the Editor tab through `_set_draft()` (via `apply_draft_edit()`); one user message = one undo step.
- Tools are 1:1 wrappers of the 14 `graph_draft.py` mutators, deliberately no composite tools (fine-grained, auditable steps are a research point).  Wrappers parse arguments and turn exceptions into readable errors.
- Context per turn: SITUATION (target platform, a WORLD section with axes/extent/regions/terrain/position, capabilities with field meanings, the full draft) then MISSION (the request); history keeps only plain requests and final replies.
- Turns run on a worker thread (Ollama blocks); events and tool calls return over one queue drained by `after(50)`, since tools touch widgets.
- First real runs failed instructively: no coordinate frame, literals passed as primitive inputs, undeclared output keys, ~400 tokens of narration per call.  Fixes: WORLD section, explicit data rules, a worked example (test-enforced to run through the real toolbox), Troop Leading Procedures adapted to an editing assistant.
- "Show thinking" also set `think=True` (~4x slower); renamed "Enable thinking", and thinking is always displayed.  A fixed `MISSION:`/`PLAN:` header backfired (the model called `MISSION(...)` as a tool), so it was dropped.
- A multi-turn run stalled on prose ("I will now add...") and ~4k-token self-talk, caused by the live-state block (last pushed graph) looking inconsistent with the draft and by unbounded replies.  Fixes: live state framed as information only, live Knowledge values omitted, `num_predict` cap, `detect_stall` nudges.
- Bug from a real run: a primitive bound to an undeclared key passed Validate and the push gate, halted at bind time, and crashed the dashboard.  Fixed: `verify_mission_structure()` checks primitive binding keys; `capability.find_binding_problems()` checks each primitive against the target's registry in `write_mission()`, Validate, and the assistant's `add_primitive`/`edit_primitive`; the dashboard shows `<undeclared key ...>` instead of raising.
- `qwen3.5:4b`'s vision isn't used: pixels are a worse coordinate source than the WORLD text and cost context.  A coarse ASCII traversability grid is the better next step if routing matters.
- The user hand-edited the system prompt (operations-order considerations, TLP steps); treat it as theirs.  `llm/ollama/llm_config.yaml` superseded by `agent/config.py`.

## 33 - 2026-10-01: Mission editor moved under the interface platform
- `mission_editor/` moved from `src/mtofr/` to `world/interface/mission_editor/`: it's specific to the interface platform, mirroring how an environment's viewer lives under `world/<environment_name>/viz/`.  Imports and `patch(...)` targets updated.

## 32 - 2026-09-14: Live Control keeps its selection
- The Live Control tab's 1 s refresh wiped the Treeview selection every tick (`delete()`+`insert()` always clears it), the same bug the Editor tables had in note 28.
- Same fix: track `selected_live_knowledge_key` via `<<TreeviewSelect>>`, re-apply after each rebuild; Edit Value reads the tracked key, so a refresh between select and click is harmless.

## 31 - 2026-09-14: Live Control tab, undo/redo, double-click edit
- Undo/redo came free: every mutation goes through `_set_draft()`, which already swaps in a new dict, so `undo_stack`/`redo_stack` (capped at `UNDO_HISTORY_LIMIT` = 50) need no extra bookkeeping.  Ctrl+Z/Y/Shift+Z are bound on the window (not `bind_all`): they fire from any child widget but stay inert while a modal dialog holds the grab.
- Double-click edits every table, alongside the Edit buttons.
- New default tab, "Live Control": the target platform's declared Knowledge, edited directly on the running platform via `KnowledgeDatabase.set()` (no draft/push, since Knowledge writes aren't privilege-gated).  Motivation: steer a running mission through its existing edges without writing a new one.  Refreshes every `LIVE_KNOWLEDGE_REFRESH_MS`.
- `_build_value_fields()`/`_read_value_fields()` extracted to module level and shared by `_KnowledgeDialog` and `_LiveValueDialog`, so a new `KnowledgeEntry` type works in both.
- "Draft loaded from" label removed by request (the Console already logs it); both `after()` loops are cancelled in `close()` instead of tolerating "invalid command name" noise.

## 30 - 2026-09-14: Editor focus, layout, console, draft source
- Dialogs pulled the whole app forward: dropped `transient()`, and `_center_over_parent()` sets `-topmost` instead.
- The Knowledge table never showed its key column (`show="headings"` hid `#0`).  Fixed (Key, Type, Value), and the Editor tab became resizable `PanedWindow`s with a larger default window.
- Validate/Push feedback was easy to miss, so a read-only Console panel logs every action (error popups kept).
- A draft loaded from ugv1 was pushed to ugv2 unnoticed.  Fixed with `draft_source_platform_id` and a non-blocking Console warning on mismatch (reuse across platforms can be intentional).  Declined multi-platform push; added a Draft/Live toggle to the Graph tab (Live renders the target's running graph read-only, refreshed every 500 ms).

## 29 - 2026-09-03: Cascaded Knowledge key rename
- `graph_draft.rename_knowledge_key()` moves the declaration and updates every primitive binding and edge condition that references the old key, instead of leaving them dangling.
- Condition tokens are told apart positionally: per the grammar, a key is always followed by a comparison operator or `"is"`, which a literal never is, so `["status", "==", "arrived"]`'s literal `"arrived"` is left alone.
- The dialog's key field is editable; `_on_edit_knowledge_key()` composes rename then `edit_knowledge_key()` rather than growing one helper.

## 28 - 2026-09-03: Mission editor UX fixes
- Dialogs opened at the screen corner: `_center_over_parent()` on every dialog, with a custom `_TextInputDialog` replacing `simpledialog.askstring`.
- Knowledge types were Location-hardcoded.  `serialization.constructor_fields()` introspects a `KnowledgeEntry` subclass's `__init__` signature (`Location.__init__` gained type hints for this), so a new type needs one line in `KNOWLEDGE_TYPES_BY_NAME`.
- Selection was lost on every refresh: `selected_node_id`/`selected_primitive_name` tracked and re-applied; adding a node auto-selects it.
- `mission_graph_view.py` curves apart edges sharing an unordered endpoint pair (A->B and B->A) with a quadratic bezier.  Hover and label anchor to the bezier midpoint, whose tangent is parallel to the chord, so the arrowhead needed only a midpoint parameter.  The preview moved to its own "Graph" tab (the seed of a future graphical editor).
- Added Edit (not just Add/Remove) for primitives, edges (including moving endpoints), and knowledge keys, via an `existing` parameter on each dialog.

## 27 - 2026-09-03: Mission editor interface platform (build order step 6)
- Built as an ordinary platform (generic Backseater + bespoke `MissionEditorFrontseater` + stationary `ConsoleHardware`), not a bolt-on that bypasses the mesh.
- Editing is not a capability: the one capability, `show_interface`, opens/closes a Tk window; everything the window does lives outside the capability machinery.  Its default graph runs `show_interface` unconditionally.
- The window is a Toplevel on `MissionDashboard`'s root, sharing its cooperative event pump.  A separate process was deferred.
- Edit a local draft (from a live platform deep-copied, a JSON file, or blank) with pure `graph_draft.py` helpers that return new dicts (the layout cache is keyed by `id()`), then push explicitly through `write_mission()`; the editor is just another writer.
- Conditions are typed as raw token literals (`ast.literal_eval` + `parse_condition()`): no tree-to-token serializer exists, and typing was judged enough.  Forms/tables chosen over a drag-and-drop canvas to keep the step small.
- New `MissionSet.VILLAGE_DEFAULT`: every platform boots its default graph; the interface platform sits at a verified clear cell (0, -30).  Every Frontseater must implement `shutdown()`.

## 26 - 2026-09-03: One-call Frontseater lifecycle
- Replaced `start_capability()`/`poll_status()`/`cancel()` and per-primitive handles with `Frontseater.set_active_primitives(primitives)`, called only when the active node's dict changes (by identity).  Edges already read only Knowledge, so polling status every tick bought nothing, and the bespoke part of the system should be as small as possible.
- The Frontseater owns the diff (new -> start, gone -> stop) and how "running" works (tick, thread, ROS nodes).
- Added back introspection as a required abstract `describe_status() -> {"overall", "primitives"}`, display-only (a by-convention Knowledge key was rejected as too easy to forget).
- Fault isolation moved to `World.step()`: each platform's three calls are wrapped individually, and a faulting platform is skipped for the rest of the tick.
- `BicycleFrontseater` rewritten as the reference: plain if/elif over `move_to`/`avoid`/`stopwatch` (a generic handler registry was tried and rejected as ceremony), with a labeled `__init__` for authors to copy.

## 25 - 2026-09-03: Default startup missions (build order step 5)
- `Frontseater.default_mission_graph()` is concrete: an inert single `"startup"` node, so test Frontseaters need no change.  Platform-specific content belongs with the Frontseater, not the platform-agnostic Backseater.
- `BicycleFrontseater` overrides it to loiter on `stopwatch` (a UAV might hover instead).  `Backseater` falls back to it when given `mission_graph=None`, replacing an empty stub with no start node.

## 24 - 2026-09-01: Image-based maps (build order step 4)
- `world/maps/` moved to `maps/` (not ground-plane-specific); `simple_test` renamed `simple_village`.  `GroundMap` loads yaml (pyyaml added) + cosmetic/traversability/regions PNGs; traversability entries became `{name, blocking, speed_multiplier}`.
- World (0, 0) is the image center, +y up (the bicycle model's convention), so sampling flips rows.  Colors snap to the nearest declared color (PNG anti-aliasing); unmatched in-bounds colors are passable, off-map is blocked.
- `GroundPlaneEnv(ground_map=None)`: scales max speed by the multiplier at the current position; a step into a blocked cell is rejected and velocity zeroed (approximate "stop at the boundary", fine at raster resolution).  `blank` is bounded to its image; `map_name=None` is the unbounded mode.
- `PlanePlotter` draws the cosmetic image plus toggleable overlays and legend; gray background off-map; heading drawn as a fixed-size marker (points) instead of a zoom-scaling `ax.arrow()`.  Dashboard: overlay checkboxes, scroll-zoom and drag-pan without the toolbar.
- `missions.py` restructured into one `MissionSetConfig` per `MissionSet` (map + per-platform builders + graphs), since mission sets may want different hardware.  New `VILLAGE` set: ugv1 hits the building and gives up, ugv2 loops road vs. open ground.
- New `stopwatch` capability (sim seconds since start, never completes), used for "give up after N s".
- Deferred: the MPC knows nothing about terrain (it drives straight and gets clamped); see `roadmap.md`.

## 23 - 2026-09-01: Mesh increment 6, World integration (build order step 3 done)
- `World.step()` calls `sync_with_stale_peers()` for every backseater with every other one as peers (full mesh), last in the tick so a synced fact is seen by next tick's edges.  `World` takes no `relay=`; `relay/relay.py` and its tests deleted, no coexistence.
- Mission Overview's knowledge panel is left empty: there is no canonical cross-platform store anymore, and the panel's real job is the platform list.
- New `test_multi_platform_mesh_integration.py` (ugv2 waits on `ugv1/arrived`, and a Mission entry gossips, purely through `World.step()`).  Fixed a test whose two platforms shared a bare `"target"` key, which mesh sync now clobbered.
- The user recorded the experiment plan (now in `spec.md`): compare human teleoperation to autonomy for scripted pick-up/drop-off logistics missions, in sim and on hardware.

## 22 - 2026-08-28: Deterministic Frontseater shutdown in tests
- `unittest discover` crashed the interpreter (`_PySemaphore_Wakeup ... ReleaseSemaphore failed`), though every file passed alone.  Cause: `BicycleFrontseater` workers were only stopped by `__del__`, so GC-timed teardown raced other tests.
- Every test building one now shuts it down (`tearDown()`/`addCleanup()`); per-test helpers take `self` and register the cleanup.  Became a standing style rule.

## 21 - 2026-08-21: Mesh increment 5, `sync_with()` and Clock
- `Backseater.sync_with(peer)` reconciles all three databases both ways, last-write-wins by locally converted timestamp, via a shared `_reconcile_database()`.  Pulled timestamps are converted with `Clock.to_local()` and stored, never re-stamped "now" (a re-stamped fact would out-race its origin and oscillate).
- Opens with `_handshake_clock()`: each side records `peer.clock.now() - self.clock.now()` in `Clock`'s per-peer offset table (a real computation, ~0 until latency is simulated).
- Received Mission/Platform entries bypass the write gates (checks happen once, at the writer).  Self-records echoed back get no special case; last-write-wins suffices.
- Symmetric and idempotent, so either side may initiate with no lock or tie-break.  `sync_with_stale_peers(peers)` syncs only peers older than `sync_interval` (default 1 s).  A checksum short-circuit (the user's request, from the old Relay) skips unchanged pairs.

## 20 - 2026-08-21: Mesh increment 4, continuous `query()`/`publish()`
- `frontseater.backseater = self` (mirrors the `platform_id` cascade).  `query(database_name, key)`/`publish(...)` over `"knowledge"`/`"mission"`/`"platform"`; a `"mission"` publish goes through `write_mission()`.  `declare_knowledge_key()` declares new keys (Knowledge only).
- Eager resolve-then-execute removed outright (`_resolve_inputs`/`_commit_outputs`, `validate_inputs`/`validate_outputs`); primitives receive key names, not values.
- Added `_check_binding_types()` at bind time (the user's request mid-session), since removing eager resolution removed the only type check before a capability ran.
- `move_to` re-queries its target each poll (mid-flight retargets work); `avoid` queries once.

## 19 - 2026-08-21: Mesh increment 3, mission-change detection
- `_detect_mission_change()` at the top of `update()` (before the blocked early return, so a new mission un-blocks): compares `mission_database.get(platform_id)` to the current graph by identity, since not every `KnowledgeEntry` defines `__eq__` and a new mission always arrives as a new object.
- On change: cancel old primitives, reset knowledge to the new graph's defaults, swap the graph and parsed conditions, clear blocked, and activate the start node the same tick.
- Detection lives in `update()`, not `write_mission()`, so mesh-synced missions (written directly) trigger it too.  Renamed from "hot-swap" at the user's request.

## 18 - 2026-08-21: Database package split
- `knowledge/knowledge.py` and `database/database.py` became `database/knowledge.py` (`KnowledgeDatabase`), `database/knowledge_types.py` (`KnowledgeEntry`, `Location`; kept apart so new types don't grow the store file), and `database/platform_keyed.py` (the platform-keyed family).  `database/__init__.py` re-exports all, so callers import `mtofr.database`.

## 17 - 2026-08-19: Mesh increment 2, privilege and gated Mission writes
- `Backseater(privilege_level=1)` (0 reserved/highest) and `write_mission(mission_graph, writer_platform_id, timestamp=None)`: privilege check (skipped for self-writes), type check, `verify_mission_structure()` (edge keys declared; `MissionStructuralError(ValueError)` so callers can tell it apart).
- Both privilege levels are read from the target's own `PlatformDatabase`; an unknown writer is rejected with `PermissionError`.  This keeps Backseaters ignorant of each other.
- Merged the increment-1 Capabilities and Status databases into `PlatformDatabase` (`PlatformRecord(privilege_level, status, capabilities)`): privilege needed a home, and one gossiped record per platform is simpler than three.
- Renamed `Backseater.knowledge` to `knowledge_database`.  Runtime privilege reassignment deferred.
- Increment 1 (same week): Mission/Capabilities/Status databases added beside Knowledge, all with `origin_platform_id`.

## 16 - 2026-08-19: Peer-to-peer mesh redesign decided
- Supersedes notes 11 and 15.  No central Relay: each platform's databases sync pairwise, full mesh (connectivity assumed for now).  World mediates who talks to whom; Backseater owns what a sync does; Backseaters hold no peer references.
- Running capabilities talk to Backseater continuously (`query()`/`publish()`, declare new keys) instead of resolve-then-execute.
- Per-platform databases: Knowledge, Mission (gated: privilege, type, structure), Capabilities and Status (self-write, gossiped); `origin_platform_id` on every entry.  Checks happen write-side only, never on receipt.
- Privilege: integer levels, 0 highest, assigned by the harness; only a strictly higher level may write another's Mission.  A deliberate placeholder, not security.
- Clock repurposed: per-peer offsets from each sync handshake; no shared clock.  Last-write-wins remains a named simplification (vector clocks/CRDTs judged not worth it: no general merge rule for arbitrary values).
- Every platform boots a default mission; the operator/LLM interface is just another platform.  Mission authoring deferred (later build order step 6).
- Build order renumbered: mesh redesign became step 3 (six increments), Foreman/Frontend dropped.

## 15 - 2026-08-17: Four-relay and full-mesh discussions (superseded by note 16)
- The user dropped Foreman (cross-platform coordination is entirely Knowledge-mediated; cross-graph inspection belongs in the visualizer) for four relays (Knowledge, Status, Capability, Graph) plus a `MissionBuilder` editing surface.  Not built.
- Same night, a full-mesh alternative was weighed: a central relay conflicts with "comms-denial tolerant as first-class" (cf. ROS1 `roscore` vs. ROS2 DDS).  Ideas that survived into note 16: `origin_platform_id`, default missions for every platform, the interface-as-platform, dropping Foreman.  Ideas dropped: mission graphs and capabilities stored as plain Knowledge entries with no privileged write path.
- Open holes raised then and later resolved by notes 16-21: hot-swap semantics, adoption-time verification, clock ownership without a relay, O(n²) sync.

## 14 - 2026-08-17: Performance pass
- The literal cause of "one core maxed": `main.py`'s loop busy-spun; it now sleeps 1 ms when a tick does no work.
- Mission-graph layout cached by `id(graph)`, with the cache holding a strong reference so a reused id can't return a stale layout.  Redraw decoupled from physics (once per outer loop).
- MPC hot path: scalar `math` instead of numpy, cost matrices inlined; 4.6x faster single-process.
- Multiprocessing (at the user's request): `Frontseater.begin_update()`/`finish_update()`; `World.step()` begins all, then finishes all, so solves overlap.  `BicycleFrontseater` has one persistent worker per platform holding the warm start (the user's choice over a pool).  Naive protocol, no timeout or recovery.  Dynamics factored into `dynamics.bicycle_step()`, shared by hardware and MPC.
- Windows "spawn" re-imports the launch script in each worker, so all of `main.py`'s setup lives under `if __name__ == "__main__":` (any script building a `BicycleFrontseater` needs the same guard).
- SLSQP `maxiter` capped at 20: worst ticks were hitting the default 100 near obstacles (100-250 ms) while median solves take 11 iterations.  Worst tick fell 250 ms -> 72 ms; ~12% of solves hit the cap.  Normal receding-horizon practice, since the next tick re-solves from a warm start.
- New `scripts/mpc_profile.py` (tick-time and iteration percentiles).  An analytic gradient is the largest remaining lever, not tried.

## 13 - 2026-08-17: Mission Overview polish
- Graph panel always titled "Mission Overview"; the edge-label checkbox and a new back button show only for a single platform.
- `PlatformOverviewViewer` rows always show `platform_id: "active_node"` beside a square marker (the hover/click target); clicking a row selects that platform.
- Mission Overview and the Knowledge panel are the defaults; knowledge columns reordered Name/Type/Value with fixed widths.

## 12 - 2026-08-17: Relay (later replaced by the mesh)
- `clock/clock.py` (`Clock`: wall time + offset) on Backseater.  Knowledge gained per-key timestamps and `set_or_declare()` (a deliberately rare bypass for facts no graph declared).
- `Relay` held a canonical store; `sync()` each tick, after dynamics: pull (last-write-wins, checksum-skipped when unchanged, the user's idea), then push without re-stamping (a re-stamped fact would out-race its origin and oscillate).
- `status()`'s per-primitive `"handle"` became `"inputs"`; the dashboard resolves live values itself.
- Mission naming `mission_<set>_<platform_id>`; new WAIT set (ugv2 waits on `ugv1/arrived`).  New Mission Overview dropdown entry and `PlatformOverviewViewer`; tooltips lead with a title line.

## 11 - 2026-08-17: Foreman/Relay/Frontend design (superseded by note 16)
- Proposed planner layer: Foreman (graph manager, verify, delegate), Relay (canonical Knowledge, conflict resolution), Frontend (user + LLM, same methods for both).  Only Relay was built.
- Verify: every edge-condition key must be declared; reachability deferred (a terminal node is legitimately edge-less).  Runs on demand and as a gate before issuing, not on every edit.  Last-write-wins and clock sync flagged as placeholders.

## 10 - 2026-08-17: Second platform, platform identity
- Structural check that two independent platforms run in one World.  `World`, the dashboard, and the plotter were already id-keyed; only `main.py` hardcoded one platform.
- Identity: `Backseater(platform_id=...)` is the only place it's set; `Frontseater.platform_id` is a property whose setter cascades to `Hardware.platform_id`.
- Mission dicts moved to `missions.py`.  No collision handling ("pass through each other").

## 9 - 2026-08-13: Local LLM via Ollama
- The mission-commander LLM runs locally on Ollama, `qwen3.5:4b`, CPU-only; no cloud API (no sustained free Claude API tier; Ollama Cloud is a separate paid product).  Backups considered: Phi-4-mini, Gemma 4 E4B.
- `llm/ollama/` holds start/stop scripts (`llm/` general, `ollama/` this runner).  `stop_ollama.bat` kills the tray app (`ollama app.exe`) before `ollama.exe`, since the tray app respawns the server.
- Config passed per `/api/chat` call rather than baked into a model with `ollama create`, so the prompt can change without a rebuild.  Setup lives in `docs/llm_setup.md`.

## 8 - 2026-08-13: Knowledge-based edge conditions
- Edges transition on Knowledge conditions, not primitive status; a capability decides what to write (`move_to` writes `arrived`, reset to `False` on a new target; `avoid` writes `registered`).
- `condition/condition.py`: pre-tokenized lists (`["ugv1/arrived", "==", True, "and", ...]`) parsed by recursive descent into a typed tree.  Tokens are real Python values, so there's no literal parsing and no `eval()`.  Chosen over a nested-dict tree (doesn't read like the expression) and a plain string (needs literal parsing).  Fixed an end-of-tokens sentinel that collided with a literal `None`.
- Every capability field, input or output, is a Knowledge key (no raw literals); one `ParamSpec` serves both.  Knowledge became type-locked (`declare()`/`set()`), with declarations in the graph's top-level `"knowledge"` section.
- Fixed a stale-output bug: a newly started primitive is polled the same tick, so a reset output lands before edges are evaluated.
- Renames: `actuate` -> `start_capability`; primitive keys `type`/`params` -> `capability`/`inputs`/`outputs`.  `move_to`'s `tolerance` became a per-mission input.

## 7 - 2026-08-12: Dashboard polish
- The BFS-column layout put cycles on one row, so closing edges curved and couldn't be hovered.  Replaced by a deterministic force-directed (Fruchterman-Reingold-style) layout, seeded on a circle.
- Explicit axis limits with fixed padding (autoscale clipped flat graphs); hover hit-tests in display pixels so it stays right across resize, pan, and zoom; tooltips flip inward near edges.
- Arrowheads drawn at edge midpoints (at the target they hid under the node marker).  The view keeps the user's pan/zoom across redraws.
- Known limit: the layout is O(n²) per iteration, untested at scale.

## 6 - 2026-08-12: Mission dashboard; Memory renamed Knowledge
- `EnvironmentViewer` ABC (`viz/base.py`) draws onto a caller-owned Axes; each environment supplies its own (`PlanePlotter` moved to `world/ground_plane/viz/`).
- `MissionDashboard` (Tkinter): platform dropdown, environment view, mission graph with hover, one capability/knowledge panel switched by a selector, and the sim's pause state.
- `Backseater.status()`: a read-only snapshot, the same query-path idea as `capabilities()`.
- `Memory`/`MemoryEntry` renamed `Knowledge`/`KnowledgeEntry`.  Debug prints gated by `debug` constructor flags.

## 5 - 2026-08-12: Capability registry (build order step 2)
- `capability/capability.py`: `ParamSpec`, `Capability`, `CapabilityRegistry`.  Each Frontseater builds its own registry; a planner learns what a platform can do only by asking its Backseater (`capabilities()`), with no central manifest.
- Entry types self-describe (`describe()` on the `KnowledgeEntry` ABC), so capabilities and their types are understandable without source.
- One name per capability: `ipl_type` is what the Frontseater receives (dropped the `move_to` -> `navigate` mapping).
- First `tests/` directory (stdlib `unittest`; pytest isn't installed and the project stays pure Python).

## 4 - 2026-08-12: Backseater/Frontseater/Hardware split
- Agent became Backseater (platform-agnostic, issues capability requests, never controls).  Platform split into Frontseater (planning/control brain: MPC, capabilities) and Hardware (MCU-equivalent: owns `WorldState`, dynamics, `send_controls`/`read_state`), like a companion computer talking to firmware.
- `read_state()` goes through a `PerfectSensor` stub, a seam for a future noisy sensor.
- Naming rule: avoid abbreviations in identifiers.
- Original build order: rename/split, capability registry, minimal planner, comms boundary with delay, edge staleness/timeouts, concurrent active nodes, second platform with cross-platform edges, OPORD/world-state layer.  Later reshaped (note 16; current order in `roadmap.md`).

## 3 - 2026-08-10: First layered architecture
- World (environment + agents, tick loop), Agent (mission graph, memory, task handles; never touches `WorldState`), Platform `BicycleUGV` (state + warm-started scipy MPC; `actuate`/`poll_status`/`cancel`), `GroundPlaneEnv` (infinite plane), per-agent Memory.
- Missions are graphs: nodes hold concurrent primitives, edges hold conditions (replacing a flat list).
- Principles: continuous capabilities (`move_to`, `avoid`) are persistent state feeding one MPC cost; discrete ones use ROS-action-like start/poll/cancel.  The LLM will write a DSL compiled and validated into the graph, and the graph is an artifact a human commander can review.
- Open at the time: `avoid` as a primitive is awkward (no real done state); only one platform type and environment existed to validate the abstractions.

## 2 - 2026-08-08: Design principles
- Continuous actions (optimal control toward a goal) and discrete actions (do once) are handled by separate mechanisms, never blended.
- MTOFR never controls hardware directly: it puts the robot at the right place at the right time and signals another process to act, so hardware programs change without changing MTOFR.
- Actions are started, then checked (`waiting`/`success`/`fail`/`timeout`), and can be cancelled for a higher-priority task.

## 1 - 2026-08-07: Initial sim loop
- Live loop: `World.step()` -> agents plan -> environment steps dynamics -> mission update -> matplotlib dot + heading arrow.
- Package `src/mtofr/` (editable install): `world/` (`WorldState`, `Platform`/`Environment` ABCs, `World`, `GroundPlaneEnv`, `BicycleUGV`), `agent/`, `memory/` (`Memory`, `Location`), `viz/plane_plotter.py`; `main.py` runs a fixed-timestep loop.
