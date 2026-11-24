# Roadmap

## Current Status
- Done: the peer-to-peer platform stack, image-based maps, default missions, the mission editor (interface platform), and the reorganization into layered packages (build order steps 1-7).  The LLM assistant (step 10) has a first cut.  The web UI (step 8) has a first cut, routed through the interface's own Backseater, with live `PlatformRecord` gossip and pose (notes 41-42), a graphical editor and per-window sessions (note 43), and an editor document, incomplete requests, a condition builder, and a Knowledge panel (note 44).
- The web UI is working and is the primary interface (checkpoint: note 46).  What remains for it is its open items below, not new features.
- The interface is now a ground_plane platform with a map sensor, feeding a World Viewer panel with a trajectory drawer.  `Trajectory` and `follow_trajectory` exist, and `environments/anywhere/` is gone (note 48).
- Convoying has begun: a `follow` capability (offhooked point, paper MPC cost, dead-reckoned synced pose), and adoption keeps keys in another platform's namespace (note 49).
- Next: the web UI's open items and known issues (below), and build order step 9.  On the LLM side, the post-turn graph check (Next Up for LLM Agent, below).



## Build Order
1. [x] Backseater/Frontseater/Hardware split (note 4)
2. [x] Capability registry (note 5)
3. [x] Peer-to-peer mesh: databases, privilege, mission change, `query()`/`publish()`, `sync_with()`, World integration (notes 16-23)
4. [x] Image-based maps: cosmetic, traversability, and region layers, physically enforced (note 24); region membership is still display-only
5. [x] Default startup missions (note 25)
6. [x] Manual mission-authoring "interface" platform (notes 27-33)
7. [x] Reorganization: layered packages, `mission/`, `scenarios/`, environment-specific state; primitive → capability request (note 40)
8. [~] Web UI capability so interface is more flexible: working (Tk parity, panel seam, mesh-routed, graphical editor, per-window sessions, editor document, condition builder, Knowledge panel; notes 41-44, checkpoint note 46; World Viewer and trajectory drawer, note 48); open items below
9. [~] Re-touch user experience implementing platforms and capabilities so it is clean and easy: friction written up in `checklists.md` (note 45); capabilities as single classes, the Frontseater base lifecycle, and automatic Knowledge-type/scenario registration done (note 47).  Still open: actuation arbitration and environment leaks (`checklists.md` friction 5 and 7)
10. [~] Convoying-related capabilities: `follow` done (note 49); see Convoy Open Items below
11. [ ] [~] Agentic LLM on the interface platform: first cut done (the mission-editor assistant, notes 34-35); see open items below
12. [ ] Teleop on the interface platform, for the experimental comparison (inside the existing system if it fits)



## Web UI Open Items
1. Usability: graphical editing, edge reordering, the condition builder, live validation (⚠), inline capability requests, and the Knowledge panel are done (notes 43-44).  Still open: the condition builder can't nest and/or groups (nested conditions use raw tokens), and the table Editor tab is off and may be retired.
2. The LLM assistant as a web panel.  `DraftToolbox` is already the Editor's command layer, so it can edit the same draft.
3. Done: the World Viewer (overhead view of the sensed map with `<id>/pose` markers, plus a trajectory drawer; note 48).  Still open: tools like obstacle painting, which would submit painted obstacles as Knowledge.  The drawer's output is copy/paste text; a direct write-back is the Future Work section below.
4. A per-platform port: two interface platforms would collide on `WEB_PORT`.
5. Retire the Tk editor's direct writes (it calls the target's `write_mission()` and reads `World`), or retire the Tk editor itself once the web UI supersedes it.
6. `CapabilityRegistry` and `KnowledgeEntry` values are gossiped as in-process objects; a real comms boundary needs them serialized (`encode_capabilities()` in `web/encoding.py` is a start).
7. `WebHost.editor_store` is memory-only: a sim restart forgets pushed missions' layouts (saved files keep theirs).  Two different missions given the same name share one entry.
8. The condition builder's operator list and token assembly (`draft_tools.js`) restate the grammar in `condition.py`, and `condition_rows()` (Python) is the other direction.  Keep them in step if the grammar changes.



## Convoy Open Items
1. Tracking lag scales with speed: the MPC treats the offhooked point as stationary over its horizon, so a follower sits behind it (headless smoke test: a median of 0.4 m at 1 m/s and 0.8 m at 2 m/s, so gaps run about 1.5-2 m for a 1 m following distance).  This is the paper's formulation; feeding the point's predicted motion into the rollout would cut it.
2. A follower needs a higher top speed than its leader to close a gap, since it waits at the start.  Hardware limits aren't exposed by `bicycle_ugv()`.
3. Dead-reckoning cuts the synced pose's error from a median of about 1.0 m to 0.16 m at 2 m/s (1 s `sync_interval`).  A leader that changes speed sharply (`follow_trajectory` on short legs, up to 8 m/s) still outruns it.
4. No string-stability analysis (the paper's future work too), and no convoy scenario yet (user's call).



## Future Work: Values a Mission Can't Carry Yet (note 46)
A value made in a specialized viewer has no direct path into a mission today.  The trajectory drawer works around this with plain text (`Trajectory` is one JSON-text field, copied and pasted by the operator; note 48); a richer value can't:
- **Adoption resets declared keys.** `Backseater._declare_knowledge_keys()` sets every key the new mission declares back to its default, so a value staged live before the push is overwritten.  Reset is still right for run flags like `ugv1/arrived`.  Partly resolved (note 49): a key in another known platform's namespace keeps its live value.  A key in the target's own or a shared namespace still resets.
- **Only the editor writes draft values.** No other panel can contribute a value to the window's draft.
- **Rich values have no encoding.** `KnowledgeEntry` types serialize through flat scalar constructor fields only, so a waypoint list or an image can't be declared, edited, saved, or sent.
- **Large values cost every sync and poll.** `_snapshot_checksum()` `repr()`s every value, and the web state resends every value each poll.

Directions to weigh (interview first; none chosen):
- a per-key "keep live value" flag on declarations, so adoption keeps a staged value of the right type (considered in note 49 and declined, since it waters down the mission specification; the namespace rule was chosen instead);
- panels registered as typed value editors: editing a Trajectory key opens the drawer, which writes back into the draft (or publishes live);
- per-type JSON encode/decode hooks on `KnowledgeEntry` (e.g. base64 images), hashed sync checksums, and on-demand fetch of large values in the web UI;
- for constrained comms, content-addressed blobs: Knowledge holds a reference (hash, media type, size), and the bytes sync separately and lazily.



## Next Up for LLM Agent
- Post-turn graph check fed back to the assistant: empty start node, nodes unreachable from the start, edges to missing nodes, unused keys.  One feedback message before the turn ends.  It would have saved the correction turns seen so far, and fills the edge-reachability gap in `verify_mission_structure()`.



## LLM Assistant Open Items
1. The post-turn graph check (above).
2. Narration (the TLP-style text from the user's prompt) is most of the generation time.  Shortening it is the user's design call.
3. The prompt example's "rename the starting node" sentence, which the model copies (user's text).
4. If stalls continue, an explicit `finish(summary)` tool is sturdier than the announce-pattern heuristic, which can misfire.
5. A larger model needs a GPU (2-3x slower per token on this CPU); no alternative model has been tried.
6. Stretch goals: a `get_draft` self-refresh tool; an ASCII traversability grid for routing around blocked terrain.
7. Resolved (note 48): `describe_world()` (`assistant_prompt.py`) reads `environment.ground_map` and `state.x/.y`, which is no longer a leak now that the interface is a ground_plane platform.  It still reads `World` directly (the Tk path); a web-panel assistant would read the sensed map instead.



## Future Steps (maybe)
1. A real comms boundary with simulated delay (planner↔backseater, backseater↔frontseater), and partial/topological mesh connectivity instead of a full mesh.  An operator should only see platforms in comms range.
2. An advanced world (CalTopo?).
3. Terrain-aware MPC: `solve_mpc` only knows fixed speed limits and straight-line target/pose/avoid costs.  The speed multiplier and blocking are applied afterwards by `GroundPlaneHardware.step_dynamics`, so the planner neither seeks roads nor anticipates walls.  Blocked cells could act like `avoid` regions and slow terrain could add cost.
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
- Flaky: `test_web_server`'s `test_a_missing_or_malformed_session_id_is_a_bad_request` errored once in a full-suite run (2026-11-24) and passed alone.  The cause is unconfirmed.



## Housekeeping
- Move `pyproject.toml` and `src/` into a `mtofr/` folder so the README's `pip install -e ./mtofr` works.



## Known Issues
- Both UGVs' default missions declare the same un-prefixed `startup/elapsed_time` key, so they overwrite each other through mesh sync (last write wins).  It should be `<platform_id>/elapsed_time`, like `<platform_id>/pose`.
- `as_knowledge_value()` reads a bare JSON-list string as positional fields.  So a Trajectory value sent as `"[[0, 0], [5, 5]]"` (rather than `{"waypoints": "..."}`) is misread and refused.  The web forms send the field dict, and `Trajectory.describe()` tells the LLM the right form, but a single-field type could be special-cased.
- Mesh sync runs on wall time (`sync_interval`), so a headless loop stepping faster than real time delays mission adoption by many sim seconds.  `main.py` paces at real time, so only scripts are affected.
