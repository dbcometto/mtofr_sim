"""End-to-end tests: Backseater hands a capability the raw Knowledge-key bindings from
the mission graph, the capability calls query()/publish() on its own Backseater to read
inputs and write outputs, and the mission graph transitions on knowledge-based edge
conditions driven by those published outputs."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import KnowledgeDatabase, Location
from mtofr.world.base import Frontseater
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


def _bicycle_setup():
    hardware = BicycleHardware()
    frontseater = BicycleFrontseater(hardware=hardware)
    knowledge = KnowledgeDatabase()
    knowledge.declare("goal", Location, Location(2.0, 0.0))
    knowledge.declare("tolerance", float, 0.5)
    return hardware, frontseater, knowledge


class TestBackseaterCapabilityExecution(unittest.TestCase):
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
        self.backseater = Backseater(frontseater=self.frontseater, knowledge_database=self.knowledge, mission_graph=mission_graph)

    def tearDown(self):
        self.frontseater.shutdown()

    def test_capabilities_passthrough_matches_frontseater(self):
        self.assertIs(self.backseater.capabilities(), self.frontseater.capabilities())

    def test_reaches_target_by_querying_knowledge_key(self):
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
        backseater = Backseater(frontseater=self.frontseater, knowledge_database=self.knowledge, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater._blocked)

    def test_mistyped_knowledge_key_blocks_mission_without_crashing(self):
        # "tolerance" is declared bool here, but move_to's ParamSpec for that field is float.
        mission_graph = {
            "knowledge": {"tolerance": {"type": bool, "value": False}},
            "nodes": {"n1": {"primitives": {
                "nav": {"capability": "move_to", "inputs": {"target": "goal", "tolerance": "tolerance"}},
            }}},
            "edges": {},
            "start": "n1",
        }
        backseater = Backseater(frontseater=self.frontseater, knowledge_database=self.knowledge, mission_graph=mission_graph)
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
        backseater = Backseater(frontseater=self.frontseater, knowledge_database=self.knowledge, mission_graph=mission_graph)
        backseater.update()
        self.assertTrue(backseater.status()["blocked"])


class TestBackseaterKnowledgeBasedTransition(unittest.TestCase):
    """A full run exercising a knowledge-based edge condition end to end: the mission
    should transition off "n1" only once move_to publishes "arrived" into Knowledge."""
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
        backseater = Backseater(frontseater=frontseater, knowledge_database=knowledge, mission_graph=mission_graph)

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
    testing that a capability publishes each bound output to its own Knowledge key by name."""
    def __init__(self):
        self.backseater = None
        self._registry = CapabilityRegistry([
            Capability(
                ipl_type="scan",
                description="Fake scan capability with two outputs.",
                outputs=(ParamSpec("found", bool, "whether a target was found"),
                         ParamSpec("count", int, "number of targets found")),
            ),
        ])
        self._outputs_by_handle = {}

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def start_capability(self, capability: str, inputs: dict, outputs: dict) -> str:
        self._outputs_by_handle["handle-1"] = outputs
        return "handle-1"

    def poll_status(self, handle: str) -> dict:
        output_keys = self._outputs_by_handle[handle]
        found, count = True, 3
        self.backseater.publish("knowledge", output_keys["found"], found)
        self.backseater.publish("knowledge", output_keys["count"], count)
        return {"status": "in_progress", "outputs": {"found": found, "count": count}}

    def cancel(self, handle: str) -> None:
        pass


class _MistypedOutputFrontseater(_TwoOutputFrontseater):
    """Publishes a wrong-typed value for a declared output, to exercise Backseater's
    runtime rejection of a bad Frontseater output write."""
    def poll_status(self, handle: str) -> dict:
        output_keys = self._outputs_by_handle[handle]
        self.backseater.publish("knowledge", output_keys["found"], "not-a-bool")
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
        knowledge = KnowledgeDatabase()
        backseater = Backseater(frontseater=_TwoOutputFrontseater(), knowledge_database=knowledge,
                                 mission_graph=self._mission_graph())
        backseater.update()
        self.assertEqual(knowledge.get("ugv1/found"), True)
        self.assertEqual(knowledge.get("ugv1/count"), 3)

    def test_wrong_typed_output_blocks_the_mission_without_crashing(self):
        knowledge = KnowledgeDatabase()
        backseater = Backseater(frontseater=_MistypedOutputFrontseater(), knowledge_database=knowledge,
                                 mission_graph=self._mission_graph())
        backseater.update()
        self.assertTrue(backseater._blocked)


if __name__ == "__main__":
    unittest.main()