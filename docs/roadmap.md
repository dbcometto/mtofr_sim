# Roadmap

## Current Status
- Done: the peer-to-peer platform stack, image-based maps, default missions, the mission editor (interface platform), and the reorganization into layered packages (build order steps 1-7).  The LLM assistant (step 10) has a first cut.  The web UI (step 8) has a first cut, routed through the interface's own Backseater, with live `PlatformRecord` gossip and pose (notes 41-42), a graphical editor and per-window sessions (note 43), and an editor document, incomplete requests, a condition builder, and a Knowledge panel (note 44).
- Next: the web UI's open items (below).  On the LLM side, the post-turn graph check (Next Up for LLM Agent, below).



## Build Order
1. [x] Backseater/Frontseater/Hardware split (note 4)
2. [x] Capability registry (note 5)
3. [x] Peer-to-peer mesh: databases, privilege, mission change, `query()`/`publish()`, `sync_with()`, World integration (notes 16-23)
4. [x] Image-based maps: cosmetic, traversability, and region layers, physically enforced (note 24); region membership is still display-only
5. [x] Default startup missions (note 25)
6. [x] Manual mission-authoring "interface" platform (notes 27-33)
7. [x] Reorganization: layered packages, `mission/`, `scenarios/`, environment-specific state; primitive → capability request (note 40)
8. [~] Web UI capability so interface is more flexible: first cut done (Tk parity, panel seam, mesh-routed, graphical editor, per-window sessions; notes 41-43); see open items below
9. [ ] Re-touch user experience implementing platforms and capabilities so it is clean and easy
10. [ ] Convoying-related capabilities
11. [ ] [~] Agentic LLM on the interface platform: first cut done (the mission-editor assistant, notes 34-35); see open items below
12. [ ] Teleop on the interface platform, for the experimental comparison (inside the existing system if it fits)



## Web UI Open Items
1. Usability: graphical editing, edge reordering, the condition builder, live validation (⚠), inline capability requests, and the Knowledge panel are done (notes 43-44).  Still open: the condition builder can't nest and/or groups (nested conditions use raw tokens), and the table Editor tab is off and may be retired.
2. The LLM assistant as a web panel.  `DraftToolbox` is already the Editor's command layer, so it can edit the same draft.
3. A map panel (overhead view with `<id>/pose` markers), then panels like obstacle painting, which would submit painted obstacles as Knowledge.  The map asset would be the panel's own config, never `World`.
4. A per-platform port: two interface platforms would collide on `WEB_PORT`.
5. Retire the Tk editor's direct writes (it calls the target's `write_mission()` and reads `World`), or retire the Tk editor itself once the web UI supersedes it.
6. `CapabilityRegistry` and `KnowledgeEntry` values are gossiped as in-process objects; a real comms boundary needs them serialized (`encode_capabilities()` in `web/encoding.py` is a start).
7. `WebHost.editor_store` is memory-only: a sim restart forgets pushed missions' layouts (saved files keep theirs).  Two different missions given the same name share one entry.



## Next Up for LLM Agent
- Post-turn graph check fed back to the assistant: empty start node, nodes unreachable from the start, edges to missing nodes, unused keys.  One feedback message before the turn ends.  It would have saved the correction turns seen so far, and fills the edge-reachability gap in `verify_mission_structure()`.



## LLM Assistant Open Items
1. The post-turn graph check (above).
2. Narration (the TLP-style text from the user's prompt) is most of the generation time.  Shortening it is the user's design call.
3. The prompt example's "rename the starting node" sentence, which the model copies (user's text).
4. If stalls continue, an explicit `finish(summary)` tool is sturdier than the announce-pattern heuristic, which can misfire.
5. A larger model needs a GPU (2-3x slower per token on this CPU); no alternative model has been tried.
6. Stretch goals: a `get_draft` self-refresh tool; an ASCII traversability grid for routing around blocked terrain.
7. `describe_world()` (`assistant_prompt.py`) reads `environment.ground_map` and `state.x/.y`, which is ground-plane knowledge inside an `anywhere` platform.  A per-environment `describe()` (e.g. on `Environment`) would remove the leak.



## Future Steps (maybe)
1. A real comms boundary with simulated delay (planner↔backseater, backseater↔frontseater), and partial/topological mesh connectivity instead of a full mesh.  An operator should only see platforms in comms range.
2. An advanced world (CalTopo?).
3. Terrain-aware MPC: `solve_mpc` only knows fixed speed limits and straight-line target/avoid costs.  The speed multiplier and blocking are applied afterwards by `GroundPlaneHardware.step_dynamics`, so the planner neither seeks roads nor anticipates walls.  Blocked cells could act like `avoid` regions and slow terrain could add cost.
4. Concurrent active nodes in a mission graph, and staleness/timeout semantics on edges.
5. Frontseater → user/LLM text messages for replanning (`PlatformStatus.message` is the seed).
6. An object/world-state/OPORD layer (object lists, confidence, OPORD parsing).


## Reach Goals
- Logistics: hardware limits, refueling (battery/gas), and pick-up/drop-off of cargo containers.  Interview heavily to nail down the details.
- Scenario scripting for experimental mission drops, and metric collection



## Deferred and Known Limitations
- Runtime privilege reassignment ("may assign levels ≤ its own, never its own") is specified but not implemented.
- `verify_mission_structure()` doesn't check edge reachability (a terminal node can legitimately have no edges).
- Last-write-wins is a named simplification, not consensus; mesh sync is O(n²) in platform count.
- The MPC worker protocol has no timeout or crash recovery.  An analytic MPC gradient (the biggest remaining speed lever) hasn't been tried.
- A platform's `State` is its environment's own type, and `World` is single-environment, so cross-environment geometry (comms range between a UGV and a UAV) has no common frame yet.  A shared placement frame (e.g. geodetic) would be needed for a multi-environment `World`.
- `compute_graph_layout()` is O(n²) per iteration and untested on large graphs.
- `avoid` as a mission capability is conceptually awkward (it has no real "done" state); a separate mechanism may fit better.
- No security beyond the privilege placeholder; no adversarial actor is modeled.
- A single slow computation (e.g. one MPC solve) freezes the UI for its duration, since Tk is pumped between calls.
- Test noise: Tk tests print "Exception ignored ... main thread is not in main loop" at teardown (GC of Tk objects).  Harmless.



## Housekeeping
- Move `pyproject.toml` and `src/` into a `mtofr/` folder so the README's `pip install -e ./mtofr` works.



## Known Issues
- Both UGVs' default missions declare the same un-prefixed `startup/elapsed_time` key, so they overwrite each other through mesh sync (last write wins).  It should be `<platform_id>/elapsed_time`, like `<platform_id>/pose`.
