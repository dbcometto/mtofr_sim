# Notes


## Status 19 Aug 26 — peer-to-peer mesh redesign finalized (supersedes Foreman/Relay/Frontend and four-relay/MissionBuilder)
(Written by Claude)

Design-only session (no code changes yet), prompted by the user with a fully worked-out
target architecture, superseding both the 17 Aug evening Foreman/Relay/Frontend design and
the 17 Aug night four-relay + MissionBuilder design below — neither of those is being built.
This finalizes the direction the 17 Aug (very late) "distributed/full-mesh redesign
discussion" entry below had already sketched as undecided; that discussion is now decided,
with several details it left open now settled (see interview answers below).

**Core shift**: Backseater still fully owns the mission graph, capability dispatch, and
enabling/disabling of capabilities — unchanged. What's new is that Frontseater/Backseater
communication becomes continuous during a capability's execution rather than a one-shot
resolve-then-execute: a running capability can `query()`/`write()` (or declare a brand-new
key) through Backseater at any time while active, across any of four databases, not just
receive values once at start.

**No centralized Relay.** Every platform's own four databases sync directly with every
other platform's, pairwise, full-mesh (assumed fully connected for now; real comms
topology/partial connectivity explicitly deferred, as before).

**Four separate databases per platform** (all owned by Backseater): **Knowledge** (keyed by
arbitrary entry key, strongly typed, declarable at any time — not just from a mission
graph's `"knowledge"` section at construction); **Mission** (keyed by platform_id, one
`mission_graph` value per platform; a write requires a privilege check, type check, and
structural verify — all three gates at the single Backseater write point — and a successful
write triggers hot-swap); **Capabilities** (keyed by platform_id, self-write-only, gossiped
`CapabilityRegistry` snapshot); **Status** (keyed by platform_id, self-write-only, a
combined status + arbitrary message string, gossiped across the mesh so a remote platform's
health/errors are observable, not just local). This fully absorbs what the four-relay
sketch's "Graph Relay"/"Status Relay"/"Capability Relay" would have been, and folds
"Knowledge Relay" into Backseater itself rather than a separate object.

**Privilege hierarchy**: integer level per platform, 0 = highest, assigned by the simulation
harness at construction (the runtime reassignment rule below has no bootstrap case, so the
very first assignment is a direct harness-side write, not gated by the rule itself). A
platform may write another platform's Mission database, or reassign another platform's
privilege level, only if its own level is strictly higher-privilege than the target's; may
only assign levels less-or-equal to its own; can never modify its own level. Explicit,
deliberate placeholder — not real security, not modeling an adversarial actor, in the same
spirit as the security gap the "very late" entry below already accepted.

**Mesh sync and clock handling**: `World` drives the mesh sync itself rather than a separate
Relay object, since it already holds every platform's Backseater — after dynamics,
`World.step()` calls a pairwise sync between every pair of Backseaters, replacing
`relay.sync(backseaters)`. World owns *who can currently talk to whom* (full mesh for now);
Backseater owns *what a sync actually does* once paired, via a `sync_with()`-style method
that absorbs the old Relay's pull/push/last-write-wins logic across all four databases.
`Clock` (`clock/clock.py`) is repurposed, not dropped or rebuilt from scratch: each pairwise
`sync_with()` handshake estimates a clock offset to that specific peer (replacing the single
global offset the old `sync_clock()` reset to 0.0), and every incoming fact's timestamp is
converted into the receiving platform's own local frame immediately and re-stamped in local
time before storage — there is still no shared/authoritative clock anywhere. Every entry
across all four databases tracks `origin_platform_id` (the platform that held it at its most
recent locally-converted timestamp, transitively) — this is what privilege checks key off
of. All type/privilege/structural checks happen write-side only, once, at the originating
platform's `publish()` call; there is no receipt-side re-verification. Conflict resolution
stays last-write-wins by (locally-converted) timestamp across all four databases — still a
named simplification, not a robust consensus mechanism, per the "very late" entry's existing
discussion of vector clocks/CRDTs as a possible-but-not-near-term upgrade.

**`ParamSpec` downgraded**: carries just a key name plus a declared type (plus plaintext
description), used only for `capabilities()`'s self-description — no longer used for eager
value-resolution. A capability receives keys, not resolved values, and calls
`query()`/`publish()` on Backseater itself whenever it actually needs data, for any of the
four databases; Backseater still type-checks before a query resolves or a publish is
accepted, keeping type-safety centralized rather than left to each Frontseater
implementation.

**Default startup mission**: every platform — including a future LLM/operator "interface"
platform, architecturally just another platform, no special class — starts on a hardcoded
mission graph at init (an idle/loiter loop for an ordinary platform; for the interface, a
single node running all its own capabilities concurrently under an unconditional
self-transition, so it's always active without any new Frontseater autonomy). **Not built
this session, and explicitly deferred to a future step (interview answer):** any
MissionBuilder-equivalent mission-authoring surface. When it is eventually built, the plan is
for it to take the shape of an interactive capability/Frontseater rather than a bespoke
system, per the user's direction — but no incremental add_node/add_edge/verify-style tool
calls exist yet, and none are being added in this pass. For now a platform can only receive
a complete, already-built mission graph via a Mission-database write.

**Hot-swap**: when a Backseater detects its own Mission database entry has changed:
declare/set every knowledge key listed in the new graph's knowledge section, cancel all
currently-running capabilities from the old graph, set the active node to the new graph's
declared start node, and start that node's capabilities.

**Interview answers settled this session** (the three genuinely open architectural
questions, asked directly since the codebase alone couldn't resolve them):
1. *What drives the pairwise mesh sync, given Backseaters currently hold zero references to
   each other and World is the only thing holding all of them?* — World mediates it, calling
   into a pairwise sync method per pair of Backseaters each tick; Backseaters still never
   store direct references to peers, preserving the existing "Backseater doesn't know about
   other platforms" invariant, just as Relay's removal doesn't require breaking it either.
2. *How does a mission graph actually get authored/edited before publishing, given the
   prompt says nothing like MissionBuilder's incremental tool calls?* — Not being built this
   pass; deferred to a future step, at which point it becomes an interactive
   capability/Frontseater rather than a bespoke system.
3. *What happens to `relay/relay.py` and `clock/clock.py`, given the centralized design they
   were built for is now fully superseded?* — Relay is deleted as a standalone class; its
   logic is rolled into Backseater (the `sync_with()`-style method above), with World only
   exposing which platforms are currently connected (faking full connectivity for now, but
   structured so a future comms model could restrict it). Clock is repurposed (per-peer
   offset table via the sync_with() handshake) rather than deleted or rebuilt from scratch.

**Status: decided, not yet implemented.** CLAUDE.md's architecture section has been rewritten
to reflect this design. The existing `relay/relay.py`/`clock/clock.py` and their tests are
still in the tree unmodified as of this entry — removal/adaptation is implementation work for
a future session, done incrementally with tests alongside each change per the project's
standard process, not as part of this planning-only pass. The build order's old step 3.5
(Foreman)/3.75 (Frontend) are dropped; the mesh redesign itself becomes the (not yet done)
step 3, with mission-authoring/LLM-interface work pushed to a new step 4.


## [SUPERSEDED by the 19 Aug 26 peer-to-peer mesh redesign above — not built] Status 17 Aug 26 (very late) — distributed/full-mesh redesign discussion (undecided, deferred)
(Written by Claude)

Design-only discussion (no code changes) proposing a significant departure from 
the just-designed Foreman/Relay/Frontend model (previous entry, same day) — 
not yet decided, explicitly deferred pending Claude Code's codebase-grounded 
analysis. Recorded here so the reasoning isn't lost, not as a locked decision.

**The trigger**: reconsidering whether a centralized `Relay` (already built and 
tested — see the "Relay implemented" entry above) is architecturally honest 
given the project's own "async/blackout-tolerant as first-class, not a 
retrofit" principle. A centralized relay requiring a live path to one object 
is arguably in tension with that principle, similar to ROS1's `roscore` 
dependency vs. ROS2's decentralized DDS transport (imperfect analogy — DDS 
still uses discovery/domains, it's not authority-free — but the spirit holds).

**Proposed alternative, sketched but not committed:**
- Drop centralized `Relay` entirely. Every platform's own `Knowledge` instance 
  syncs pairwise, directly, with every other platform's — full mesh, assumed 
  fully connected for now (real comms topology / partial connectivity 
  explicitly deferred to later, if ever). Conflict resolution stays 
  last-write-wins by timestamp, computed pairwise instead of through one 
  canonical store.
- `Knowledge` gains a third piece of per-key metadata, `origin_platform_id` 
  (alongside existing `value`/`timestamp`) — the platform that held the key 
  at its most recent timestamp update, transitively (true original source 
  through however many hops, not just the last platform that relayed it).
- **Status stays local** to each Backseater (+ sim world viewer) — never 
  gossiped, since it's high-frequency and purely observational. Not part of 
  this redesign's scope.
- **Capabilities become a Knowledge entry** (`<platform>/capabilities`), 
  written by a platform to its own Knowledge at init and propagated via 
  ordinary sync like any other fact — would require `CapabilityRegistry` to 
  become a `KnowledgeEntry` subclass (implementing `describe()`, like 
  `Location` does) to be declarable.
- **Mission graph structure becomes a Knowledge entry** 
  (`<platform>/mission_graph`), deliberately separate from active-node (which 
  stays fast-changing local Backseater state, not gossiped as part of the 
  graph — bundling them was considered and rejected: active-node changes 
  every tick, graph structure rarely, and conflating them under one 
  timestamp risks a stale delayed broadcast clobbering a platform's own more 
  recent self-transition). Assigning a platform a new mission becomes just an 
  ordinary Knowledge write to that key — no special `load_mission` call, no 
  privileged path.
- **This fully absorbs what "Graph Relay" would have been** in an earlier 
  four-relay sketch considered mid-discussion (Knowledge/Status/Capability/
  Graph Relays) — once mission graphs are Knowledge entries, a separate Graph 
  Relay is redundant with Knowledge Relay. That four-relay idea itself 
  replaced an even earlier "one unified Relay with namespaced sub-interfaces" 
  idea and a "one Relay class, four thin wrapper objects" idea — abandoned 
  once it became clear push/pull semantics genuinely differ per data type 
  (Knowledge bidirectional; Status/Capability pull-only), so a shared 
  mechanism doesn't actually fit cleanly. None of these intermediate shapes 
  are being pursued.
- **Every platform — including a new operator/LLM "interface" platform — gets 
  a hardcoded default/fallback mission graph at init.** For an idle UGV/UAV, 
  something like a loiter loop; for the operator, a single node running its 
  own capabilities (add_node, verify, issue_order, etc. — see MissionBuilder 
  below) concurrently, with a literal `True` unconditional self-transition, 
  so it's always "running" without any new Frontseater autonomy — Frontseater 
  still only ever implements what the graph tells it, no decision-making 
  added there. This single mechanism was recognized mid-discussion as solving 
  two separate problems at once: normal idle-platform behavior, and how an 
  operator/LLM interface stays alive and responsive without special-casing.
- **Foreman is dropped entirely.** It was found to add no real value once 
  cross-platform coordination turned out to be 100% Knowledge-mediated — no 
  cross-graph *reasoning* is needed (e.g. no rule spanning two platforms' 
  graphs together), only cross-graph *inspection* (visualizing which node's 
  knowledge-write feeds which other platform's edge-condition read), which is 
  a read-only structural scan belonging in the visualizer, not a backend 
  component.
- **MissionBuilder** replaces Foreman's editing role — the mutable, 
  in-progress graph-editing surface (add/remove node, add/remove edge, 
  add/remove knowledge, verify). Verify is unchanged from the previous 
  entry's design (knowledge-declaration check only, edge-reachability still 
  deferred; runs manually and always automatically before issuing/broadcasting 
  a mission). Once verified, "issuing" a mission is just MissionBuilder 
  writing the graph to the target platform's `mission_graph` Knowledge key.
- **Interface-as-platform**: the operator/LLM is architecturally identical to 
  any UGV/UAV — a generic, unmodified `Backseater`, with a custom Frontseater 
  implementing the operator's own capabilities (add_node, verify, 
  issue_order, query_status, etc.) via the same `CapabilityRegistry`/
  `ParamSpec` self-description machinery every other capability already uses. 
  This means the LLM's tool schema is not a bespoke thing to hand-design — 
  it's the same `capabilities()` query path used everywhere else. Considered 
  and rejected along the way: a dedicated `OperatorBackseater` subclass 
  (unnecessary — the plain generic Backseater already suffices once mission 
  graphs are just Knowledge-stored data like anything else).

**Security — explicitly, deliberately not addressed.** Once "assigning a 
mission" is just an ordinary Knowledge write, there is no privileged path 
left to gate: any platform can write any Knowledge key, including another 
platform's `mission_graph` or its own (e.g. an operator accidentally 
overwriting its own default graph with something broken, with no path back). 
This is being noted and accepted as a known limitation for this thesis's 
scope, in the same category as the already-accepted worker-crash-handling 
gap — not solved here, and real cryptographic/identity-based trust is 
considered out of scope (no adversarial actor is being modeled). A narrower 
allowlist idea (each platform locally checks a gossiped fact's 
`origin_platform_id` against a hardcoded trusted-sources list before 
adopting a new mission graph) was discussed as a cheap partial mitigation but 
not committed to.

**Conflict resolution robustness**: last-write-wins by timestamp remains a 
named simplification, not a solved consensus mechanism — discussed and 
explicitly not pursuing vector clocks or CRDTs as part of this redesign. 
Vector clocks would only detect concurrent conflicts, not resolve them (still 
need a tiebreak rule on top); CRDTs require a conflict-free merge rule 
defined per data type, which arbitrary `Knowledge` values (typed objects, 
whole mission graphs, capability registries) don't have an obvious one for. 
Treated as a possible future upgrade, not a near-term one.

**From an autonomy-research standpoint**: this direction was judged more 
defensible than centralized Relay — a system requiring a live path to a 
central point isn't autonomous under comms denial by definition, and 
real field/military C2 practice already assumes comms will degrade (this 
matches the project's own OPORD/intent-driven framing at the mission-
authoring level; what changes here is purely the knowledge-propagation layer 
underneath it). The trade-off is real added scope (comms topology modeling, 
no single canonical query point, transitive-origin bookkeeping) landing 
before Step 3.5's actual deliverable (a working MissionBuilder/LLM demo) — 
this is a redesign of already-working, tested infrastructure (Relay), not 
free.

**Known open holes, not resolved this discussion:**
1. Hot-swap mechanism undesigned: how a Backseater detects its own 
   `mission_graph` key changed and switches onto the new graph; unclear what 
   happens to in-flight primitives from the old graph on switchover.
2. No execution-time verification: MissionBuilder's verify() only runs at 
   authoring time; nothing gates what actually gets adopted once "issuing" is 
   just a Knowledge write — a malformed graph could hot-swap in unchecked.
3. Knowledge-declaration re-seeding sequencing on hot-swap is undefined (does 
   adopting a new graph automatically re-run its own `"knowledge"` section's 
   declarations against the platform's Knowledge store?).
4. Clock sync's placeholder (previously `Relay.sync_clock()`) has no obvious 
   new owner without a central Relay object — pairwise sync still needs some 
   shared notion of "now" for last-write-wins to mean anything.
5. The dashboard's direct Python references to every Backseater (a 
   single-process simulation convenience) is a simplification that won't 
   hold once this heads toward real distributed hardware (F1Tenth deployment 
   target) — on real hardware, an operator should only see a platform's 
   status if actually in comms range with it.
6. Full-mesh pairwise sync is O(n²) in platform count, vs. the current 
   Relay's O(n) — irrelevant at the current 2-platform scale, worth 
   remembering given how much attention performance already got this project 
   (see the "performance pass" entry above).
7. No guaranteed path back to a platform's own default/safe graph if its 
   `mission_graph` key gets clobbered (self-inflicted or otherwise) — related 
   to the accepted security gap above but broader.

**Status: fully undecided.** Nothing has been implemented. Next step (agreed) 
is a Claude Code review of the actual current codebase (`Knowledge`, 
`Backseater`, `Frontseater`, `Relay`, mission graph shape, `Condition`, 
`CapabilityRegistry`, `World`) to assess real implementation cost against 
what already exists, and to weigh in on the open holes above before any 
commitment is made either way. The existing, working, tested Relay (previous 
entry) remains in place and unmodified until/unless this direction is 
actually chosen.




## Status 17 Aug 26 - Step 3.5 Prompt (Superseded)

Architecture change: the earlier three-part Foreman/Relay/Frontend design 
(from the 17 Aug design session) is being replaced. Foreman was found to add 
no real value once cross-platform coordination turned out to be entirely 
Knowledge-mediated — there's no cross-graph reasoning needed, only cross-graph 
*inspection* (e.g. visualizing which node's knowledge-write feeds which other 
platform's edge-condition read), and that inspection is a read-only, 
structural, per-graph-declarations scan that belongs in the visualizer, not 
in a backend component. So "Foreman" is dropped entirely — no union-graph 
manager exists or is needed.

Step 3.5 is replaced by four Relays plus one Builder:

- **Knowledge Relay** (the existing Relay class, to be renamed) — canonical 
  cross-platform Knowledge store. Bidirectional: pulls each platform's local 
  Knowledge into canonical (last-write-wins by timestamp), then pushes 
  canonical facts newer than a platform's local copy back down. Synced every 
  World tick. This component already exists and is fully implemented/tested — 
  only the name changes as part of this restructure.
- **Status Relay** (new) — cached, timestamped snapshot of each platform's 
  Backseater.status() (active node, blocked flag, per-primitive 
  capability/status/inputs). Pull-only from platforms (Relay never pushes a 
  status back to a platform — a platform doesn't need to be told its own 
  status). Deliberately caches rather than passing through live, so a 
  platform's last-known status remains visible/queryable during a comms 
  blackout — staleness (time since last update) should be inspectable 
  alongside the cached value, not hidden.
- **Capability Relay** (new) — cached, timestamped snapshot of each platform's 
  Backseater.capabilities(). Also pull-only, also periodically repolled (not 
  just fetched once at registration) in case a platform's capability set 
  changes at runtime (e.g. after simulated damage/failure) — but capabilities 
  change far less often than status or knowledge, so this relay's poll cadence 
  should be configurable independently and can be much less frequent.
- **Graph Relay** (new) — holds the authoritative, delegated mission graph per 
  platform once MissionBuilder has pushed it. This is the query-up path (e.g. 
  for a dashboard or LLM asking "what's currently running on ugv1") and the 
  hand-off point that actually delegates a finished graph down to a 
  Backseater. Distinct from MissionBuilder's in-progress/mutable graph — 
  Graph Relay only ever holds verified, delegated graphs.
- **MissionBuilder** (new) — the mutable, in-progress graph-editing surface. 
  Owns one editable graph per platform (not a merged/union structure — just a 
  dict of independent graphs, since no cross-graph reasoning is needed). 
  Exposes add/remove node, add/remove edge, add/remove knowledge as callable 
  methods, meant to be called by both an LLM tool-calling loop and a manual 
  user interface later (same methods, multiple callers — this is the 
  "Frontend" idea from the earlier design, now folded directly into 
  MissionBuilder rather than being a separate wrapping layer). Runs verify() 
  — currently just a knowledge-declaration check (every edge-condition 
  Knowledge key must be declared in the graph's knowledge section) — 
  edge-reachability/dead-node checking is still explicitly deferred. Verify 
  runs manually on demand and always automatically as a gate before 
  issue_order() delegates. On issue_order(), pushes the verified graph to 
  Graph Relay (for delegation/query) and pushes the graph's knowledge 
  declarations (types + initial values) to Knowledge Relay, so platforms 
  receive pre-seeded values before they even start executing.

After your inspection, interview me on how much of the Knowledge Relay's existing pull/push/checksum machinery generalizes across all four relays via a shared base class, versus needing to 
stay type-specific, given push/pull semantics genuinely differ per relay 
(Knowledge is bidirectional; Status/Capability are pull-only; Graph's 
"push" is really a one-time delegation trigger, not a recurring sync). Don't 
force a shared abstraction that doesn't fit the real shape of the data.  Also, some things maybe should be pushed up from the backseater (like status or capability changes... maybe even everything) rather than polled, but that may increase comm bandwidth requirements.  I am not sure status is worth pushing up frequently, so maybe polling 1/sec is enough, and polling capabilities 1/10s or 1/30s.  We'll also eventually need a way for text messages to travel from the frontseater to the user/LLM (for LLM/human replanning purpopses), but none of that machinery is implemented yet.

Interview me for any questions and create live task lists of your research, planning, and then execution precesses.

Please update CLAUDE.md's architecture section and add a dated notes.md entry 
reflecting this restructure (Foreman dropped, four-relay + MissionBuilder 
model adopted, rationale as above) before and after implementation, 
following the standard process.




## Status 17 Aug 26 (performance pass: main-loop busy-spin, MPC hot-path, multiprocessing, iteration cap)
(Written by Claude)

Performance-only session, at the user's request ("the simulator seems to be limited by
CPU compute power and is maxing out one core"). No mission-graph/architecture behavior
changed except the two items below that were deliberately scoped in (Frontseater's
begin_update/finish_update split, and the MPC iteration cap) — everything else is either
a pure optimization (same output, less compute) or a bug fix.

- **Found and fixed the literal cause of "one core maxed out": `main.py`'s loop never
  slept.** It was an unthrottled busy-spin — whenever there was no physics step or
  redraw to do yet (accumulator hasn't reached `DT`, or the sim is paused), it still
  called `time.perf_counter()` in a tight `while True` as fast as the CPU allowed. Fixed
  with a `time.sleep(0.001)` whenever a tick did no work. Independent of every other fix
  below, this alone would have pegged one core permanently regardless of simulation load.
- **Mission-graph layout was being recomputed from scratch every dashboard redraw**,
  despite being static once a mission graph is built into a `Backseater` — 150 iterations
  of an O(n^2) force simulation (`viz/mission_graph_view.py::compute_graph_layout`) on
  every single tick. Now cached by the graph object's identity (`_layout_cache`,
  keyed by `id(mission_graph)`), with the cache holding a strong reference to the graph
  itself alongside its result — caching by `id()` alone risks a garbage-collected graph's
  id being reused by an unrelated dict and silently returning a stale layout, so the
  cache must keep the object alive for as long as it's cached.
- **Dashboard redraw decoupled from physics tick rate**: `main.py` used to call
  `vizualizer.update()` (a full redraw: environment plot, mission graph, both Treeviews)
  after *every* `world.step()` call, including every step of a catch-up burst. Now it
  redraws once per outer-loop iteration instead — a catch-up burst (capped at 5*DT of
  backlog) still stays visually smooth since it's at most a handful of steps.
- **MPC hot-path micro-optimizations** (`world/ground_plane/hardware.py::calculate_dynamics`,
  `world/ground_plane/frontseater.py::compute_controls`, now `mpc.py::solve_mpc`):
  profiling (`cProfile`) showed the whole simulator's cost was almost entirely inside
  `scipy.optimize.minimize`'s cost-function evaluations, not scipy itself — replaced
  scalar `numpy` calls (`np.clip`/`cos`/`sin`/`arctan2`/`hypot`/`tan`) with the `math`
  module (numpy's per-call dispatch overhead dominates over the actual arithmetic for
  scalars at this call volume — tens of thousands of calls per solve), and stopped
  rebuilding the constant `Q`/`R` cost matrices (`np.diag`/`np.eye`) on every one of those
  calls, inlining their quadratic forms as scalar arithmetic instead. Measured 4.6x
  speedup on a single-process baseline (2 platforms, WAIT mission, no avoid regions):
  300 ticks / 30s sim time went from 3.6s wall to 0.85s wall, same resulting trajectory.
- **Multiprocessing added for the MPC solve, at the user's explicit request** after
  confirming (profiling the harder SPLIT mission, which has `avoid` regions) that a
  single platform's obstacle-avoidance solve is genuinely the dominant cost, and that
  it's parallelizable since platforms are already fully independent (per the existing
  architecture — no Backseater/Frontseater ever coordinates with another platform's
  stack). Design, confirmed with the user before implementing:
  - **`Frontseater` ABC gained `begin_update()`/`finish_update()`**, replacing the
    single `update()` as what `World.step()` calls — `begin_update()` starts a
    platform's control computation without blocking, `finish_update()` collects it.
    This is backward compatible: the ABC's default implementation of both reproduces
    exactly what `update()` used to do (`begin_update` calls `compute_controls()`
    synchronously and stashes the result; `finish_update` sends it), and `update()`
    itself still exists, now just composing the two — any Frontseater implementing
    only `compute_controls()` (the pre-existing abstract method) needs no changes.
    `World.step()` now does all platforms' `begin_update()` first, then all
    `finish_update()`s, instead of interleaving update-then-dynamics per platform —
    safe since platforms don't coordinate, so batching doesn't change per-platform
    semantics, only lets their solves overlap.
  - **`BicycleFrontseater` spawns one dedicated, persistent worker process per
    platform** (created once in `__init__`, not per-tick), which holds the MPC's
    warm-start solution and avoid-region list resident for the platform's lifetime —
    the user's explicit choice over a shared pool shipping full solver state every
    tick, since only the current hardware state and target actually change tick to
    tick. `begin_update()` dispatches a `{"state", "target"}` request over a
    `multiprocessing.Queue`; `finish_update()` blocks on the response queue. Naive
    request/response loop, no timeout or crash recovery — matches the project's other
    placeholder comms seams (e.g. Relay's clock sync) ahead of the real comms-boundary
    work planned for build order step 4, at the user's explicit confirmation.
  - The dynamics math itself was factored out into a new
    `world/ground_plane/dynamics.py::bicycle_step()` (plain floats/math, no
    WorldState/Hardware object) so `BicycleHardware.calculate_dynamics` and the new
    `mpc.py::solve_mpc`'s rollout share one implementation instead of the worker
    needing its own hand-copied physics that could drift out of sync.
  - **Required restructuring `main.py`**: all setup code (previously unguarded
    module-level code) moved inside `if __name__ == "__main__":`, alongside the run
    loop. This is a Windows-specific necessity, not a style choice: `multiprocessing`'s
    default "spawn" start method re-imports the launching script as `__main__` in every
    worker process, so unguarded top-level setup would re-run there too — reconstructing
    the whole world (and spawning more worker processes) recursively inside each worker.
    `main.py`'s `finally:` block now also calls `shutdown()` on each platform's
    Frontseater to stop its worker process cleanly on exit.
  - Measured: on the SPLIT mission (2 platforms, with avoid regions — the hard case),
    median per-tick wall time dropped from 54ms to ~32-36ms (parallelizing two
    platforms' solves roughly halves the typical case, short of a clean 2x due to
    IPC/queue overhead), but this alone did **not** fix the worst-case spike during
    turns, since multiprocessing only overlaps platforms against each other — it can't
    shrink one platform's own hardest solve. That took the iteration cap below.
  - **A real pitfall found while benchmarking, not a bug in the shipped code**: an
    early scratch benchmark script wasn't guarded by `if __name__ == "__main__":` and
    had to be killed mid-run over the same Windows spawn-recursion risk described
    above — a reminder that *any* script constructing a `BicycleFrontseater` at module
    level needs the same guard as `main.py`, not just `main.py` itself.
- **MPC iteration cap fixed the actual "slowdown on turns" the user reported.**
  Diagnosed by instrumenting `scipy.optimize.minimize`'s own `result.nit`/`result.nfev`
  from inside the worker process (patching `mpc.minimize` only works if done *inside*
  the child, since Windows' spawn model means a parent-process monkeypatch never
  reaches an already-imported child module) — this showed the worst-case ticks were
  hitting SLSQP's default 100-iteration cap without converging near obstacles, each
  burning 100ms-250ms+, while normal solves converge in a median of 11 iterations.
  Capped `maxiter=20` in `mpc.py::solve_mpc`'s `minimize()` call — legitimate real-time
  MPC practice, since a solve that hasn't converged by then will just be refined again
  next tick from a warm start anyway. Verified apples-to-apples (both excluding the
  one-time worker cold-start tick, which otherwise looks like a giant solve outlier):
  worst-case tick dropped from 250ms to 72ms, with median/p90 essentially unchanged
  (typical solves already converge well under 20 iterations). Iteration-count
  percentiles across both platforms over a 60s SPLIT-mission run: min 1, p25 8,
  median 11, p75 15, p90 20 (capped), with 11.7% of all solves actually hitting the cap
  (the near-obstacle cases the cap targets).
- **New `scripts/` directory** (top-level, not under `tests/` — these are one-off
  profiling tools, not part of the automated suite) holding `mpc_profile.py`, which
  replaces several one-shot diagnostic scripts written and discarded during this
  session: runs the SPLIT mission through the real `World`/`BicycleFrontseater` stack
  and reports both per-tick `World.step()` wall-time percentiles and per-solve
  iteration/eval-count percentiles in one run, excluding the one-time worker
  cold-start tick from the timing stats.
- Tests: `test_mission_graph_view.py` gained the layout-cache regression tests (repeat
  calls return the cached object; the cache holds a strong reference to what it cached);
  `test_world.py`'s `FakeFrontseater` updated to expose `begin_update`/`finish_update`
  instead of `update`, matching what `World.step()` now calls. Also fixed two tests
  broken by the user's own unrelated rename of `mission_wait_ugv2`'s start node
  (`"return_to_start"` -> `"stay_at_start"`): `test_missions.py` and
  `test_relay_mission_integration.py` still referenced the old name. 189 tests total
  (up from 187, before the two broken-then-fixed tests are counted as new). Verified
  with the full suite (slower now, ~36s vs ~8s before multiprocessing, due to real
  `multiprocessing.Process` spawns in the handful of tests that construct a
  `BicycleFrontseater`) and multiple live runs of `main.py` (12-15s each), confirming
  no errors and no leftover worker processes after shutdown (`tasklist` checked clean).

Known follow-up, not done this session: the worker's request/response protocol has no
timeout or crash-recovery, per the user's explicit "naive for now" — revisit alongside
build order step 4's real comms boundary. Also not investigated: whether the MPC's
finite-difference gradient (the dominant per-solve cost, per the iteration/eval-count
data above) could be replaced with an analytic gradient for a much larger constant-factor
speedup — flagged during design discussion as the single biggest remaining lever, but out
of scope for this session's "tuning" ask.


## Status 17 Aug 26 (later night) — Mission Overview dashboard polish
(Written by Claude)

Follow-up feedback pass on the Mission Overview tab added earlier tonight, all at
the user's explicit direction:

- **Graph panel is now titled "Mission Overview" unconditionally** (was "Mission
  graph", and used to only apply to the single-platform view) — it's the same
  panel whether it's showing a platform's mission graph or the platform list, so
  one static title now covers both. The "Show edge labels" checkbox only makes
  sense for the mission-graph half, so `_update_graph_panel_controls()` now
  packs/unpacks it (and the new back button below) based on whether Mission
  Overview or a specific platform is selected, called once per `_refresh()`.
- **`PlatformOverviewViewer` rows are no longer hover-only**: each row always
  shows `platform_id: "active_node_id"` inline, next to a small colored square
  marker (`ax.scatter(..., marker="s")`) that marks exactly where to hover/click —
  the row's tracked "position" for hit-testing is the box's coordinates, not the
  text's, since the box is the visible target. Active-primitives detail stays
  hover-only (`find_platform_label_at`); a new `find_platform_id_at()` reuses the
  same hit-testing for the click-to-select path below.
- **Mission Overview and the Knowledge side panel are now the dashboard's
  defaults on construction** (previously the first platform + Capabilities),
  at the user's explicit request. The knowledge Treeview's columns were also
  reordered to Name/Type/Value (previously Type/Name/Value) with Name and Type
  given fixed narrower widths (90/70px) than Value (220px) so all three fit
  inside the existing fixed-width side panel without resizing on startup.
- **Left-clicking a platform row in Mission Overview now selects that platform**
  (`_on_graph_click`, bound to the graph canvas's `button_press_event`, calls
  `find_platform_id_at` and sets `selected_id` exactly like the dropdown would),
  and a new "⬅ Overview" button (visible only for a single selected platform,
  per the checkbox-visibility logic above) calls `_deselect_platform()` to
  return to the platform list.
- Tests: new `test_platform_overview_view.py` (row count, the always-visible
  inline label including the "(none)" placeholder when a platform has no active
  node, hover-label and click-id hit-testing, box-marker presence), plus
  `test_mission_dashboard.py` updates for the new defaults (a dedicated
  `TestMissionDashboardDefaults` class), the Name/Type/Value column reorder, and
  new coverage for checkbox/back-button visibility and click-to-select. 186
  tests total (up from 171). Verified with a real headless run of `main.py`'s
  actual `wait`-mission wiring, screenshotting the graph panel to confirm the
  box+inline-label rendering matches what was asked for.


## Status 17 Aug 26 (night) — Relay implemented (build order step 3)
(Written by Claude)

Built Relay per the architecture settled in the previous entry, plus the pieces it
turned out to depend on that didn't exist yet.

- **New `clock/clock.py`**: `Clock` wraps wall-clock `time.time()` with an
  adjustable offset (`now()`, `set_offset()`). Lives on `Backseater` (not
  Frontseater/Hardware), at the user's direction — a platform-agnostic layer is
  the right place for something Relay needs to be able to adjust uniformly,
  regardless of platform type.
- **`Knowledge` gained per-key timestamps**: `declare()`/`set()` now take an
  optional `timestamp` (defaulting to wall-clock time if omitted, so every
  existing call site keeps working unchanged), plus a new `timestamp_of(key)`
  accessor. `Backseater` stamps every declare/output-commit with its own
  `clock.now()`. This is what lets Relay compare "when did each platform last
  write this key" for last-write-wins, instead of Relay only being able to guess
  from when it happened to notice a change.
- **New `Knowledge.set_or_declare(key, value, timestamp=None)`**: behaves like
  `set()` for an already-declared key, otherwise auto-declares via `type(value)`.
  This is the deliberately-rare bypass the user asked for so a future
  replanning flow (Frontend/LLM pushing a fact no mission graph anticipated)
  won't be blocked by Knowledge's normal declare-before-use discipline — for a
  pre-planned mission today, every relayed key is still pre-declared by the
  receiving platform's own graph, so this path is essentially unused.
- **New `relay/relay.py`**: `Relay` holds one canonical
  `{key: {value, timestamp, platform_id}}` store. `sync(backseaters)` — called
  by `World.step()` once per tick, after dynamics, at the user's direction
  ("relay should sync after the backseater gets new knowledge... towards the
  end of the tick") — does three passes: a no-op `sync_clock()` per platform
  (resets clock offset to 0.0; the real clock-sync mechanism is still an open
  design question per the previous entry, this just keeps the seam explicit),
  a **pull** merging every platform's Knowledge into canonical (last-write-wins
  by timestamp, gated by a per-platform checksum so an unchanged platform's
  Knowledge is skipped instead of re-scanned every tick — the user's own
  suggestion), then a **push** writing any canonical fact newer than a
  platform's local copy back into that platform's Knowledge via
  `set_or_declare`. Push preserves the canonical timestamp rather than
  re-stamping "now" — re-stamping would make a pushed fact look freshly-written
  on the next sync, letting it out-race the platform that actually originated it
  and oscillate forever.
- **`World` gained an optional `relay` constructor arg**, defaulting to `None`
  (existing single/multi-platform tests untouched); `step()` calls
  `relay.sync(self.backseaters)` at the very end when one is attached.
- **`Backseater.status()`'s per-primitive `"handle"` field was dropped and
  replaced with `"inputs"`** (the primitive's static `field_name -> knowledge_key`
  mapping from the mission graph) — the user wanted the handle gone from both the
  dashboard's capability table and its tooltips, replaced by something more
  informative. No caching needed: `MissionDashboard` resolves each key to its
  live value via `knowledge.get()` at render time, since the user was clear the
  Backseater itself shouldn't own that caching.
- **`missions.py` mission-naming convention changed** to `mission_<set>_<platform_id>`
  at the user's explicit request: the two existing graphs were renamed
  `mission_ugv1`/`mission_ugv2` -> `mission_split_ugv1`/`mission_split_ugv2`
  (content unchanged), and a new pair, `mission_wait_ugv1`/`mission_wait_ugv2`,
  demonstrates the cross-platform relay: ugv1 drives to a destination and writes
  `ugv1/arrived`; ugv2's first node drives to its own starting location (a
  deliberately trivial move, per the user's example), and its only outgoing edge
  is gated purely on `ugv1/arrived == True` — a key ugv2's own graph pre-declares
  but never writes itself, so any value it ever sees for that key can only have
  arrived through Relay. A new exported `MissionSet(IntEnum)` (`SPLIT`/`WAIT`)
  lives in `missions.py`; `main.py` selects the active pair via a
  `MISSION_SETS: dict[MissionSet, tuple]` lookup keyed by a single
  `ACTIVE_MISSION_SET` config constant, and always constructs a `Relay()`
  regardless of which mission set is active, at the user's direction.
- **New "Mission Overview" dashboard tab** (name chosen by the user from three
  options offered): an extra entry in the existing platform dropdown, not a
  separate widget. Selecting it swaps the mission-graph panel for a new
  `viz/platform_overview_view.py::PlatformOverviewViewer` — one row per platform
  id, hover shows that platform's active primitives — and swaps the knowledge
  panel's source from a single platform's `Knowledge` to `Relay.all()`
  (`_refresh_knowledge_tree` now takes any object exposing `.all()`). The
  capability-status table is cleared while this tab is selected, since there's
  no single active platform to describe. All hover tooltips (mission graph
  nodes/edges, and the new platform-overview rows) now start with a
  `"Node: "`/`"Edge: "`/`"Platform: "` title line and a separator, at the user's
  request for "a title and maybe some nicer formatting instead of just the raw
  data."
- Tests: `test_clock.py`, `test_relay.py` (canonical merge, a genuine two-writer
  timestamp conflict independent of dict iteration order, the checksum-skip
  fast path proven via a corrupt-then-resync check, the `sync_clock` no-op, the
  `set_or_declare` bypass), `test_missions.py`, a new
  `test_relay_mission_integration.py` (builds the real `mission_wait_*` graphs
  through actual `Backseater`/`BicycleFrontseater`/`BicycleHardware`/`World`/
  `Relay` instances and confirms ugv2 only transitions off `return_to_start`
  once ugv1 actually arrives, with an explicit assertion that ugv2's own
  Knowledge never appears as an output key for `"ugv1/arrived"` in its own
  graph), plus updates to every test touching `Knowledge.declare/set`'s new
  timestamp param, `status()`'s old `"handle"` field, the renamed
  `mission_ugv1`/`mission_ugv2` dicts, and the mission-graph-view tooltip text
  format. 171 tests total (up from 138). Verified with a headless run of the
  real `main.py` wiring (`ACTIVE_MISSION_SET = WAIT`) confirming `ugv1/arrived`
  lands in `ugv2`'s own Knowledge and in `Relay.all()`, and that ugv2 actually
  transitions to `drive_elsewhere`, purely through Relay.

Left off here — 3.5 (Foreman) and 3.75 (Frontend) are next and untouched.


## [SUPERSEDED by the 19 Aug 26 peer-to-peer mesh redesign above — not built] Status 17 Aug 26 (evening) — Foreman/Relay/Frontend architecture design
(Written by Claude)

Design-only session (no code changes) settling the shape of step 3+ — the 
planner layer sitting above Backseater/Frontseater/Hardware. Following the 
project's "discuss before implementing" pattern, this locks names and 
responsibilities before Claude Code touches anything.

- **Three components, replacing the informal "planner" from earlier build-order 
  notes:**
  - **Foreman** — the mission graph manager. Owns the multi-platform union 
    view (one active node per assigned platform — a concurrent, multi-typed 
    finite-state-machine-like structure, not yet built). Handles LLM/user tool 
    calls that edit the graph (add/remove node, add/remove edge, add/remove 
    knowledge, query graph state + verification status), runs a **verify** 
    step, and delegates validated graphs down to Backseaters.
  - **Relay** — owns the canonical cross-platform Knowledge database (distinct 
    from each Backseater's own per-platform `Knowledge` instance) and handles 
    conflict resolution. This is the concrete realization of the "future 
    planner relaying facts across an async comms boundary" mentioned in the 
    build-order's step 7 — Relay *is* that higher-level asset.
  - **Frontend** — the user + LLM-facing layer. The LLM is one component 
    *within* Frontend, not a peer of Foreman/Relay. Every LLM-callable tool 
    (graph edits, knowledge query/write, mission-state query) is also exposed 
    directly to the user — same underlying methods, multiple callers. A 
    Frontend write acts like any other platform pushing knowledge up to Relay 
    (own identity, e.g. `platform_id = "frontend"`/`"operator"`, same 
    timestamp/conflict-resolution path — no bypass around Backseater-equivalent 
    validation). A dedicated Frontend UI (buttons, a second visualizer window) 
    is deliberately deferred; only shared method signatures need to exist for 
    now, callable from a CLI-driven LLM loop.
  - Names rejected along the way: "MGM"/"CM" (placeholder, disliked), Planner, 
    Overlooker/Overseer/Overwatch (too surveillance/military-coded or awkward).

- **Foreman's verify step**: checks that every Knowledge key referenced in an 
  edge condition is declared in the graph's top-level `"knowledge"` section 
  before delegation — reusing the same declare/type-lock concept `Knowledge` 
  already has, just checked at graph-authoring time instead of runtime. 
  Explicitly **out of scope for now**: edge-reachability / dead-node checking 
  (ambiguous how to handle a legitimate terminal/success node with no outgoing 
  edge — revisit once "mission complete" representation is decided).
  Verify can run **manually** (user/LLM-triggered on demand) and **always 
  automatically on "issue the order"** as a hard gate before delegation — but 
  explicitly *not* on every single tool call, since a graph is expected to be 
  incomplete/invalid mid-edit. The LLM's graph-query tool should return the 
  latest verification result alongside graph state.

- **Type checking is intentionally dual-location, not duplicated by mistake**: 
  Backseater type-checks each knowledge write at the platform boundary 
  (existing, unchanged); Relay also type-checks, since Frontend's writes reach 
  Relay directly rather than passing through a Backseater.

- **Conflict resolution**: last-write-wins by platform-recorded timestamp — 
  explicitly a placeholder ("good enough for a thesis sim," not a robust 
  distributed-systems answer). This requires platforms to share a consistent 
  notion of time, which was already an implicit need for time-based mission 
  conditions, not new scope. **Clock synchronization mechanism is tentatively 
  Relay's job**, exact approach (authoritative clock, offset reporting, etc.) 
  undecided and flagged as a real open question, not solved here.

- Naming decided by elimination/preference, not derived from any technical 
  constraint — flagging in case it needs revisiting once real interfaces 
  exist and a name stops fitting.

**Explicitly deferred / open, not decided this session:**
1. Real conflict-resolution robustness beyond last-write-wins.
2. Clock synchronization mechanism (Relay-owned, unspecified).
3. Edge-reachability / dead-node verification.
4. Frontend's manual UI / second visualizer window.
5. Whether LLM chat happens via CLI or a UI panel (leaning CLI, not finalized).
6. The still-open CPU-core profiling item from the multi-platform test session.

Still nothing implemented for this layer — next session is expected to start 
translating this into an actual Foreman/Relay/Frontend implementation plan, 
likely starting with Foreman (graph manager + verify) since it's fully 
testable without an LLM or Relay in the loop.

## Status 17 Aug 26 (second platform, platform identity)
(Written by Claude)

Narrow structural test, at the user's request: get a second platform (`ugv2`) running independently alongside `ugv1` in `main.py`, in the same `World` instance, to validate that `World`/`Backseater`/the viz layer already support more than one platform — not a coordination test. Cross-platform coordination is explicitly scoped to the future planner relaying facts across an async comms boundary (build order step 7), not something Backseaters do directly, so this added no shared Knowledge and no cross-platform logic.

- **Survey result: almost everything already supported this.** `World.__init__`/`step()`/`get_states()` are already keyed on an `entity_id -> Backseater` dict, iterated generically; `GroundPlaneEnv.step_dynamics_all` iterates a hardware dict the same way; `MissionDashboard`'s platform dropdown is built from `list(world.backseaters.keys())` and `PlanePlotter.render()` already draws one marker per entity in `states.items()`. None of this was aspirational — it was real, tested code with no single-platform assumption baked in. The only actual gap was `main.py` hardcoding exactly one platform's construction.
- **New platform identity chain**, per the user's answer to "where should the id live": `Backseater` owns an optional `platform_id: str` given at construction, and is the only place identity is ever set directly. Its constructor assigns `self.frontseater.platform_id = platform_id` (guarded: only when both `platform_id` and `frontseater` are not `None`, so existing tests using minimal fake Frontseaters without a `hardware` attribute don't break). `Frontseater.platform_id` (`world/base.py`) is a `@property`, not a plain attribute — its setter also assigns `self.hardware.platform_id`, so setting it once on the Frontseater cascades all the way to Hardware without Backseater ever reaching past its Frontseater. `Hardware.platform_id` is a plain `str | None` attribute, defaulting to `None`.
- **New `missions.py`**: `main.py`'s mission graph dicts moved out into their own module at the user's request ("move our test mission dicts into a new file and import them so it is cleaner"). The old unused `test_mission` dict (dead code — never actually passed to a `Backseater`) was dropped; the previously-used `test_mission_2` was renamed `mission_ugv1`; a new, structurally distinct `mission_ugv2` (2-node north/south patrol with its own avoid region, vs. `ugv1`'s 3-node east/west/southeast loop) was added per the user's preference for a genuinely different mission over reusing the same graph shape.
- `main.py` now builds two fully independent stacks (`ugv1_hardware`/`ugv1_frontseater`/`ugv1_knowledge`/`ugv1_backseater`, and the same for `ugv2`, each with its own `platform_id`), sharing only the same `GroundPlaneEnv`/`World` instance. Both start at the origin and diverge toward their own mission's targets — no collision handling, per the user's explicit "pretend they pass through each other for now."
- Tests: new `test_platform_identity.py` (id cascade Backseater -> Frontseater -> Hardware, and that omitting it leaves both untouched) and `test_multi_platform_world.py` (two independent stacks ticked through one real `World`, confirming no Knowledge key leakage and independent movement toward separate targets). 138 tests total (up from 131). Verified with a 50-tick headless run of the actual `main.py` module showing both platforms' `platform_id`s, positions, and Knowledge key sets staying fully separate.
- **Known issue, not investigated this session**: the sim currently runs slowly while only using a single CPU core (observed by the user during this session, not yet profiled) — worth a look before piling on more platforms or a heavier planner, since it may get worse as this project's compute needs grow.

Still left off at step 3 (the minimal single-platform planner) — untouched this session.


## Status 13 Aug 26 (local LLM setup: Ollama + Qwen3.5:4b)
(Written by Claude)

Decision made outside a session (relayed at the start of this one): the mission-commander LLM will run locally via Ollama on `qwen3.5:4b`, CPU-only, native Windows, no cloud API. Rejected cloud alternatives: no sustained free tier on the Claude API for this use case, and Ollama Cloud is a separate paid product not used here. This session only brought the repo's scripts/docs/config up to date with what had already been manually tested (`ollama -v`, `ollama pull qwen3.5:4b`, a manual `ollama run` chat test) — no Python integration or eval work yet.

- **New `llm/ollama/` directory** (moved from a flat `scripts/`) holding `start_ollama.bat`, `stop_ollama.bat`, and `llm_config.yaml` — grouped so a future non-Ollama backend wouldn't require restructuring (`llm/` is the general package, `ollama/` this specific runner).
- Both scripts now echo success/failure based on `%errorlevel%` instead of `start_ollama.bat` echoing unconditionally and `stop_ollama.bat` echoing nothing at all. Caveat documented inline and in `docs/llm_setup.md`: `start /min ollama serve` returns as soon as `cmd` launches the process, not once the server has actually bound its port, so this only catches launch failures (e.g. `ollama.exe` not found), not runtime ones (e.g. port already in use).
- **Config is a plain YAML file (`llm_config.yaml`), not an Ollama Modelfile** — model name, system prompt, `temperature`, `num_predict`, `keep_alive` are decided by the user to be loaded and passed explicitly by future Python code on each `/api/chat` call, rather than baked into a custom model via `ollama create`. This keeps the system prompt tunable without rebuilding a model, which matters since the real mission-commander prompt (tool schema, few-shot examples) is unwritten and will iterate a lot during the eval work. System prompt content itself is a minimal placeholder for now (suppress verbose/markdown-heavy default style) — not the real mission-commander prompt.
- **New `docs/llm_setup.md`**: full setup workflow (install → disable autostart → pull model → start/stop scripts) separated from usage (CLI `ollama run` vs stateless `/api/chat`, and the config file's role). `README.md`'s Ollama section now just points here instead of inlining the steps.
- Explicitly not done this session, deferred to next: the Python `/api/chat` client (stateless — history managed manually, unlike `ollama run`'s CLI), streaming, the agentic tool-call loop, and an eval set validating Qwen3.5:4b (or backups considered: Phi-4-mini, Gemma 4 E4B) against the actual mission-graph tool schema (add/remove node, add/remove edge, add/remove knowledge fact).
- **Found and fixed a real bug in `stop_ollama.bat` during smoke-testing**, not just a schema/docs change: killing `ollama.exe` alone left it respawning within moments, even with the Task Manager auto-start entry set to disabled. Root cause: the installer's tray app (`ollama app.exe`, a separate process from the server) acts as a watchdog and restarts `ollama.exe` whenever it's killed; Task Manager's "disabled" setting only prevents the tray app from launching at the next login, it doesn't quit an already-running instance or stop it from respawning the server. `stop_ollama.bat` now kills `ollama app.exe` before `ollama.exe`, verified via a live smoke test (two dangling `ollama.exe`/`ollama app.exe` processes from an earlier manual chat session, confirmed fully gone with no respawn after the fix).


## Status 13 Aug 26 (knowledge-based edge conditions and capability outputs)
(Written by Claude)

Prerequisite rewrite before step 3 (the planner), at the user's request: mission graph edges no longer transition on primitive status (`{"primitive": idx, "status": "success"}`) — they transition on Knowledge-based conditions instead, and capability outputs are now a first-class, named, typed concept independent of status.

- **Status and Knowledge are now separate concerns.** `status` (`waiting`/`success`/`fail`/`timeout`) is comms-health information between Backseater and Frontseater only, still exposed via `status()` for the dashboard, but it no longer drives edges at all. A capability decides for itself what, if anything, is meaningful to write to Knowledge on a given poll — e.g. `move_to` writes an `arrived` output on every poll (`False` immediately on a new target, `True` once within tolerance); `avoid` writes a `registered` output once its region is live, since "success" never had real meaning for an instantaneous action.
- **New `condition/condition.py`**: edge conditions are a pre-tokenized boolean expression list over Knowledge keys — e.g. `["(", "ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9, ")", "or", "ugv1/target_found", "is", "not", None]` — parsed once by a recursive-descent parser (`parse_condition()`) into a small typed tree (`Comparison`, `IsNone`, `And`, `Or`, `Not`, each with `evaluate(knowledge)`). Chosen over a nested-dict tree (the first schema proposed) at the user's request for something closer to how the expression actually reads; chosen over a plain space-separated string (the user's initial sketch) because the token list is already real Python objects (`True`/`None`/floats), so no custom literal-parsing is needed — only keys/operators/keywords/parens are strings. Neither form uses `eval()` or hands control to the Python interpreter, per the hard requirement to keep this a structured, inspectable format. Caught and fixed a real parser bug during implementation: `_peek()`'s original "end of tokens" sentinel was `None`, indistinguishable from a legitimate literal `None` token in the list (e.g. after `"is" "not"`), which would have silently accepted a truncated condition like `["key", "is", "not"]` as valid; fixed with a private sentinel object distinct from any real token value.
- **Every capability field — input or output — is now always a Knowledge reference**, at the user's request after noticing the original design still had a raw-literal path for some inputs (e.g. `avoid`'s `radius`) alongside the Knowledge-id path for others (e.g. `move_to`'s `target`). There is now exactly one mechanism: a primitive's `"inputs"`/`"outputs"` dicts always map a capability's field name to a Knowledge key, resolved/committed via `Knowledge.get()`/`Knowledge.set()`. This also retired the `is_knowledge_ref` flag entirely, and — after the user asked whether the new output-spec type needed to be different from the existing input-spec type (it didn't: identical fields, identical `describe()`) — unified what would have been two duplicate dataclasses into one `ParamSpec`, used for both `Capability.inputs` and `Capability.outputs`.
- **`Knowledge` gained real type-locking**: `add()` is gone, replaced by `declare(key, type, value)` (locks the key's type, seeds a default) and `set(key, value)` (raises if the key wasn't declared or the value doesn't match its declared type). This is what lets Backseater reject a Frontseater trying to write a wrong-typed output instead of silently corrupting Knowledge. Declarations for planner-supplied constants (e.g. `move_to`'s `tolerance`, `avoid`'s `radius`, named `Location`s) live in a new top-level `"knowledge"` section of the mission graph (`{key: {"type": type, "value": value}}`), seeded into `Knowledge` by the Backseater constructor — this is also where `main.py`'s test missions now declare things like `"ugv1/nav_tolerance"` that used to be inline literals. Graph-time validation of knowledge-key type conflicts (e.g. two bound outputs disagreeing on a key's type) was explicitly scoped out at the user's direction as the planner's job, not the Backseater's; only the runtime `Knowledge.set()` rejection is built and tested here.
- **Fixed a real staleness bug found during implementation**, not just a schema change: `Backseater.update()` used to commit outputs only from `poll_status()`, and skipped straight to the next primitive (`continue`) on the tick a primitive was first started via `start_capability()`. For a *resettable* output like `arrived` (reset to `False` on a new target), this meant the old value could linger in Knowledge for one extra tick after re-actuation — long enough to spuriously satisfy an edge condition and transition immediately, before the fresh value ever landed. Fixed by always polling immediately after starting, in the same tick, so a reset output is recommitted before any edge condition is evaluated against it.
- **`actuate` renamed to `start_capability`** throughout (`Frontseater` ABC, `Backseater`, `BicycleFrontseater`), at the user's request, to read more clearly as "begin this capability task" rather than an ambiguous verb.
- Mission graph primitive keys renamed for clarity alongside the schema change: `"type"` -> `"capability"`, `"params"` -> `"inputs"` (matching the new `"outputs"`), and `Capability.params` -> `Capability.inputs` to match. `MissionGraphViewer`/`MissionDashboard` updated to the new field names and to render token-list conditions (joined with spaces) instead of `primitive=status` labels.
- `BicycleFrontseater`'s `move_to` now takes `tolerance` as a capability input (a Knowledge key, like everything else) instead of a `nav_tolerance` constructor default — the user wanted it planner-controllable per mission, not fixed per platform instance.
- Tests: `test_condition.py` (new — tokenizer/parser/evaluator across every operator, `and`/`or`/`not`/parens, and malformed-token error cases including the end-of-tokens-vs-`None` regression above), plus rewrites of `test_capability.py`, `test_knowledge.py`, `test_backseater_capability_resolution.py` (now includes a full knowledge-based-transition run and a fake multi-output Frontseater proving per-name output commitment and wrong-typed-output rejection), `test_bicycle_frontseater.py`, `test_mission_graph_view.py`, and `test_mission_dashboard.py`. 131 tests total (up from 118). Verified with a 3000-tick headless run of `main.py`'s `test_mission_2` (debug-logged) showing clean repeated transitions around the three-node loop with no blocking.

Still left off at step 3 (the minimal single-platform planner) — untouched this session.


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