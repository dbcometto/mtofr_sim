"""Defines a clock"""
import time


#========================================#
# Config
#========================================#

DEFAULT_PEER_OFFSET = 0.0   # s, assumed offset to a peer never synced with







#========================================#
# Clock
#========================================#

class Clock:
    """Wraps wall-clock time with an adjustable offset. There is no shared/authoritative
    clock anywhere: this clock's own offset is locally decided, and on top of it the
    clock holds a per-peer offset table, one entry per platform this Backseater has
    synced with, estimated fresh by each pairwise Backseater.sync_with() handshake. A
    peer offset converts a timestamp from that peer's local clock frame into this
    clock's own frame, which is what lets a mesh sync store an incoming fact in local
    time instead of storing a foreign timestamp verbatim."""
    # NOTE: the own offset is the seam a future real clock-synchronization mechanism
    # would drive.

    def __init__(self, offset: float = 0.0):
        """Starts `offset` (s) from wall-clock time, with no peers synced yet."""
        self._offset = offset                         # s, this clock's frame minus wall-clock time
        self._peer_offsets: dict[str, float] = {}     # peer_id -> s, peer frame minus this frame

    def now(self) -> float:
        """Current time (s, local frame): wall-clock time plus this clock's own offset."""
        return time.time() + self._offset

    def set_offset(self, offset: float) -> None:
        """Adjusts this clock relative to wall-clock time (s)."""
        self._offset = offset

    def set_peer_offset(self, peer_id: str, offset: float) -> None:
        """Records the estimated offset (s) from this clock's own frame to `peer_id`'s,
        as computed by a sync_with() handshake against that peer."""
        self._peer_offsets[peer_id] = offset

    def peer_offset(self, peer_id: str) -> float:
        """Returns the offset (s) to `peer_id`'s clock frame, or DEFAULT_PEER_OFFSET if
        this clock has never synced with that peer yet."""
        return self._peer_offsets.get(peer_id, DEFAULT_PEER_OFFSET)

    def to_local(self, peer_id: str, remote_timestamp: float) -> float:
        """Converts `remote_timestamp` (s, `peer_id`'s frame) into this clock's own
        local frame. A mesh sync calls this on every incoming fact before storing it,
        so nothing is ever stored with a foreign timestamp."""
        return remote_timestamp - self.peer_offset(peer_id)
