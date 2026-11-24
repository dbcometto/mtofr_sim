"""Defines a backseater"""
import dataclasses
import hashlib

from mtofr.core.clock import Clock
from mtofr.database import MissionDatabase, PlatformDatabase, PlatformRecord, PlatformStatus
from mtofr.mission import (
    MissionGraph,
    MissionStructuralError,
    find_binding_problems,
    find_capability_problems,
    parse_condition,
    verify_mission_structure,
)


#========================================#
# Config
#========================================#

DATABASE_NAMES = ("knowledge", "mission", "platform")   # every database a Backseater owns, in sync order
DEFAULT_PRIVILEGE_LEVEL = 1   # 0 is the highest privilege, reserved
DEFAULT_SYNC_INTERVAL = 1.0   # s between syncs with the same peer
INITIAL_PLATFORM_STATUS = "idle"







#========================================#
# Sync Helpers
#========================================#

def _reconcile_database(destination_database, source_database, source_platform_id: str, destination_clock: Clock) -> None:
    """Pulls every entry of `source_database` into `destination_database` that is
    newer (once its timestamp is converted into `destination_clock`'s local frame)
    than what's already stored there: last-write-wins, generalized across
    Knowledge/Mission/Platform. Works one direction at a time; sync_with() calls this
    twice per database (pull, then push) to reconcile bidirectionally."""
    # NOTE: the converted timestamp is preserved rather than re-stamped "now".
    # Re-stamping would make a pulled fact look freshly written on the next sync,
    # letting it out-race the platform that actually originated it and oscillate forever.
    for key, value in source_database.all().items():
        source_timestamp = source_database.timestamp_of(key)
        converted_timestamp = destination_clock.to_local(source_platform_id, source_timestamp)
        local_timestamp = destination_database.timestamp_of(key)
        is_newer = local_timestamp is None or local_timestamp < converted_timestamp
        if is_newer:
            origin_platform_id = source_database.origin_of(key)
            if hasattr(destination_database, "set_or_declare"):
                destination_database.set_or_declare(key, value, timestamp=converted_timestamp, origin_platform_id=origin_platform_id)
            else:
                # PlatformKeyedDatabase.declare() is an unconditional upsert, unlike KnowledgeDatabase's
                # declare()/set() split, so it serves both a brand-new and an already-known entry.
                destination_database.declare(key, value, timestamp=converted_timestamp, origin_platform_id=origin_platform_id)







#========================================#
# Backseater
#========================================#

class Backseater:
    """Platform-agnostic relay between a mission graph (shape and semantics in
    mtofr.mission.graph) and a Frontseater.

    Edge conditions are parsed once per mission graph. Edges are checked in
    order; the first edge whose condition evaluates true against current Knowledge
    is taken. A node's active capability requests are handed to the Frontseater as a
    single dict (see Frontseater.set_active_capabilities) and run entirely under its own
    control from there. Backseater never polls for completion: a capability request
    decides for itself what, if anything, to write to Knowledge, and edges only ever read
    Knowledge, never capability request status. Backseater never touches physical state directly.
    """

    #===============# Construction #===============#

    def __init__(self, frontseater, knowledge_database, mission_graph: MissionGraph | None = None, platform_id: str = None,
                 privilege_level: int = DEFAULT_PRIVILEGE_LEVEL, clock: Clock = None,
                 sync_interval: float = DEFAULT_SYNC_INTERVAL, debug: bool = False):
        """Wires itself to `frontseater`, seeds its databases, and activates the mission graph's start node."""
        self.frontseater = frontseater
        self.frontseater.backseater = self  # cascades down, mirrors the platform_id cascade below
        self.knowledge_database = knowledge_database
        self.clock = clock or Clock()
        self.debug = debug
        self.privilege_level = privilege_level
        self.sync_interval = sync_interval   # s
        self._last_sync_time = {}          # peer platform_id -> local clock time (s) this platform last synced with it
        self._last_snapshot_checksum = {}  # peer platform_id -> (my_checksum, their_checksum) as of that last sync

        # Platform_id-keyed siblings to Knowledge. Mission writes from another platform are
        # gated via write_mission(), which resolves both sides' privilege levels from
        # PlatformDatabase.
        self.mission_database = MissionDatabase()
        self.platform_database = PlatformDatabase()


        # Identity cascades down to the Frontseater (and from there to its Hardware)
        # NOTE: before the default mission graph is built, since a default graph may bind
        # platform-prefixed keys (e.g. BicycleFrontseater's "<platform_id>/pose").
        self.platform_id = platform_id
        if self.platform_id is not None and self.frontseater is not None:
            self.frontseater.platform_id = platform_id
        self.mission_graph = mission_graph if mission_graph is not None else self.frontseater.default_mission_graph()


        # Own entries, gossiped to peers by mesh sync
        # NOTE: The boot mission is self-written too, so a peer (e.g. an operator interface) can read
        # what this platform is running before anyone has pushed it a new one; it is the same
        # object as self.mission_graph, so _detect_mission_change() leaves it alone.
        if self.platform_id is not None:
            self.platform_database.declare(
                self.platform_id,
                PlatformRecord(privilege_level=self.privilege_level, status=PlatformStatus(INITIAL_PLATFORM_STATUS),
                               capabilities=self.frontseater.capabilities()),
                timestamp=self.clock.now(),
                origin_platform_id=self.platform_id,
            )
            self.mission_database.declare(self.platform_id, self.mission_graph,
                                          timestamp=self.clock.now(), origin_platform_id=self.platform_id)


        # Mission state
        self._declare_knowledge_keys(self.mission_graph)
        self._parsed_conditions = self._parse_edge_conditions(self.mission_graph)

        self.active_node_id = self.mission_graph.get("start")
        self._last_sent_capability_requests = None   # last capability requests dict handed to the Frontseater, for change detection
        self._blocked = False





    #===============# Queries #===============#

    def capabilities(self):
        """Relays the Frontseater's advertised CapabilityRegistry: the query path a planner
        uses to discover what this backseater's platform can do, instead of assuming it."""
        return self.frontseater.capabilities()

    def status(self) -> dict:
        """Read-only snapshot of mission progress: the query path a visualization tool
        uses instead of reaching into private state. Per-request and overall status
        text is sourced fresh from the Frontseater's own describe_status() on every call,
        since Backseater doesn't track progress itself."""
        node = self.mission_graph["nodes"].get(self.active_node_id, {}) if self.active_node_id else {}
        capability_requests = node.get("capabilities", {})
        frontseater_status = self.frontseater.describe_status()
        request_statuses = frontseater_status.get("capabilities", {})
        return {
            "active_node_id": self.active_node_id,
            "blocked": self._blocked,
            "overall_status": frontseater_status.get("overall", ""),
            "capabilities": {
                name: {
                    "capability": capability_request["capability"],
                    "status": request_statuses.get(name, "unknown"),
                    "inputs": capability_request.get("inputs", {}),
                }
                for name, capability_request in capability_requests.items()
            },
        }





    #===============# Database Access #===============#

    def _database_for(self, database_name: str):
        """Maps a database_name string to the matching database instance: the dispatch
        point shared by query()/publish() and mesh sync."""
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
        \"platform\"): the path a running capability uses to read live data at any time,
        rather than only receiving resolved values once at start."""
        return self._database_for(database_name).get(key)

    def publish(self, database_name: str, key, value, timestamp: float = None) -> None:
        """Writes `value` to `key` in one of this platform's three databases: the path a
        running capability (or an operator interface) uses to write data at any time.
        - "mission": `key` is the target platform_id (None or this platform's own id for a
          self-write), through the gated write_mission(); a write to another platform's
          entry lands here and reaches the target by mesh sync.
        - "platform": self-write-only, and may not change this platform's own privilege level.
        - "knowledge"/"platform" go straight to that database's own type-checked set(), which
          raises if `key` wasn't already declared or `value` doesn't match its declared type."""
        if database_name == "mission":
            self.write_mission(value, writer_platform_id=self.platform_id, timestamp=timestamp, target_platform_id=key)
            return
        if database_name == "platform":
            self._check_own_record_write(key, value)
        database = self._database_for(database_name)
        database.set(key, value, timestamp=timestamp if timestamp is not None else self.clock.now(),
                      origin_platform_id=self.platform_id)

    def declare_knowledge_key(self, key: str, entry_type: type, value, timestamp: float = None) -> None:
        """Declares a brand-new Knowledge key mid-execution: the path a running capability
        uses for a key its mission graph's "knowledge" section never anticipated. Mission and
        Platform entries have no equivalent: they're created per-platform through write_mission()
        and construction-time seeding respectively, not ad hoc by a capability."""
        self.knowledge_database.declare(key, entry_type, value,
                                         timestamp=timestamp if timestamp is not None else self.clock.now(),
                                         origin_platform_id=self.platform_id)

    def _check_own_record_write(self, platform_id: str, record) -> None:
        """Raises PermissionError unless a Platform write targets this platform's own record
        and leaves its privilege level alone (only a strictly higher-privilege platform may
        change that; runtime reassignment isn't implemented). Write-side only: mesh sync
        carries peers' records without this check."""
        if platform_id != self.platform_id:
            raise PermissionError(
                f"Platform '{self.platform_id}' may only write its own PlatformRecord, not '{platform_id}'s"
            )
        own_record = self.platform_database.get(self.platform_id)
        if isinstance(record, PlatformRecord) and record.privilege_level != own_record.privilege_level:
            raise PermissionError(f"Platform '{self.platform_id}' may not change its own privilege level")

    def _capabilities_of(self, platform_id: str):
        """The CapabilityRegistry `platform_id` advertises: this platform's own live one, or a
        peer's as gossiped in its PlatformRecord (None if unknown here)."""
        if platform_id == self.platform_id:
            return self.frontseater.capabilities()
        known_records = self.platform_database.all()
        return known_records[platform_id].capabilities if platform_id in known_records else None

    def write_mission(self, mission_graph: MissionGraph, writer_platform_id: str, timestamp: float = None,
                      target_platform_id: str = None) -> None:
        """The single gated write point for a Mission database entry: `target_platform_id`'s
        (None = this platform's own). Writing another platform's entry is a mesh write: it
        lands in this platform's Mission database and reaches the target by sync, whose
        mission-change detection adopts it, with every check done here, write-side.

        Skips the privilege check when the writer is the target (self-writes are always
        allowed); otherwise requires the writer's privilege level to be strictly
        higher-privilege (lower number) than the target's, both resolved from this platform's
        own PlatformDatabase. Raises PermissionError if the writer is unprivileged or either
        side is unknown, ValueError on a type mismatch, and MissionStructuralError if the graph
        references an undeclared knowledge key, or can't be bound on the target (or the
        target's capabilities aren't known here yet). A successful write just lands; the
        target's next update() detects it and changes the mission."""
        target_platform_id = self.platform_id if target_platform_id is None else target_platform_id


        # Privilege check
        if writer_platform_id != target_platform_id:
            known_records = self.platform_database.all()
            for platform_id in (writer_platform_id, target_platform_id):
                if platform_id not in known_records:
                    raise PermissionError(
                        f"Cannot verify privilege of unknown platform '{platform_id}' — rejecting Mission write"
                    )
            writer_record, target_record = known_records[writer_platform_id], known_records[target_platform_id]
            if not writer_record.privilege_level < target_record.privilege_level:
                raise PermissionError(
                    f"Platform '{writer_platform_id}' (privilege {writer_record.privilege_level}) may not write "
                    f"platform '{target_platform_id}'s Mission entry (privilege {target_record.privilege_level})"
                )


        # Type check, before structural verify, which assumes a dict
        if not isinstance(mission_graph, self.mission_database.value_type):
            raise ValueError(
                f"{type(self.mission_database).__name__} expected "
                f"{self.mission_database.value_type.__name__}, got {type(mission_graph).__name__}"
            )


        # Structural verify and binding check
        verify_mission_structure(mission_graph)
        target_capabilities = self._capabilities_of(target_platform_id)
        if target_capabilities is None:
            raise MissionStructuralError(
                f"Cannot check bindings: platform '{target_platform_id}'s capabilities aren't known here yet"
            )
        binding_problems = find_binding_problems(mission_graph, target_capabilities)
        if binding_problems:   # reject now rather than accept it and halt the running mission at bind time
            raise MissionStructuralError(
                f"Mission graph cannot be bound on platform '{target_platform_id}': " + "; ".join(binding_problems)
            )


        # Write
        write_timestamp = timestamp if timestamp is not None else self.clock.now()
        if target_platform_id in self.mission_database.all():
            self.mission_database.set(target_platform_id, mission_graph, timestamp=write_timestamp, origin_platform_id=writer_platform_id)
        else:
            self.mission_database.declare(target_platform_id, mission_graph, timestamp=write_timestamp, origin_platform_id=writer_platform_id)





    #===============# Mesh Sync #===============#

    def _snapshot_checksum(self) -> str:
        """Hashes every (database, key, value, timestamp) entry across all three of this
        platform's databases: the cheap "did anything change since the last sync with
        this peer" check sync_with() uses to skip a full reconcile when nothing did.
        Database name prefixes each item since Knowledge keys and platform_ids share the
        same string namespace and could otherwise collide."""
        items = []
        for database_name in DATABASE_NAMES:
            database = self._database_for(database_name)
            items.extend(
                (database_name, key, repr(value), database.timestamp_of(key))
                for key, value in database.all().items()
            )
        return hashlib.sha256(repr(sorted(items, key=lambda item: (item[0], item[1]))).encode()).hexdigest()

    def _handshake_clock(self, peer: "Backseater") -> None:
        """Estimates the offset (s) from this platform's clock frame to `peer`'s, and vice
        versa, and records both, each side computed independently from its own read of
        the other's clock."""
        # NOTE: no network delay is simulated yet (see roadmap.md's comms boundary), so this
        # is exact rather than a real round-trip estimate.
        self.clock.set_peer_offset(peer.platform_id, peer.clock.now() - self.clock.now())
        peer.clock.set_peer_offset(self.platform_id, self.clock.now() - peer.clock.now())

    def sync_with(self, peer: "Backseater") -> None:
        """Reconciles this platform's three databases against `peer`'s, bidirectionally,
        last-write-wins by (locally-converted) timestamp: a named simplification, not a
        robust consensus mechanism. Symmetric: calling it from either side of a pair
        produces the same end state. Idempotent: calling it twice in a row (or from both
        sides in the same tick) converges to the same state the second time as a no-op,
        which is what lets both platforms in a pair independently decide to initiate a
        sync without any lock or tie-break between them.

        Bypasses write_mission()'s privilege/type/structural gate for the Mission database
        (and self-write-only for Platform), since all such checks happen write-side only,
        once, at the originating platform, with no receipt-side re-verification. A Mission
        or Platform entry "about" this platform itself is reconciled like any other.
        """
        self_checksum = self._snapshot_checksum()
        peer_checksum = peer._snapshot_checksum()
        if self._last_snapshot_checksum.get(peer.platform_id) == (self_checksum, peer_checksum):
            self._last_sync_time[peer.platform_id] = self.clock.now()
            peer._last_sync_time[self.platform_id] = peer.clock.now()
            return   # nothing changed on either side since the last sync with this peer

        self._handshake_clock(peer)

        for database_name in DATABASE_NAMES:
            self_database = self._database_for(database_name)
            peer_database = peer._database_for(database_name)
            _reconcile_database(self_database, peer_database, peer.platform_id, self.clock)
            _reconcile_database(peer_database, self_database, self.platform_id, peer.clock)

        self._last_sync_time[peer.platform_id] = self.clock.now()
        peer._last_sync_time[self.platform_id] = peer.clock.now()
        self._last_snapshot_checksum[peer.platform_id] = (self._snapshot_checksum(), peer._snapshot_checksum())

        if self.debug:
            print(f"[Backseater] Synced with '{peer.platform_id}'")

    def last_sync_times(self) -> dict:
        """peer platform_id -> local clock time (s) this platform last synced with it (a copy):
        how fresh each peer's gossiped entries here can be, for an operator display."""
        return dict(self._last_sync_time)

    def sync_with_stale_peers(self, peers: list["Backseater"]) -> None:
        """Calls sync_with() against every peer in `peers` whose last sync (if any) is
        older than this platform's sync_interval: the staleness gate World drives each
        tick. Peers within the interval are skipped entirely, not even checksummed."""
        now = self.clock.now()
        for peer in peers:
            last_sync_time = self._last_sync_time.get(peer.platform_id)
            if last_sync_time is None or now - last_sync_time > self.sync_interval:
                self.sync_with(peer)





    #===============# Mission Change #===============#

    def _declare_knowledge_keys(self, mission_graph: MissionGraph) -> None:
        """Declares/resets every knowledge key listed in `mission_graph`'s "knowledge"
        section to its declared type/default; shared by construction and mission-change handling."""
        for key, declaration in mission_graph.get("knowledge", {}).items():
            self.knowledge_database.declare(key, declaration["type"], declaration["value"], timestamp=self.clock.now(),
                                            origin_platform_id=self.platform_id)

    def _parse_edge_conditions(self, mission_graph: MissionGraph) -> dict:
        """Parses every edge condition in `mission_graph` once, keyed by source node id;
        shared by construction and mission-change handling."""
        return {
            node_id: [(parse_condition(edge["condition"]), edge["to"]) for edge in edges]
            for node_id, edges in mission_graph.get("edges", {}).items()
        }

    def _activate_node(self, node_id) -> None:
        """Makes `node_id` the active node; its capability requests are handed off on the next check in update()."""
        self.active_node_id = node_id

    def _detect_mission_change(self) -> None:
        """Detects whether this platform's own Mission database entry is a different
        object than the mission graph currently driving update(), and if so swaps to it.
        Done here rather than synchronously inside write_mission() so a mesh sync that
        writes mission_database directly triggers the mission change the same way a
        local write_mission() call does. No-ops while the entry is still the boot mission
        the constructor self-wrote (the same object), or for a platform with no id.
        """
        if self.platform_id is None or self.platform_id not in self.mission_database.all():
            return

        new_mission_graph = self.mission_database.get(self.platform_id)
        if new_mission_graph is self.mission_graph:
            return

        self._declare_knowledge_keys(new_mission_graph)

        self.mission_graph = new_mission_graph
        self._parsed_conditions = self._parse_edge_conditions(new_mission_graph)
        self._blocked = False
        self._last_sent_capability_requests = None   # force a fresh set_active_capabilities() call below, even on a coincidental match
        self._activate_node(new_mission_graph.get("start"))

        if self.debug:
            print(f"[Backseater] Mission changed — active node now '{self.active_node_id}'")





    #===============# Tick #===============#

    def update(self) -> None:
        """Advances this platform's mission by one tick, then re-publishes its own
        PlatformRecord if its live status changed, so peers observe it via mesh sync."""
        self._advance_mission()
        self._refresh_own_record()

    def _refresh_own_record(self) -> None:
        """Self-writes this platform's PlatformRecord with a status built from status(), only
        when that status changed (so an idle platform doesn't churn the sync checksum)."""
        if self.platform_id is None:
            return
        status = self.status()
        own_record = self.platform_database.get(self.platform_id)
        new_status = PlatformStatus(
            status=status["overall_status"],
            message=own_record.status.message,
            active_node_id=status["active_node_id"],
            blocked=status["blocked"],
            capability_statuses=status["capabilities"],
        )
        if new_status != own_record.status:
            self.publish("platform", self.platform_id, dataclasses.replace(own_record, status=new_status))

    def _advance_mission(self) -> None:
        """Detects a mission change, checks the active node's capability requests are all
        fulfillable and correctly bound, hands them to the Frontseater only if they differ
        from what it was last given, then evaluates edges. There is no polling here: once
        handed off, running the capability requests is entirely the Frontseater's own affair."""
        self._detect_mission_change()
        if self._blocked or self.active_node_id is None:
            return

        node = self.mission_graph["nodes"][self.active_node_id]
        capability_requests = node["capabilities"]
        capability_registry = self.frontseater.capabilities()


        # Every capability request must be fulfillable and correctly bound, or the mission halts
        # NOTE: checked against the live Knowledge types, not the graph's declarations: a
        # key may also come from mesh sync or declare_knowledge_key(). Run once per tick
        # before handing off, so the check stays here instead of in each Frontseater.
        known_types = self.knowledge_database.types()
        binding_problems = [
            f"capability request '{name}' ({capability_request['capability']}): {problem}"
            for name, capability_request in capability_requests.items()
            for problem in find_capability_problems(capability_request, known_types, capability_registry)
        ]
        if binding_problems:
            print(f"[Backseater] Node '{self.active_node_id}' failed binding check: "
                  f"{'; '.join(binding_problems)} — halting mission.")
            self._blocked = True
            return


        # Hand off on change only
        # NOTE: object identity, not value equality: the active node's capability requests dict
        # is the same object every tick until the node changes, so this is a cheap no-op check
        # rather than a deep dict comparison, and a node change always yields a
        # different dict object, so it's never a false negative.
        if capability_requests is not self._last_sent_capability_requests:
            self.frontseater.set_active_capabilities(capability_requests)
            self._last_sent_capability_requests = capability_requests
            if self.debug:
                print(f"[Backseater] Node '{self.active_node_id}' -> active capability requests: {list(capability_requests)}")


        # Take the first edge whose condition holds
        target_node_id = next(
            (target for condition, target in self._parsed_conditions.get(self.active_node_id, [])
             if condition.evaluate(self.knowledge_database)),
            None,
        )
        if target_node_id is not None:
            if self.debug:
                print(f"[Backseater] Transitioning '{self.active_node_id}' -> '{target_node_id}'")
            self._activate_node(target_node_id)
