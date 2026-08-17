"""End-to-end tests: Backseater resolves Knowledge-key inputs against the Frontseater's
CapabilityRegistry, commits capability outputs back to Knowledge, and drives a mission
graph via knowledge-based edge conditions."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.knowledge.knowledge import Knowledge, Location
from mtofr.world.base import Frontseater
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


def _bicycle_setup():
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    knowledge = Knowledge()
    knowledge.declare("goal", Location, Location(2.0, 0.0))
    knowledge.declare("tolerance", float, 0.5)
    return hardware, frontseater, knowledge


class TestBackseaterCapabilityResolution(unittest.TestCase):
    def setUp(self):
        self.hardware, self.frontseater, self.knowledge = _bicycle_setup()

        mission_graph = {
            "knowledge": {"tolerance": {"type": float, "value": 0.5}},
            "nodes": {
                "n1": {"primitives": {
                    "nav": {"capability": "move_to", "inputs": {"target": "goal", "tolerance": "tolerance"}},
                }},
            },
            "edges": {},
            "start": "n1",
        }
        self.backseater = Backseater(frontseater=self.frontseater, knowledge=self.knowledge, mission_graph=mission_graph)

    def test_capabilities_passthrough_matches_frontseater(self):
        self.assertIs(self.backseater.capabilities(), self.frontseater.capabilities())

    def test_reaches_target_by_resolving_knowledge_key(self):
        for _ in range(500):
            self.backseater.update()
            self.frontseater.update()
            self.hardware.step_dynamics(0.1)

        self.assertEqual(self.backseater._statuses["nav"], "success")

    def test_unknown_knowledge_key_blocks_mission_without_crashing(self):
        mission_graph = {
            "knowledge": {"tolerance": {"type": float, "value": 0.5}},
            "nodes": {"n1": {"primitives": {
                "nav": {"capability": "move_to", "inputs": {"target": "does_not_exist", "tolerance": "tolerance"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=self.frontseater, knowledge=self.knowledge, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater._blocked)

    def test_status_before_first_update_reports_pending(self):
        status = self.backseater.status()
        self.assertEqual(status["active_node_id"], "n1")
        self.assertFalse(status["blocked"])
        self.assertEqual(
            status["primitives"],
            {"nav": {"capability": "move_to", "status": "pending",
                      "inputs": {"target": "goal", "tolerance": "tolerance"}}},
        )

    def test_status_after_actuation_reports_capability_status_and_inputs(self):
        self.backseater.update()
        status = self.backseater.status()
        primitive_status = status["primitives"]["nav"]
        self.assertEqual(primitive_status["capability"], "move_to")
        self.assertIn(primitive_status["status"], ("in_progress", "success"))
        self.assertEqual(primitive_status["inputs"], {"target": "goal", "tolerance": "tolerance"})

    def test_status_reflects_blocked_mission(self):
        mission_graph = {
            "knowledge": {"tolerance": {"type": float, "value": 0.5}},
            "nodes": {"n1": {"primitives": {
                "nav": {"capability": "move_to", "inputs": {"target": "does_not_exist", "tolerance": "tolerance"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=self.frontseater, knowledge=self.knowledge, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater.status()["blocked"])


class TestBackseaterKnowledgeBasedTransition(unittest.TestCase):
    """A full run exercising a knowledge-based edge condition end to end: the mission
    should transition off "n1" only once move_to's "arrived" output lands in Knowledge."""
    def test_transitions_when_arrived_output_satisfies_the_edge_condition(self):
        hardware, frontseater, knowledge = _bicycle_setup()
        mission_graph = {
            "knowledge": {
                "ugv1/arrived": {"type": bool, "value": False},
                "tolerance": {"type": float, "value": 0.5},
            },
            "nodes": {
                "n1": {"primitives": {
                    "nav": {"capability": "move_to", "inputs": {"target": "goal", "tolerance": "tolerance"},
                            "outputs": {"arrived": "ugv1/arrived"}},
                }},
                "n2": {"primitives": {}},
            },
            "edges": {
                "n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}],
            },
            "start": "n1",
        }
        knowledge.declare("goal", Location, Location(2.0, 0.0))
        backseater = Backseater(frontseater=frontseater, knowledge=knowledge, mission_graph=mission_graph)

        for _ in range(500):
            backseater.update()
            frontseater.update()
            hardware.step_dynamics(0.1)
            if backseater.active_node_id == "n2":
                break

        self.assertEqual(backseater.active_node_id, "n2")
        self.assertTrue(knowledge.get("ugv1/arrived"))


class _TwoOutputFrontseater(Frontseater):
    """Minimal fake Frontseater advertising one capability with two named outputs, for
    testing that Backseater commits each bound output to its own Knowledge key by name."""
    def __init__(self):
        self._registry = CapabilityRegistry([
            Capability(
                ipl_type="scan",
                description="Fake scan capability with two outputs.",
                outputs=(ParamSpec("found", bool, "whether a target was found"),
                         ParamSpec("count", int, "number of targets found")),
            ),
        ])

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def start_capability(self, capability: str, inputs: dict) -> str:
        return "handle-1"

    def poll_status(self, handle: str) -> dict:
        return {"status": "in_progress", "outputs": {"found": True, "count": 3}}

    def cancel(self, handle: str) -> None:
        pass


class _MistypedOutputFrontseater(_TwoOutputFrontseater):
    """Reports a wrong-typed value for a declared output, to exercise Backseater's
    runtime rejection of a bad Frontseater output write."""
    def poll_status(self, handle: str) -> dict:
        return {"status": "in_progress", "outputs": {"found": "not-a-bool"}}


class TestBackseaterOutputCommitment(unittest.TestCase):
    def _mission_graph(self):
        return {
            "knowledge": {
                "ugv1/found": {"type": bool, "value": False},
                "ugv1/count": {"type": int, "value": 0},
            },
            "nodes": {"n1": {"primitives": {
                "scan": {"capability": "scan", "inputs": {}, "outputs": {"found": "ugv1/found", "count": "ugv1/count"}},
            }}},
            "edges": {},
            "start": "n1",
        }

    def test_multiple_named_outputs_are_committed_to_their_bound_keys(self):
        knowledge = Knowledge()
        backseater = Backseater(frontseater=_TwoOutputFrontseater(), knowledge=knowledge,
                                 mission_graph=self._mission_graph())
        backseater.update()
        self.assertEqual(knowledge.get("ugv1/found"), True)
        self.assertEqual(knowledge.get("ugv1/count"), 3)

    def test_wrong_typed_output_blocks_the_mission_without_crashing(self):
        knowledge = Knowledge()
        backseater = Backseater(frontseater=_MistypedOutputFrontseater(), knowledge=knowledge,
                                 mission_graph=self._mission_graph())
        backseater.update()
        self.assertTrue(backseater._blocked)


if __name__ == "__main__":
    unittest.main()
