"""Defines a clock"""
import time


class Clock:
    """Wraps wall-clock time with an adjustable offset. The offset is the seam a
    future real clock-synchronization mechanism would drive; the old centralized
    Relay's placeholder sync_clock() used to reset it to 0.0 unconditionally.
    There is no shared/authoritative clock anywhere: this clock's own offset is
    locally decided (not reset by anything external), and on top of that it
    holds a separate per-peer offset table, one entry per platform this
    Backseater has synced with — estimated fresh by each pairwise
    Backseater.sync_with() handshake, not a single global value. A peer offset
    converts a timestamp from that peer's local clock frame into this clock's
    own frame, which is what lets a mesh sync re-stamp an incoming fact in
    local time before storage instead of storing a foreign timestamp verbatim."""

    def __init__(self, offset: float = 0.0):
        self._offset = offset
        self._peer_offsets: dict[str, float] = {}

    def now(self) -> float:
        """Current time, adjusted by this clock's own offset."""
        return time.time() + self._offset

    def set_offset(self, offset: float) -> None:
        """Adjusts this clock relative to wall-clock time."""
        self._offset = offset

    def set_peer_offset(self, peer_id: str, offset: float) -> None:
        """Records the estimated offset from this clock's own frame to `peer_id`'s,
        as computed by a sync_with() handshake against that peer."""
        self._peer_offsets[peer_id] = offset

    def peer_offset(self, peer_id: str) -> float:
        """Returns the offset to `peer_id`'s clock frame, or 0.0 if this clock has
        never synced with that peer yet."""
        return self._peer_offsets.get(peer_id, 0.0)

    def to_local(self, peer_id: str, remote_timestamp: float) -> float:
        """Converts `remote_timestamp`, taken from `peer_id`'s clock frame, into this
        clock's own local frame — what a mesh sync calls on every incoming fact
        before storing it, so nothing is ever stored with a foreign timestamp."""
        return remote_timestamp - self.peer_offset(peer_id)