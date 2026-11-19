"""Integration test: two fully independent platform stacks (own hardware, frontseater,
backseater, Knowledge, mission graph) ticked through the same World, to confirm World
supports more than one platform with no shared state or cross-platform coupling."""
import unittest

from mtofr.database import Location
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.world.platform import Platform
from mtofr.world.world import World


def _build_platform(test_case, platform_id, target, tolerance_key, arrived_key) -> Platform:
    """Builds a bicycle UGV whose one node drives to target, registering its shutdown."""
    # Target key is namespaced per platform, not shared as a bare "target" -- with
    # World now mesh-syncing Knowledge between every pair of platforms, a shared key
    # name would have one platform's target silently overwrite the other's.
    target_key = f"{platform_id}/target"
    mission_graph = {
        "knowledge": {
            target_key: {"type": Location, "value": target},
            tolerance_key: {"type": float, "value": 0.5},
            arrived_key: {"type": bool, "value": False},
        },
        "nodes": {"n1": {"primitives": {
            "nav": {"capability": "move_to", "inputs": {"target": target_key, "tolerance": tolerance_key},
                    "outputs": {"arrived": arrived_key}},
        }}},
        "edges": {},
        "start": "n1",
    }
    platform = Platform(bicycle_ugv(platform_id, 0.0, 0.0, mission_graph=mission_graph))
    test_case.addCleanup(platform.shutdown)
    return platform


class TestMultiPlatformWorld(unittest.TestCase):
    def setUp(self):
        ugv1 = _build_platform(self, "ugv1", Location(5.0, 0.0), "ugv1/tolerance", "ugv1/arrived")
        ugv2 = _build_platform(self, "ugv2", Location(-5.0, 0.0), "ugv2/tolerance", "ugv2/arrived")
        self.ugv1_hardware, self.ugv1_knowledge = ugv1.hardware, ugv1.knowledge_database
        self.ugv2_hardware, self.ugv2_knowledge = ugv2.hardware, ugv2.knowledge_database

        self.world = World(GroundPlaneEnv(), platforms={"ugv1": ugv1, "ugv2": ugv2})

    def test_both_platforms_keep_their_own_identity(self):
        self.assertEqual(self.ugv1_hardware.platform_id, "ugv1")
        self.assertEqual(self.ugv2_hardware.platform_id, "ugv2")

    def test_stepping_moves_each_platform_toward_its_own_target_independently(self):
        for _ in range(200):
            self.world.step(0.1)

        self.assertGreater(self.ugv1_hardware.state.x, 0.0)
        self.assertLess(self.ugv2_hardware.state.x, 0.0)

    def test_knowledge_stores_do_not_leak_keys_between_platforms(self):
        self.assertNotIn("ugv2/arrived", self.ugv1_knowledge.all())
        self.assertNotIn("ugv1/arrived", self.ugv2_knowledge.all())

    def test_get_states_reports_both_platforms_by_id(self):
        states = self.world.get_states()
        self.assertEqual(set(states.keys()), {"ugv1", "ugv2"})


if __name__ == "__main__":
    unittest.main()