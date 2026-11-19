"""End-to-end test for World-driven peer-to-peer mesh sync: ugv2's edge condition
references "ugv1/arrived", a fact that originates entirely on ugv1's own Knowledge and
never exists on ugv2 until World.step()'s pairwise sync_with_stale_peers() carries it
across. Also covers a privileged Mission write propagating to a peer the same way,
since Mission entries are gossiped by the same mesh sync."""
import unittest

from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.world import World
from mtofr.platform.platform import Platform
from mtofr.scenarios.wait import mission_wait_ugv1, mission_wait_ugv2


def _build_stack(test_case, mission_graph, platform_id, privilege_level=1) -> Platform:
    """Builds a bicycle UGV that re-syncs every tick, registering its shutdown."""
    spec = bicycle_ugv(platform_id, 0.0, 0.0, mission_graph=mission_graph, privilege_level=privilege_level)
    # sync_interval=0.0: every World.step() re-syncs immediately rather than waiting
    # on real wall-clock time to elapse, which would make this test's timing depend
    # on how long BicycleFrontseater's MPC solve actually takes.
    spec.sync_interval = 0.0
    platform = Platform(spec)
    test_case.addCleanup(platform.shutdown)
    return platform


class TestMeshMissionIntegration(unittest.TestCase):
    def setUp(self):
        """Put ugv1 and ugv2, running the WAIT mission set, in one World."""
        ugv1 = _build_stack(self, mission_wait_ugv1, "ugv1")
        ugv2 = _build_stack(self, mission_wait_ugv2, "ugv2")
        self.ugv1_knowledge, self.ugv1_backseater = ugv1.knowledge_database, ugv1.backseater
        self.ugv2_knowledge, self.ugv2_backseater = ugv2.knowledge_database, ugv2.backseater
        self.world = World(GroundPlaneEnv(), platforms={"ugv1": ugv1, "ugv2": ugv2})

    def test_ugv2_never_locally_writes_ugv1_arrived(self):
        """No capability request in ugv2's graph binds "ugv1/arrived" as an output."""
        # ugv2's mission graph only ever reads "ugv1/arrived" -- nothing in ugv2's
        # own graph declares it as an output, so any value ugv2 sees for that key
        # must have arrived via mesh sync.
        outputs = [
            output_key
            for node in mission_wait_ugv2["nodes"].values()
            for capability_request in node["capabilities"].values()
            for output_key in capability_request.get("outputs", {}).values()
        ]
        self.assertNotIn("ugv1/arrived", outputs)

    def test_ugv2_waits_until_ugv1_arrives_then_drives_elsewhere_via_mesh_sync(self):
        """ugv2 leaves stay_at_start for drive_elsewhere once ugv1's arrival reaches it through mesh sync."""
        self.assertEqual(self.ugv2_backseater.active_node_id, "stay_at_start")

        step_count = 0
        while self.ugv2_backseater.active_node_id != "drive_elsewhere" and step_count < 3000:
            self.world.step(0.1)
            step_count += 1

        self.assertTrue(self.ugv1_knowledge.get("ugv1/arrived"))
        self.assertEqual(self.ugv2_backseater.active_node_id, "drive_elsewhere")
        # The fact reached ugv2 purely through World.step()'s pairwise mesh sync,
        # not any direct link between the two independent Knowledge instances.
        self.assertTrue(self.ugv2_knowledge.get("ugv1/arrived"))


class TestMeshMissionEntryGossipIntegration(unittest.TestCase):
    """A platform's own Mission database entry is gossiped to a peer purely through
    World.step()'s mesh sync -- write_mission() itself is a direct, gated call (there
    is no networked "install a mission on a remote platform" RPC yet, per docs/roadmap.md's
    "real comms boundary" step being deferred); what's networked is a peer's *view*
    of that entry propagating afterward, the same way Knowledge does."""
    def setUp(self):
        """Put a privilege-0 commander and a privilege-1 ugv1, both on empty graphs, in one World."""
        empty_graph ={"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        commander = _build_stack(self, empty_graph, "commander", privilege_level=0)
        ugv1 = _build_stack(self, empty_graph, "ugv1", privilege_level=1)
        self.commander_knowledge, self.commander_backseater = commander.knowledge_database, commander.backseater
        self.ugv1_knowledge, self.ugv1_backseater = ugv1.knowledge_database, ugv1.backseater
        self.world = World(GroundPlaneEnv(), platforms={"commander": commander, "ugv1": ugv1})

    def test_a_platforms_mission_entry_reaches_a_peer_via_world_step(self):
        """ugv1's Mission entry, written there by commander, reaches commander's Mission database via World steps."""
        # One tick first, so ugv1 and commander have already gossiped each other's
        # PlatformRecord -- required for the privilege check inside write_mission().
        self.world.step(0.1)

        new_graph = {
            "knowledge": {"ugv1/marker": {"type": bool, "value": True}},
            "nodes": {"n1": {"capabilities": {}}},
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
