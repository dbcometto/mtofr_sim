"""Tests for Relay: canonical cross-platform Knowledge merge, last-write-wins
conflict resolution, the checksum-gated pull skip, and the clock-sync placeholder."""
import unittest

from mtofr.relay.relay import Relay
from mtofr.knowledge.knowledge import Knowledge
from mtofr.clock.clock import Clock


class _FakePlatform:
    """Minimal stand-in for a Backseater — Relay only ever touches `.knowledge`
    and `.clock`, so a full Backseater/Frontseater/Hardware stack isn't needed here."""
    def __init__(self):
        self.knowledge = Knowledge()
        self.clock = Clock()


class TestRelaySync(unittest.TestCase):
    def test_all_returns_empty_dict_initially(self):
        self.assertEqual(Relay().all(), {})

    def test_sync_pulls_a_platforms_knowledge_into_canonical(self):
        relay = Relay()
        platform = _FakePlatform()
        platform.knowledge.declare("ugv1/arrived", bool, True, timestamp=10.0)

        relay.sync({"ugv1": platform})

        self.assertEqual(relay.all()["ugv1/arrived"], True)

    def test_sync_pushes_canonical_facts_into_a_platform_that_declared_the_key(self):
        relay = Relay()
        ugv1 = _FakePlatform()
        ugv1.knowledge.declare("ugv1/arrived", bool, False, timestamp=1.0)
        ugv2 = _FakePlatform()
        ugv2.knowledge.declare("ugv1/arrived", bool, False, timestamp=0.0)   # foreign key, pre-declared

        ugv1.knowledge.set("ugv1/arrived", True, timestamp=5.0)
        relay.sync({"ugv1": ugv1, "ugv2": ugv2})

        self.assertEqual(ugv2.knowledge.get("ugv1/arrived"), True)

    def test_push_preserves_the_original_timestamp_not_now(self):
        relay = Relay()
        ugv1 = _FakePlatform()
        ugv1.knowledge.declare("ugv1/arrived", bool, True, timestamp=42.0)
        ugv2 = _FakePlatform()
        ugv2.knowledge.declare("ugv1/arrived", bool, False, timestamp=0.0)

        relay.sync({"ugv1": ugv1, "ugv2": ugv2})

        self.assertEqual(ugv2.knowledge.timestamp_of("ugv1/arrived"), 42.0)

    def test_push_skips_a_platform_whose_local_copy_is_already_at_least_as_fresh(self):
        relay = Relay()
        platform = _FakePlatform()
        platform.knowledge.declare("shared/flag", bool, True, timestamp=50.0)
        relay._canonical["shared/flag"] = {"value": False, "timestamp": 20.0, "platform_id": "other"}

        relay._push(platform.knowledge)

        self.assertEqual(platform.knowledge.get("shared/flag"), True)   # not overwritten by the older canonical value

    def test_push_auto_declares_an_undeclared_key_via_the_bypass(self):
        relay = Relay()
        ugv1 = _FakePlatform()
        ugv1.knowledge.declare("ugv1/novel_fact", bool, True, timestamp=1.0)
        ugv2 = _FakePlatform()   # never declared this key at all

        relay.sync({"ugv1": ugv1, "ugv2": ugv2})

        self.assertEqual(ugv2.knowledge.get("ugv1/novel_fact"), True)

    def test_last_write_wins_on_a_real_conflict_regardless_of_dict_order(self):
        relay = Relay()
        ugv1 = _FakePlatform()
        ugv1.knowledge.declare("shared/flag", bool, False, timestamp=10.0)
        ugv2 = _FakePlatform()
        ugv2.knowledge.declare("shared/flag", bool, True, timestamp=20.0)   # newer -> should win

        relay.sync({"ugv1": ugv1, "ugv2": ugv2})
        self.assertEqual(relay.all()["shared/flag"], True)

        relay_reordered = Relay()
        relay_reordered.sync({"ugv2": ugv2, "ugv1": ugv1})
        self.assertEqual(relay_reordered.all()["shared/flag"], True)

    def test_sync_clock_resets_offset_to_zero(self):
        relay = Relay()
        platform = _FakePlatform()
        platform.clock.set_offset(123.0)

        offset = relay.sync_clock(platform)

        self.assertEqual(offset, 0.0)
        self.assertEqual(platform.clock._offset, 0.0)

    def test_unchanged_platform_is_skipped_on_the_next_sync(self):
        # Regression test for the checksum fast-path: if a platform's Knowledge
        # hasn't changed since the last sync, its pull is skipped entirely rather
        # than re-scanning every key. Prove the skip is real (not just harmless) by
        # corrupting canonical directly between syncs and confirming a no-op sync
        # doesn't repair it -- if pull always rescanned, it would.
        relay = Relay()
        platform = _FakePlatform()
        platform.knowledge.declare("ugv1/arrived", bool, True, timestamp=10.0)

        relay.sync({"ugv1": platform})
        relay._canonical["ugv1/arrived"]["value"] = False   # simulate external corruption

        relay.sync({"ugv1": platform})   # platform's Knowledge did not change

        self.assertEqual(relay.all()["ugv1/arrived"], False)


if __name__ == "__main__":
    unittest.main()