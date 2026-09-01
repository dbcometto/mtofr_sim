"""Defines a backseater"""
import hashlib

from mtofr.condition.condition import parse_condition
from mtofr.clock.clock import Clock
from mtofr.database import (
    MissionDatabase,
    PlatformDatabase,
    PlatformRecord,
    PlatformStatus,
    verify_mission_structure,
)


def _reconcile_database(destination_database, source_database, source_platform_id: str, destination_clock: Clock) -> None:
    """Pulls every entry of `source_database` into `destination_database` that is
    newer (once its timestamp is converted into `destination_clock`'s local frame)
    than what's already stored there — last-write-wins, generalized across
    Knowledge/Mission/Platform, the three databases a pairwise sync_with()
    reconciles. Works one direction at a time; sync_with() calls this twice per
    database (pull, then push) to reconcile bidirectionally. Preserves the
    converted timestamp rather than re-stamping "now": re-stamping would make a
    pulled fact look freshly-written on the next sync, letting it out-race the
    platform that actually originated it and oscillate forever."""
    for key, value in source_database.all().items():
        source_timestamp = source_database.timestamp_of(key)
        converted_timestamp = destination_clock.to_local(source_platform_id, source_timestamp)
        local_timestamp = destination_database.timestamp_of(key)
        if local_timestamp is not None and local_timestamp >= converted_timestamp:
            continue   # local copy is at least as fresh as the peer's — nothing to pull
        origin_platform_id = source_database.origin_of(key)
        if hasattr(destination_database, "set_or_declare"):
            destination_database.set_or_declare(key, value, timestamp=converted_timestamp, origin_platform_id=origin_platform_id)
        else:
            # PlatformKeyedDatabase.declare() is an unconditional upsert, unlike KnowledgeDatabase's
            # declare()/set() split — reused here for both a brand-new and an already-known entry.
            destination_database.declare(key, value, timestamp=converted_timestamp, origin_platform_id=origin_platform_id)


class Backseater:
    """Platform-agnostic relay between a mission graph and a Frontseater.

    Mission graph:
      {"knowledge": {key: {"type": type, "value": value}, ...},
       "nodes": {id: {"primitives": {name: {"capability", "inputs", "outputs"}}}},
       "edges": {id: [{"condition": [token, ...], "to": next_id}, ...]},
       "start": id}
    `condition` is a pre-tokenized boolean expression over Knowledge keys (see
    mtofr.condition.condition), parsed once at construction. Edges are checked in
    order; the first edge whose condition evaluates true against current Knowledge
    is taken. Primitive `status` (waiting/success/fail/timeout) is comms-health
    information between Backseater and Frontseater only — it never drives edges;
    a capability decides for itself what, if anything, to write to Knowledge.
    Backseater never touches WorldState directly.
    """

    def __init__(self, frontseater, knowledge_database, mission_graph=None, platform_id: str = None,
                 privilege_level: int = 1, clock: Clock = None, sync_interval: float = 1.0, debug=False):
        self.frontseater = frontseater
        self.frontseater.backseater = self  # cascades down, mirrors the platform_id cascade below
        self.knowledge_database = knowledge_database
        self.mission_graph = mission_graph or {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        self.clock = clock or Clock()
        self.debug = debug
        self.privilege_level = privilege_level
        self.sync_interval = sync_interval
        self._last_sync_time = {}          # peer platform_id -> local clock time this platform last synced with it
        self._last_snapshot_checksum = {}  # peer platform_id -> (my_checksum, their_checksum) as of that last sync

        # Peer-to-peer mesh redesign (increment 1): platform_id-keyed siblings to
        # Knowledge. Not yet wired into mission-change handling or mesh sync — those are
        # later increments. Mission writes from another platform are gated via
        # write_mission() (increment 2); PlatformDatabase is what that gate
        # resolves both sides' privilege levels from.
        self.mission_database = MissionDatabase()
        self.platform_database = PlatformDatabase()

        self.platform_id = platform_id
        if self.platform_id is not None and self.frontseater is not None:
            self.frontseater.platform_id = platform_id  # cascades down to frontseater.hardware

        if self.platform_id is not None:
            self.platform_database.declare(
                self.platform_id,
                PlatformRecord(privilege_level=self.privilege_level, status=PlatformStatus("idle")),
                timestamp=self.clock.now(),
                origin_platform_id=self.platform_id,
            )

        self._declare_knowledge_keys(self.mission_graph)
        self._parsed_conditions = self._parse_edge_conditions(self.mission_graph)

        self.active_node_id = self.mission_graph.get("start")
        self._handles = {}      # primitive name -> handle
        self._statuses = {}     # primitive name -> last known status
        self._blocked = False

    def capabilities(self):
        """Relays the Frontseater's advertised CapabilityRegistry — the query path a planner
        uses to discover what this backseater's platform can do, instead of assuming it."""
        return self.frontseater.capabilities()

    def status(self) -> dict:
        """Read-only snapshot of mission progress — the query path a visualization tool
        uses instead of reaching into private state. Primitive statuses default to
        "pending" for primitives in the active node that haven't been actuated yet."""
        node = self.mission_graph["nodes"].get(self.active_node_id, {}) if self.active_node_id else {}
        primitives = node.get("primitives", {})
        return {
            "active_node_id": self.active_node_id,
            "blocked": self._blocked,
            "primitives": {
                name: {
                    "capability": primitive["capability"],
                    "status": self._statuses.get(name, "pending"),
                    "inputs": primitive.get("inputs", {}),
                }
                for name, primitive in primitives.items()
            },
        }

    def write_mission(self, mission_graph: dict, writer_platform_id: str, timestamp: float = None) -> None:
        """The single gated write point for this platform's Mission database entry.
        Skips the privilege check entirely when `writer_platform_id` is this platform's
        own id (self-writes are always allowed); otherwise requires the writer's
        privilege level, resolved from this platform's own PlatformDatabase, to be
        strictly higher-privilege (lower number) than this platform's own. Raises
        PermissionError if the writer is unprivileged or unknown, ValueError on a type
        mismatch, and MissionStructuralError if an edge condition references an
        undeclared knowledge key. Type check runs before structural verify since the
        latter assumes `mission_graph` is already a dict. No mission-change handling
        yet — a successful write just lands.
        """
        if writer_platform_id != self.platform_id:
            writer_record = self.platform_database.get(writer_platform_id) if writer_platform_id in self.platform_database.all() else None
            if writer_record is None:
                raise PermissionError(
                    f"Cannot verify privilege of unknown platform '{writer_platform_id}' — rejecting Mission write"
                )
            own_record = self.platform_database.get(self.platform_id)
            if not writer_record.privilege_level < own_record.privilege_level:
                raise PermissionError(
                    f"Platform '{writer_platform_id}' (privilege {writer_record.privilege_level}) may not write "
                    f"platform '{self.platform_id}'s Mission entry (privilege {own_record.privilege_level})"
                )

        if not isinstance(mission_graph, self.mission_database.value_type):
            raise ValueError(
                f"{type(self.mission_database).__name__} expected "
                f"{self.mission_database.value_type.__name__}, got {type(mission_graph).__name__}"
            )

        verify_mission_structure(mission_graph)

        write_timestamp = timestamp if timestamp is not None else self.clock.now()
        if self.platform_id in self.mission_database.all():
            self.mission_database.set(self.platform_id, mission_graph, timestamp=write_timestamp, origin_platform_id=writer_platform_id)
        else:
            self.mission_database.declare(self.platform_id, mission_graph, timestamp=write_timestamp, origin_platform_id=writer_platform_id)

    def _snapshot_checksum(self) -> str:
        """Hashes every (database, key, value, timestamp) entry across all three of this
        platform's databases — the cheap "did anything change since the last sync with
        this peer" check sync_with() uses to skip a full reconcile when nothing did.
        Database name prefixes each item since Knowledge keys and platform_ids share the
        same string namespace and could otherwise collide."""
        items = []
        for database_name in ("knowledge", "mission", "platform"):
            database = self._database_for(database_name)
            items.extend(
                (database_name, key, repr(value), database.timestamp_of(key))
                for key, value in database.all().items()
            )
        return hashlib.sha256(repr(sorted(items, key=lambda item: (item[0], item[1]))).encode()).hexdigest()

    def _handshake_clock(self, peer: "Backseater") -> None:
        """Estimates the offset from this platform's clock frame to `peer`'s, and vice
        versa, and records both — each side computed independently from its own read of
        the other's clock. No network delay is simulated yet (deferred to build-order
        step 5), so this is exact rather than a real round-trip estimate."""
        self.clock.set_peer_offset(peer.platform_id, peer.clock.now() - self.clock.now())
        peer.clock.set_peer_offset(self.platform_id, self.clock.now() - peer.clock.now())

    def sync_with(self, peer: "Backseater") -> None:
        """Reconciles this platform's three databases against `peer`'s, bidirectionally,
        last-write-wins by (locally-converted) timestamp — a named simplification, not a
        robust consensus mechanism. Symmetric: calling it from either side of a pair
        produces the same end state. Idempotent: calling it twice in a row (or from both
        sides in the same tick) converges to the same state the second time as a no-op,
        which is what lets both platforms in a pair independently decide to initiate a
        sync without any lock or tie-break between them. Bypasses write_mission()'s
        privilege/type/structural gate for the Mission database — and self-write-only for
        Platform — since CLAUDE.md's architecture specifies all such checks happen
        write-side only, once, at the originating platform's publish() call, with no
        receipt-side re-verification; a Mission or Platform entry that is "about" this
        platform itself is reconciled the same as any other, no self-record special-casing.
        """
        self_checksum = self._snapshot_checksum()
        peer_checksum = peer._snapshot_checksum()
        if self._last_snapshot_checksum.get(peer.platform_id) == (self_checksum, peer_checksum):
            self._last_sync_time[peer.platform_id] = self.clock.now()
            peer._last_sync_time[self.platform_id] = peer.clock.now()
            return   # nothing changed on either side since the last sync with this peer

        self._handshake_clock(peer)

        for database_name in ("knowledge", "mission", "platform"):
            self_database = self._database_for(database_name)
            peer_database = peer._database_for(database_name)
            _reconcile_database(self_database, peer_database, peer.platform_id, self.clock)
            _reconcile_database(peer_database, self_database, self.platform_id, peer.clock)

        self._last_sync_time[peer.platform_id] = self.clock.now()
        peer._last_sync_time[self.platform_id] = peer.clock.now()
        self._last_snapshot_checksum[peer.platform_id] = (self._snapshot_checksum(), peer._snapshot_checksum())

        if self.debug:
            print(f"[Backseater] Synced with '{peer.platform_id}'")

    def sync_with_stale_peers(self, peers: list["Backseater"]) -> None:
        """Calls sync_with() against every peer in `peers` whose last sync (if any) is
        older than this platform's sync_interval — the staleness gate a future World
        would drive per tick, called directly by tests for now since World integration is
        a later increment. Peers within the interval are skipped entirely, not even
        checksummed."""
        now = self.clock.now()
        for peer in peers:
            last_sync_time = self._last_sync_time.get(peer.platform_id)
            if last_sync_time is None or now - last_sync_time > self.sync_interval:
                self.sync_with(peer)

    def _declare_knowledge_keys(self, mission_graph: dict) -> None:
        """Declares/resets every knowledge key listed in `mission_graph`'s "knowledge"
        section to its declared type/default — shared by construction and mission-change handling."""
        for key, declaration in mission_graph.get("knowledge", {}).items():
            self.knowledge_database.declare(key, declaration["type"], declaration["value"], timestamp=self.clock.now())

    def _parse_edge_conditions(self, mission_graph: dict) -> dict:
        """Parses every edge condition in `mission_graph` once, keyed by source node id —
        shared by construction and mission-change handling."""
        return {
            node_id: [(parse_condition(edge["condition"]), edge["to"]) for edge in edges]
            for node_id, edges in mission_graph.get("edges", {}).items()
        }

    def _activate_node(self, node_id):
        self.active_node_id = node_id
        self._handles = {}
        self._statuses = {}

    def _detect_mission_change(self) -> None:
        """Detects whether this platform's own Mission database entry is a different
        object than the mission graph currently driving update() — the trigger point
        CLAUDE.md specifies ("when a Backseater detects its own Mission database entry
        has changed"), rather than handling the mission change synchronously inside
        write_mission(), so a future mesh sync that writes mission_database directly
        (increment 5) triggers the mission change the same way a local write_mission()
        call does. No-ops until this platform's first Mission write lands, leaving the
        constructor's initial mission graph (which never touches mission_database)
        untouched.
        """
        if self.platform_id is None or self.platform_id not in self.mission_database.all():
            return

        new_mission_graph = self.mission_database.get(self.platform_id)
        if new_mission_graph is self.mission_graph:
            return

        for handle in self._handles.values():
            self.frontseater.cancel(handle)

        self._declare_knowledge_keys(new_mission_graph)

        self.mission_graph = new_mission_graph
        self._parsed_conditions = self._parse_edge_conditions(new_mission_graph)
        self._blocked = False
        self._activate_node(new_mission_graph.get("start"))

        if self.debug:
            print(f"[Backseater] Mission changed — active node now '{self.active_node_id}'")

    def _database_for(self, database_name: str):
        """Maps a database_name string to the matching database instance — the dispatch
        point shared by query()/publish()."""
        databases = {
            "knowledge": self.knowledge_database,
            "mission": self.mission_database,
            "platform": self.platform_database,
        }
        database = databases.get(database_name)
        if database is None:
            raise ValueError(f"Unknown database '{database_name}' — expected one of {sorted(databases)}")
        return database

    def query(self, database_name: str, key):
        """Reads `key` from one of this platform's three databases (\"knowledge\"/\"mission\"/
        \"platform\") — the path a running capability uses to read live data at any time,
        rather than only receiving resolved values once at start."""
        return self._database_for(database_name).get(key)

    def publish(self, database_name: str, key, value, timestamp: float = None) -> None:
        """Writes `value` to `key` in one of this platform's three databases — the path a
        running capability uses to write data at any time. A "mission" publish always
        targets this platform's own entry and goes through the gated write_mission() (key
        is ignored, since Mission has exactly one entry per platform); "knowledge"/"platform"
        publishes go straight to that database's own type-checked set(), which raises if
        `key` wasn't already declared or `value` doesn't match its declared type."""
        if database_name == "mission":
            self.write_mission(value, writer_platform_id=self.platform_id, timestamp=timestamp)
            return
        database = self._database_for(database_name)
        database.set(key, value, timestamp=timestamp if timestamp is not None else self.clock.now(),
                      origin_platform_id=self.platform_id)

    def _check_binding_types(self, capability, primitive: dict) -> None:
        """Verifies that every Knowledge key a primitive binds to one of `capability`'s
        declared input/output fields is itself declared with that field's exact type —
        run once, at bind time, before a capability is started. Backseater now hands a
        capability the key rather than a resolved value, so this is what keeps that
        type check centralized instead of leaving it to each Frontseater implementation."""
        bound_inputs = primitive.get("inputs", {})
        for spec in capability.inputs:
            key = bound_inputs.get(spec.name)
            if key is None:
                raise ValueError(f"Capability '{capability.ipl_type}' missing required input '{spec.name}'")
            declared_type = self.knowledge_database.type_of(key)
            if declared_type is None:
                raise KeyError(f"Knowledge key '{key}' bound to input '{spec.name}' was not declared")
            if declared_type != spec.type:
                raise ValueError(
                    f"Capability '{capability.ipl_type}' input '{spec.name}' expects {spec.type.__name__}, "
                    f"but bound Knowledge key '{key}' is declared {declared_type.__name__}"
                )

        bound_outputs = primitive.get("outputs", {})
        outputs_by_name = {spec.name: spec for spec in capability.outputs}
        for output_name, key in bound_outputs.items():
            spec = outputs_by_name.get(output_name)
            if spec is None:
                raise ValueError(f"Capability '{capability.ipl_type}' has no declared output '{output_name}'")
            declared_type = self.knowledge_database.type_of(key)
            if declared_type is None:
                raise KeyError(f"Knowledge key '{key}' bound to output '{output_name}' was not declared")
            if declared_type != spec.type:
                raise ValueError(
                    f"Capability '{capability.ipl_type}' output '{output_name}' expects {spec.type.__name__}, "
                    f"but bound Knowledge key '{key}' is declared {declared_type.__name__}"
                )

    def declare_knowledge_key(self, key: str, entry_type: type, value, timestamp: float = None) -> None:
        """Declares a brand-new Knowledge key mid-execution — the path a running capability
        uses for a key its mission graph's "knowledge" section never anticipated. Mission and
        Platform entries have no equivalent: they're created per-platform through write_mission()
        and construction-time seeding respectively, not ad hoc by a capability."""
        self.knowledge_database.declare(key, entry_type, value,
                                         timestamp=timestamp if timestamp is not None else self.clock.now(),
                                         origin_platform_id=self.platform_id)

    def update(self) -> None:
        self._detect_mission_change()
        if self._blocked or self.active_node_id is None:
            return

        node = self.mission_graph["nodes"][self.active_node_id]
        primitives = node["primitives"]
        capability_registry = self.frontseater.capabilities()

        for name, primitive in primitives.items():
            capability = capability_registry.get(primitive["capability"])
            if capability is None:
                print(f"[Backseater] Frontseater cannot fulfill IPL type '{primitive['capability']}' — halting mission.")
                for handle in self._handles.values():
                    self.frontseater.cancel(handle)
                self._blocked = True
                return

            if name not in self._handles:
                try:
                    self._check_binding_types(capability, primitive)
                    self._handles[name] = self.frontseater.start_capability(
                        capability.ipl_type, primitive.get("inputs", {}), primitive.get("outputs", {})
                    )
                except (KeyError, ValueError) as error:
                    print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' "
                          f"({primitive['capability']}) -> failed to start: {error} — halting mission.")
                    for handle in self._handles.values():
                        self.frontseater.cancel(handle)
                    self._blocked = True
                    return
                if self.debug:
                    print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' ({primitive['capability']}) -> started")

            # Poll immediately, including on the tick a primitive was just started: a
            # resettable output (e.g. move_to's "arrived") must be recommitted to
            # Knowledge the same tick it's reset, or a stale prior value could satisfy
            # an edge condition for one extra tick before the fresh value lands. A capability
            # now publishes its own outputs to Knowledge as part of poll_status(); the
            # returned "outputs" dict here is read-only reporting, not a write path.
            try:
                poll_result = self.frontseater.poll_status(self._handles[name])
            except (KeyError, ValueError) as error:
                print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' "
                      f"({primitive['capability']}) -> polling failed: {error} — halting mission.")
                for handle in self._handles.values():
                    self.frontseater.cancel(handle)
                self._blocked = True
                return
            status = poll_result["status"]
            if self.debug and status != self._statuses.get(name):
                print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' ({primitive['capability']}) -> {status}")
            self._statuses[name] = status
            if status in ("fail", "timeout"):
                del self._handles[name]

        for condition, target_node_id in self._parsed_conditions.get(self.active_node_id, []):
            if condition.evaluate(self.knowledge_database):
                if self.debug:
                    print(f"[Backseater] Transitioning '{self.active_node_id}' -> '{target_node_id}'")
                self._activate_node(target_node_id)
                break
