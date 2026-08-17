"""Defines the Relay: the canonical cross-platform Knowledge store."""
import hashlib


class Relay:
    """Owns the canonical cross-platform Knowledge database — distinct from each
    Backseater's own per-platform Knowledge — and reconciles it against every
    platform's local Knowledge on every sync() call, the same way a future
    Foreman/Frontend would sit above Backseater/Frontseater/Hardware. Conflict
    resolution is last-write-wins by timestamp: a placeholder, not a robust
    distributed-systems answer, but enough to make the consideration explicit.
    Clock synchronization is likewise a placeholder — sync_clock() always resets
    a platform's clock offset to 0.0 (identity); the real mechanism is an open
    design question (see notes.md), not solved here.

    sync() pulls every platform's current Knowledge into the canonical store
    (newest timestamp per key wins), then pushes any canonical fact newer than a
    platform's local copy back into that platform's Knowledge. A per-platform
    checksum of the last-seen snapshot lets an unchanged platform's pull be
    skipped cheaply instead of re-comparing every key/timestamp pair every tick."""

    def __init__(self):
        self._canonical = {}              # key -> {"value", "timestamp", "platform_id"}
        self._last_snapshot_checksum = {}  # platform_id -> checksum, to skip an unchanged platform's pull

    def all(self) -> dict:
        """key -> value for every canonical fact — a read-only snapshot, the query
        path a visualization tool uses to browse the relay's cross-platform store."""
        return {key: entry["value"] for key, entry in self._canonical.items()}

    def sync(self, backseaters: dict) -> None:
        """Reconciles every backseater's Knowledge against the canonical store.
        `backseaters`: platform_id -> Backseater (or any object exposing
        `.knowledge` and `.clock`)."""
        for backseater in backseaters.values():
            self.sync_clock(backseater)
        for platform_id, backseater in backseaters.items():
            self._pull(platform_id, backseater.knowledge)
        for backseater in backseaters.values():
            self._push(backseater.knowledge)

    def sync_clock(self, backseater) -> float:
        """Placeholder clock-synchronization seam: real offset computation (so
        every platform agrees on "now") is an open design question, so this
        always resets the given backseater's clock to identity and returns 0.0."""
        backseater.clock.set_offset(0.0)
        return 0.0

    #=====# Internal #=====#

    @staticmethod
    def _snapshot_checksum(knowledge) -> str:
        items = sorted(
            (key, repr(value), knowledge.timestamp_of(key))
            for key, value in knowledge.all().items()
        )
        return hashlib.sha256(repr(items).encode()).hexdigest()

    def _pull(self, platform_id: str, knowledge) -> None:
        checksum = self._snapshot_checksum(knowledge)
        if self._last_snapshot_checksum.get(platform_id) == checksum:
            return   # nothing changed on this platform since the last sync

        for key, value in knowledge.all().items():
            timestamp = knowledge.timestamp_of(key)
            canonical_entry = self._canonical.get(key)
            if canonical_entry is None or timestamp > canonical_entry["timestamp"]:
                self._canonical[key] = {"value": value, "timestamp": timestamp, "platform_id": platform_id}

        self._last_snapshot_checksum[platform_id] = checksum

    def _push(self, knowledge) -> None:
        for key, canonical_entry in self._canonical.items():
            local_timestamp = knowledge.timestamp_of(key)
            if local_timestamp is not None and local_timestamp >= canonical_entry["timestamp"]:
                continue   # local copy is at least as fresh as canonical — nothing to push
            # Preserve the canonical timestamp rather than stamping "now": re-stamping
            # would make a pushed fact look freshly-written on the next sync, letting
            # it out-race the platform that actually originated it and oscillate forever.
            knowledge.set_or_declare(key, canonical_entry["value"], timestamp=canonical_entry["timestamp"])