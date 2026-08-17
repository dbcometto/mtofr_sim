"""End-to-end test for the "wait" mission set: ugv2's edge condition references
"ugv1/arrived", a fact that originates entirely on ugv1's own Knowledge and never
existed on ugv2 until Relay carried it across — the concrete demonstration of
cross-platform conditions described in CLAUDE.md's build order step 3."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.knowledge.knowledge import Knowledge
from mtofr.missions import mission_wait_ugv1, mission_wait_ugv2
from mtofr.relay.relay import Relay
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.world import World


def _build_stack(mission_graph, platform_id):
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    knowledge = Knowledge()
    backseater = Backseater(frontseater=frontseater, knowledge=knowledge,
                             mission_graph=mission_graph, platform_id=platform_id)
    return knowledge, backseater


class TestRelayMissionIntegration(unittest.TestCase):
    def setUp(self):
        self.ugv1_knowledge, ugv1_backseater = _build_stack(mission_wait_ugv1, "ugv1")
        self.ugv2_knowledge, ugv2_backseater = _build_stack(mission_wait_ugv2, "ugv2")
        self.ugv1_backseater = ugv1_backseater
        self.ugv2_backseater = ugv2_backseater
        self.relay = Relay()
        self.world = World(GroundPlaneEnv(), relay=self.relay,
                            backseaters={"ugv1": ugv1_backseater, "ugv2": ugv2_backseater})

    def test_ugv2_never_locally_writes_ugv1_arrived(self):
        # ugv2's mission graph only ever reads "ugv1/arrived" -- nothing in ugv2's
        # own graph declares it as an output, so any value ugv2 sees for that key
        # must have arrived via Relay.
        outputs = [
            output_key
            for node in mission_wait_ugv2["nodes"].values()
            for primitive in node["primitives"].values()
            for output_key in primitive.get("outputs", {}).values()
        ]
        self.assertNotIn("ugv1/arrived", outputs)

    def test_ugv2_waits_until_ugv1_arrives_then_drives_elsewhere_via_relay(self):
        self.assertEqual(self.ugv2_backseater.active_node_id, "stay_at_start")

        for _ in range(3000):
            self.world.step(0.1)
            if self.ugv2_backseater.active_node_id == "drive_elsewhere":
                break

        self.assertTrue(self.ugv1_knowledge.get("ugv1/arrived"))
        self.assertEqual(self.ugv2_backseater.active_node_id, "drive_elsewhere")
        # The fact reached ugv2 purely through Relay's canonical store, not any
        # direct link between the two independent Knowledge instances.
        self.assertTrue(self.ugv2_knowledge.get("ugv1/arrived"))
        self.assertTrue(self.relay.all()["ugv1/arrived"])


if __name__ == "__main__":
    unittest.main()