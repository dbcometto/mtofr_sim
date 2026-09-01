"""End-to-end test for World-driven peer-to-peer mesh sync (mesh redesign increment
6): ugv2's edge condition references "ugv1/arrived", a fact that originates entirely
on ugv1's own Knowledge and never existed on ugv2 until World.step()'s pairwise
sync_with_stale_peers() carried it across — replacing the old Relay-mediated version
of this same demonstration (test_relay_mission_integration.py, deleted this
increment). Also covers a privileged Mission write propagating to a peer the same
way, since Mission entries are gossiped by the same mesh sync."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.database import KnowledgeDatabase, PlatformRecord
from mtofr.missions import mission_wait_ugv1, mission_wait_ugv2
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.world import World


def _build_stack(test_case, mission_graph, platform_id, privilege_level=1):
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    test_case.addCleanup(frontseater.shutdown)
    knowledge = KnowledgeDatabase()
    # sync_interval=0.0: every World.step() re-syncs immediately rather than waiting
    # on real wall-clock time to elapse, which would make this test's timing depend
    # on how long BicycleFrontseater's MPC solve actually takes.
    backseater = Backseater(frontseater=frontseater, knowledge_database=knowledge,
                             mission_graph=mission_graph, platform_id=platform_id,
                             privilege_level=privilege_level, sync_interval=0.0)
    return knowledge, backseater


class TestMeshMissionIntegration(unittest.TestCase):
    def setUp(self):
        self.ugv1_knowledge, ugv1_backseater = _build_stack(self, mission_wait_ugv1, "ugv1")
        self.ugv2_knowledge, ugv2_backseater = _build_stack(self, mission_wait_ugv2, "ugv2")
        self.ugv1_backseater = ugv1_backseater
        self.ugv2_backseater = ugv2_backseater
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": ugv1_backseater, "ugv2": ugv2_backseater})

    def test_ugv2_never_locally_writes_ugv1_arrived(self):
        # ugv2's mission graph only ever reads "ugv1/arrived" -- nothing in ugv2's
        # own graph declares it as an output, so any value ugv2 sees for that key
        # must have arrived via mesh sync.
        outputs = [
            output_key
            for node in mission_wait_ugv2["nodes"].values()
            for primitive in node["primitives"].values()
            for output_key in primitive.get("outputs", {}).values()
        ]
        self.assertNotIn("ugv1/arrived", outputs)

    def test_ugv2_waits_until_ugv1_arrives_then_drives_elsewhere_via_mesh_sync(self):
        self.assertEqual(self.ugv2_backseater.active_node_id, "stay_at_start")

        for _ in range(3000):
            self.world.step(0.1)
            if self.ugv2_backseater.active_node_id == "drive_elsewhere":
                break

        self.assertTrue(self.ugv1_knowledge.get("ugv1/arrived"))
        self.assertEqual(self.ugv2_backseater.active_node_id, "drive_elsewhere")
        # The fact reached ugv2 purely through World.step()'s pairwise mesh sync,
        # not any direct link between the two independent Knowledge instances.
        self.assertTrue(self.ugv2_knowledge.get("ugv1/arrived"))


class TestMeshMissionEntryGossipIntegration(unittest.TestCase):
    """A platform's own Mission database entry is gossiped to a peer purely through
    World.step()'s mesh sync -- write_mission() itself is a direct, gated call (there
    is no networked "install a mission on a remote platform" RPC yet, per CLAUDE.md's
    "real comms boundary" step being deferred); what's networked is a peer's *view*
    of that entry propagating afterward, the same way Knowledge does."""
    def setUp(self):
        empty_graph = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        self.commander_knowledge, self.commander_backseater = _build_stack(
            self, empty_graph, "commander", privilege_level=0)
        self.ugv1_knowledge, self.ugv1_backseater = _build_stack(
            self, empty_graph, "ugv1", privilege_level=1)
        self.world = World(GroundPlaneEnv(), backseaters={
            "commander": self.commander_backseater, "ugv1": self.ugv1_backseater,
        })

    def test_a_platforms_mission_entry_reaches_a_peer_via_world_step(self):
        # One tick first, so ugv1 and commander have already gossiped each other's
        # PlatformRecord -- required for the privilege check inside write_mission().
        self.world.step(0.1)

        new_graph = {
            "knowledge": {"ugv1/marker": {"type": bool, "value": True}},
            "nodes": {"n1": {"primitives": {}}},
            "edges": {},
            "start": "n1",
        }
        self.ugv1_backseater.write_mission(new_graph, writer_platform_id="commander")

        for _ in range(50):
            self.world.step(0.1)
            if self.commander_backseater.mission_database.get("ugv1") == new_graph:
                break

        # The fact that ugv1's Mission entry is now this graph reached commander
        # purely through World.step()'s pairwise mesh sync, not any direct link.
        self.assertEqual(self.commander_backseater.mission_database.get("ugv1"), new_graph)
        self.assertEqual(self.ugv1_backseater.active_node_id, "n1")


if __name__ == "__main__":
    unittest.main()
