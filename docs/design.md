# Design

The ideas behind MTOFR_SIM, stated as math rather than code.  `spec.md` says where each idea lives in the code, and `notes.md` says how it got there.



## 1. Premise: Orders, Not Programs
A **mission-type order** says *what* to achieve and *when to move on*, never *how*.  The commander's intent is data, a mission graph, that any platform able to perform the named capabilities can run.  Everything below follows from keeping three things separate:
- **intent**: the mission, which is plain, serializable, and platform-agnostic;
- **ability**: the capabilities, which are typed and advertised by each platform;
- **embodiment**: the hardware and its dynamics, which are private to each platform.

A mission never names a controller, a frame, or a vehicle type.  A platform never interprets a mission beyond binding it to what it can do.



## 2. A Platform Is a Three-Layer Stack
Each platform $p$ is a composition $B_p \circ F_p \circ H_p$, layered as on a real robot.

**Hardware $H$: the plant.**  It has a state $x_t$ and its own dynamics:
$$x_{t+\Delta t} = f(x_t, u_t, \Delta t;\ \mathcal{E}).$$
Its only output is a sensed state $y_t = s(x_t)$, where $s$ is the identity for a perfect sensor.  The environment $\mathcal{E}$ is *passive*: it only answers queries (traversability $\mathcal{E}.\mathrm{blocked}(x, y)$ and the speed multiplier $\mathcal{E}.\mu(x, y)$), and it never steps.  All change in the world is some platform's $f$.

**Frontseater $F$: the policy.**  It maps the active capability requests and $y_t$ to a control $u_t$.  It is the only bespoke layer per platform.  It sees $H$ only through $y$ (`read_state`) and $u$ (`send_controls`).

**Backseater $B$: the mission automaton.**  It holds the mission, decides the active node, and owns the platform's databases, clock, identity, and privilege.  It never touches $x$.

Each layer depends only on the one below it, through a narrow interface.  The package structure enforces the same discipline: each layer imports only from the layers more general than itself.



## 3. Knowledge: Typed, Timestamped State
A platform's Knowledge is a finite map
$$K : \mathsf{Key} \to (\tau, v, t, o)$$
- $\tau$ is a **locked type**, fixed at declaration;
- $v$ is the value, with $v : \tau$ checked on every write;
- $t$ is the write time in this platform's local clock;
- $o$ is the origin platform.

Every key must be declared before use.  The type lock is what lets a Backseater reject a wrong-typed write from its own Frontseater.

Keys are namespaced, as in $k = \mathit{ns}/\mathit{name}$.  A namespace that equals a platform id marks **ownership**: `ugv1/pose` is ugv1's fact about itself.  Ownership is a convention with one piece of semantics, described in §6.

Missions bind capabilities to keys, never to literals.  So every quantity a mission acts on is in $K$, where it can be inspected, synced, and edited live.



## 4. A Mission Is a Guarded Automaton
A mission is a tuple
$$M = (D,\ N,\ E,\ n_0).$$
- $D : \mathsf{Key} \to (\tau, v_0)$ declares each key's type and default.
- $N$ is a set of nodes.  Each node $n$ is a set of **capability requests** $r = (c, \beta_{in}, \beta_{out})$.  Here $c$ names a capability, and the bindings $\beta : \mathsf{Field} \to \mathsf{Key}$ map its fields to Knowledge keys.
- $E(n) = [(\varphi_1, n_1), \ldots, (\varphi_m, n_m)]$ is an **ordered** list of guarded edges.  Each guard $\varphi_i$ is a boolean formula over $K$, with this grammar:
  $$\varphi ::= k \bowtie \ell \mid k\ \mathtt{is}\ [\mathtt{not}]\ \mathtt{None} \mid \neg\varphi \mid \varphi \wedge \varphi \mid \varphi \vee \varphi,\qquad \bowtie\ \in \{=, \neq, <, \le, >, \ge\}$$
- $n_0$ is the start node.

**Transition.**  Exactly one node is active, and all of its requests run concurrently.  Each tick:
$$n' = \begin{cases} n_i & \text{for the first } i \text{ with } \varphi_i(K) = \top \\ n & \text{if no guard holds.} \end{cases}$$
Edge order is priority, so the automaton is deterministic.

**Capabilities never drive transitions.**  Guards read only $K$, and capabilities affect the automaton only by writing $K$.  So the mission's control flow is a pure function of Knowledge.  It can be read, validated, and edited without knowing any capability's internals.  "Done" is whatever a capability chooses to write, such as `arrived := true`.

**Admissibility.**  A mission $M$ is admissible on platform $p$ when three conditions hold:
1. **Closure:** every key a guard or binding mentions is declared, $\mathrm{keys}(\varphi) \cup \mathrm{img}(\beta) \subseteq \mathrm{dom}(D)$.
2. **Bindability:** every requested $c$ is advertised by $p$, every field is bound exactly once, and the types match exactly, $D(\beta(f)).\tau = \tau_c(f)$.
3. **Typed guards:** every literal $\ell$ has the type of the key it is compared against.

These checks are done **once, at the writer**, before the mission is accepted.  They are repeated at bind time only against the live types of $K$, which may have changed.  Edge reachability is deliberately not checked, because a terminal node legitimately has no edges.



## 5. Capabilities: Typed Transducers with a Lifecycle
A capability $c$ declares typed input and output fields.  A running request is an instance with the lifecycle `start` → `tick`* → `stop`.  Each tick it reads its bound inputs live, writes its bound outputs, and may set an **actuation intent** on its Frontseater (e.g. a navigation target).  The controller then turns that intent into $u$.

When the active node changes, the Frontseater diffs the request sets by name:
- a request that is gone or changed is stopped;
- a request that is new or changed is started fresh;
- an equal request keeps running across the node change.

So a mission can share a long-running behavior, such as a pose sensor, between nodes without restarting it.

Reads are live, so retargeting a key takes effect on the next tick.  Writes to unbound outputs are no-ops, so a mission takes only the outputs it cares about.



## 6. Adopting a New Mission
When a new mission $M' = (D', \ldots)$ arrives, the platform stops the old requests and initializes $K$ from $D'$, then activates $n_0'$ in the same tick.  Let $P$ be the known peers (excluding self).  For each $k \in \mathrm{dom}(D')$:
$$K(k) \leftarrow \begin{cases} K(k) & \mathrm{ns}(k) \in P,\ k \in \mathrm{dom}(K) & \text{(a peer's fact: keep the live value)} \\ (\tau, v_0, 0, p) & \mathrm{ns}(k) \in P,\ k \notin \mathrm{dom}(K) & \text{(placeholder until the real value arrives)} \\ (\tau, v_0, \mathrm{now}, p) & \text{otherwise} & \text{(reset)} \end{cases}$$

**Principle.**  A mission may reset its own platform's facts and shared facts, never another platform's facts.  Run flags (`ugv1/arrived` on ugv1) reset, so the new mission starts clean.  A follower's mission that reads `ugv1/pose` declares the key, so it is well-typed and admissible, but it never overwrites ugv1's pose.  The placeholder's timestamp $0$ is the bottom element of the merge order (§7), so it can never spread across the mesh.



## 7. Distribution: Replicas Merged by Last-Write-Wins
Each platform holds its own replica of three maps:
- **Knowledge** (§3);
- **Mission**: platform → mission graph;
- **Platform**: platform → (privilege, status, capabilities), which is how peers learn each other's abilities.

There is no central store.  Syncing two replicas merges them key by key:
$$\mathrm{merge}(a, b)(k) = \arg\max_{e \in \{a(k),\, b(k)\}} \ \hat t(e),$$
where $\hat t$ is the timestamp converted into the local clock frame.

- **The merge is a join** on entries ordered by timestamp.  It is commutative, associative, and idempotent, so sync is symmetric (either side may start it) and order-independent, and repeating it changes nothing.  Under full connectivity, replicas converge once writes stop.
- **Timestamps are never re-stamped on receipt.**  Re-stamping would make a relayed fact look newer than its origin, and two platforms could then out-race each other forever.  The origin $o$ is carried along with the value.
- **There is no shared clock.**  Each platform has $t_{\mathrm{local}} = t_{\mathrm{wall}} + \delta_p$, and it keeps a per-peer offset $\hat\delta_q$ estimated at each sync handshake, so that $\hat t = t_q + \hat\delta_q$.
- **Data has an age.**  A value's age $\mathrm{now} - \hat t$ includes sync latency.  Consumers that need fresh data reason about that age explicitly (§10) rather than assuming fresh values.
- **Known simplifications.**  Last-write-wins is not consensus: concurrent writes resolve by clock, not by intent.  Sync is $O(n^2)$ in the number of platforms.



## 8. Privilege: Who May Reassign Whom
Privilege is an integer level, where lower is more privileged and 0 is reserved.  A write of platform $q$'s mission by writer $w$ is permitted iff
$$w = q \quad\text{or}\quad \mathrm{level}(w) < \mathrm{level}(q).$$
The strict inequality means peers of equal rank cannot retask each other.  The check runs write-side, against the writer's own replica of the Platform map.  Receivers trust synced entries, following the same "check once, at the writer" rule as admissibility (§4).

A mission push is therefore just a write to the target's entry *in the writer's own replica*.  Sync delivers it, and the target's adoption (§6) does the rest.  An operator console is an ordinary platform with a high privilege level.



## 9. Time and the Tick
Simulation advances in steps of $\Delta t$.  Each step runs in this order:
1. **Decide.**  Every $B_p$ evaluates its guards and hands off requests.
2. **Act.**  Every $F_p$ ticks its capabilities and dispatches its controller.  The controllers' solves overlap across platforms.
3. **Collect.**  Every $F_p$ collects its controls and sends them to $H_p$.
4. **Physics.**  Every $H_p$ steps $f$ against $\mathcal{E}$.
5. **Sync.**  Replicas merge with any peer not synced within the sync interval.

Faults are isolated per platform: a platform that faults skips its own decisions for the rest of the step, but its physics still runs (a vehicle keeps coasting).



## 10. Ground Vehicles: Bicycle Model and MPC
**Dynamics.**  A kinematic bicycle with wheelbase $L$, speed $v$, and steering angle $\delta$, both clamped to their limits:
$$\dot x = v\cos\theta,\qquad \dot y = v\sin\theta,\qquad \dot\theta = \frac{v}{L}\tan\delta.$$
The terrain scales the speed limit by $\mu(x, y)$ and rejects steps into blocked cells.  The controller itself knows nothing about terrain.

**Control.**  Receding-horizon MPC over $N$ steps of $\Delta t_{\mathrm{nav}}$, warm-started from the previous solution shifted by one step:
$$\min_{a_{0..N-1}} \sum_{k=1}^{N} \ell(s_k, a_k) \quad \text{s.t.}\quad s_{k+1} = f_{\mathrm{bicycle}}(s_k, a_k),\quad a_k \in [v_{\min}, v_{\max}] \times [\delta_{\min}, \delta_{\max}].$$
The stage cost $\ell$ depends on the kind of intent:
- **Reach a point** $g$: a heading-to-bearing term, effort, and distance:
  $$\ell = w_h\, \angle(\theta, \mathrm{bearing}(s, g))^2 + a^\top R a + \|s_{xy} - g\|^2.$$
- **Track a pose** $s^\star$, as in the convoy paper:
  $$\ell = (s - s^\star)^\top W_s (s - s^\star) + a^\top W_a a,\qquad W_s = \mathrm{diag}(1, 1, 0.1),\quad W_a = \mathrm{diag}(0.2, 0.7).$$
  The heading error is wrapped.  Equal $x$ and $y$ weights make the world frame equivalent to the paper's follower frame.

Avoid-regions add soft penalties to both modes.  The kind of intent is carried by the intent's type: a location is reached, and a pose is tracked.



## 11. Convoy Following
This is the predecessor-follower topology of Cometto et al.  Each follower's target is the vehicle ahead of it, and the information it needs arrives through the Knowledge mesh.  That mesh stands in for vehicle-to-vehicle radio, so there is no global frame requirement beyond the shared world frame of `Pose`.

**Offhooked target** (a virtual trailer link).  For a leader pose $(x_l, y_l, \theta_l)$, a follower heading $\theta_f$, and a following distance $d$, the target is
$$p^\star = \begin{bmatrix}x_l\\ y_l\end{bmatrix} - \frac d2\begin{bmatrix}\cos\theta_l\\ \sin\theta_l\end{bmatrix} - \frac d2\begin{bmatrix}\cos\theta_f\\ \sin\theta_f\end{bmatrix},\qquad \theta^\star = \theta_f.$$
Setting the target heading to the follower's own means the controller never anticipates the leader's turn.  In a steady turn, this keeps the follower on the leader's path, so each follower inherits its leader's obstacle-free route.

**Waiting.**  If the target is not ahead of the follower, $(p^\star - p_f)\cdot(\cos\theta_f, \sin\theta_f) \le 0$, the follower commands zero motion rather than reversing.

**Prediction instead of estimation.**  The paper's EKF fused lidar and radio range because the leader's pose was unobserved.  Here the pose is known, but it is stale by its age $\alpha$, up to the sync interval.  So only the EKF's *predict* step remains:
1. From two successive samples $(P_{i-1}, t_{i-1})$ and $(P_i, t_i)$, estimate the speed along the heading and the yaw rate:
   $$\hat v = \frac{(p_i - p_{i-1})\cdot(\cos\theta_{i-1}, \sin\theta_{i-1})}{t_i - t_{i-1}},\qquad \hat\omega = \frac{\mathrm{wrap}(\theta_i - \theta_{i-1})}{t_i - t_{i-1}}.$$
2. Extrapolate by $\alpha$ along a constant-turn arc of radius $r = \hat v/\hat\omega$ (a straight line when $\hat\omega \approx 0$):
   $$\theta' = \theta + \hat\omega\alpha,\qquad x' = x + r(\sin\theta' - \sin\theta),\qquad y' = y - r(\cos\theta' - \cos\theta).$$

A pose older than a timeout stops the follower.  That is the safe response to a lost link, and it also covers the placeholder of §6, whose age is effectively infinite.



## 12. Principles, Summarized
1. **Intent is data.**  Missions are plain, serializable graphs over typed keys, and they never contain code or literals bound to capabilities.
2. **Coupling only through Knowledge.**  Capabilities write facts, and guards read facts, so control flow never depends on a capability's internals.
3. **Check once, at the writer.**  Type, structure, bindability, and privilege are verified where a write originates.  Receivers trust what they are sent.
4. **Every fact has an owner, a type, and an age.**  Ownership limits who may reset a fact (§6), the type is locked, and the age is explicit (§7, §11).
5. **No global anything.**  There is no shared clock, no central store, and no global frame beyond the environment's own.  Replicas converge by merging.
6. **A passive world.**  Only platforms change state, and the environment only answers queries.
7. **Narrow layers.**  Each layer sees one interface below it.  The only bespoke part of a new platform is its Frontseater.
8. **Keep it simple, but effective.**  Each mechanism is the smallest one that serves the experiment, such as last-write-wins over consensus and prediction over full estimation.  Each simplification is named, so it can be revisited.
