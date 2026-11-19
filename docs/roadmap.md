# Roadmap

## Build Order
1. [x] Backseater/Frontseater/Hardware split (note 4)
2. [x] Capability registry (note 5)
3. [x] Peer-to-peer mesh: databases, privilege, mission change, `query()`/`publish()`, `sync_with()`, World integration (notes 16-23)
4. [x] Image-based maps: cosmetic, traversability, and region layers, physically enforced (note 24); region membership is still display-only
5. [x] Default startup missions (note 25)
6. [x] Manual mission-authoring "interface" platform (notes 27-33)
7. [~] Agentic LLM on the interface platform: first cut done (the mission-editor assistant, notes 34-35); see open items below
8. [ ] Logistics: hardware limits, refueling (battery/gas), and pick-up/drop-off of cargo containers.  Interview heavily to nail down the details.
9. [ ] Teleop on the interface platform, for the experimental comparison (inside the existing system if it fits)
10. [ ] Scenario scripting for experimental mission drops, and metric collection



## Next Up
- Post-turn graph check fed back to the assistant: empty start node, nodes unreachable from the start, edges to missing nodes, unused keys.  One feedback message before the turn ends.  It would have saved the correction turns seen so far, and fills the edge-reachability gap in `verify_mission_structure()`.



## LLM Assistant Open Items
1. The post-turn graph check (above).
2. Narration (the TLP-style text from the user's prompt) is most of the generation time.  Shortening it is the user's design call.
3. The prompt example's "rename the starting node" sentence, which the model copies (user's text).
4. If stalls continue, an explicit `finish(summary)` tool is sturdier than the announce-pattern heuristic, which can misfire.
5. A larger model needs a GPU (2-3x slower per token on this CPU); no alternative model has been tried.
6. Stretch goals: a `get_draft` self-refresh tool; an ASCII traversability grid for routing around blocked terrain; unifying `Backseater._check_binding_types` with `find_binding_problems`, which duplicate logic.



## Future Steps (maybe)
1. A real comms boundary with simulated delay (planner↔backseater, backseater↔frontseater), and partial/topological mesh connectivity instead of a full mesh.  An operator should only see platforms in comms range.
2. An advanced world (CalTopo?).
3. Terrain-aware MPC: `solve_mpc` only knows fixed speed limits and straight-line target/avoid costs.  The speed multiplier and blocking are applied afterwards by `GroundPlaneHardware.step_dynamics`, so the planner neither seeks roads nor anticipates walls.  Blocked cells could act like `avoid` regions and slow terrain could add cost.
4. Concurrent active nodes in a mission graph, and staleness/timeout semantics on edges.
5. Frontseater → user/LLM text messages for replanning (`PlatformStatus.message` is the seed).
6. An object/world-state/OPORD layer (object lists, confidence, OPORD parsing).



## Deferred and Known Limitations
- Runtime privilege reassignment ("may assign levels ≤ its own, never its own") is specified but not implemented.
- `verify_mission_structure()` doesn't check edge reachability (a terminal node can legitimately have no edges).
- Last-write-wins is a named simplification, not consensus; mesh sync is O(n²) in platform count.
- The MPC worker protocol has no timeout or crash recovery.  An analytic MPC gradient (the biggest remaining speed lever) hasn't been tried.
- `WorldState` is 2D (x, y, theta) in the base layer; a 3D environment (e.g. a UAV) needs its own state type.
- `compute_graph_layout()` is O(n²) per iteration and untested on large graphs.
- `avoid` as a mission primitive is conceptually awkward (it has no real "done" state); a separate mechanism may fit better.
- No security beyond the privilege placeholder; no adversarial actor is modeled.
- A single slow computation (e.g. one MPC solve) freezes the UI for its duration, since Tk is pumped between calls.
- Test noise: Tk tests print "Exception ignored ... main thread is not in main loop" at teardown (GC of Tk objects).  Harmless.



## Housekeeping
- Move `pyproject.toml` and `src/` into a `mtofr/` folder so the README's `pip install -e ./mtofr` works.



## Known Issues
- None currently
