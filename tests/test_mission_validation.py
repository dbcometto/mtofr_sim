"""Tests for mtofr.mission.validation: the structural gate (verify_mission_structure) and
the binding checks (find_capability_problems/find_binding_problems) shared by the editor,
the assistant, Backseater.write_mission(), and Backseater's bind-time check."""
import unittest

from mtofr.core.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import Location
from mtofr.mission.validation import (
    MissionStructuralError,
    declared_types,
    find_binding_problems,
    find_capability_problems,
    find_condition_problems,
    verify_mission_structure,
)


class TestConditionProblems(unittest.TestCase):
    KNOWN = {"flag": bool, "speed": float, "count": int, "label": str}

    def test_a_clean_condition_has_no_problems(self):
        """Matching literal types (an int for a float key included) are fine."""
        condition = ["flag", "==", True, "and", "speed", ">", 1, "and", "count", "<", 3, "and", "label", "==", "x"]
        self.assertEqual(find_condition_problems(condition, self.KNOWN), [])

    def test_a_string_compared_with_a_bool_key_is_flagged(self):
        """The JSON-editor trap: "true" (a string) against a bool key."""
        problems = find_condition_problems(["flag", "==", "true"], self.KNOWN)
        self.assertEqual(len(problems), 1)
        self.assertIn("declared bool", problems[0])

    def test_a_bool_compared_with_a_number_key_is_flagged(self):
        """A bool is never a number here, even though Python treats it as an int."""
        self.assertEqual(len(find_condition_problems(["speed", ">", True], self.KNOWN)), 1)

    def test_an_undeclared_key_is_flagged(self):
        """A condition key missing from the declarations is reported."""
        self.assertIn("not declared", find_condition_problems(["ghost", "==", 1], self.KNOWN)[0])

    def test_a_condition_that_does_not_parse_is_flagged(self):
        """A malformed token list is one problem, not an exception."""
        self.assertIn("doesn't parse", find_condition_problems(["flag", "=="], self.KNOWN)[0])


class TestVerifyMissionStructure(unittest.TestCase):
    def test_passes_when_every_referenced_key_is_declared(self):
        """A graph whose edge conditions only use declared keys passes."""
        mission_graph = {
            "knowledge": {"ugv1/arrived": {"type": bool, "value": False}},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }
        verify_mission_structure(mission_graph)   # does not raise

    def test_raises_on_a_reference_to_an_undeclared_key(self):
        """An edge condition on an undeclared key raises MissionStructuralError."""
        mission_graph = {
            "knowledge": {},
            "nodes": {},
            "edges": {"n1": [{"condition": ["ugv1/arrived", "==", True], "to": "n2"}]},
            "start": "n1",
        }
        with self.assertRaises(MissionStructuralError):
            verify_mission_structure(mission_graph)

    def test_raises_on_a_capability_request_binding_to_an_undeclared_key(self):
        """An input or output bound to an undeclared key is caught at verify time, naming the key,
        rather than halting the mission later."""
        def graph(inputs, outputs):
            """Build a one-node graph whose move_to capability request has the given bindings."""
            return {"knowledge": {"goal": {"type": float, "value": 0.0}},
                    "nodes": {"n1": {"capabilities": {"nav": {"capability": "move_to", "inputs": inputs, "outputs": outputs}}}},
                    "edges": {}, "start": "n1"}
        verify_mission_structure(graph({"target": "goal"}, {}))   # does not raise
        with self.assertRaisesRegex(MissionStructuralError, "tolerance"):
            verify_mission_structure(graph({"target": "goal", "tolerance": "tolerance"}, {}))
        with self.assertRaisesRegex(MissionStructuralError, "arrived"):
            verify_mission_structure(graph({"target": "goal"}, {"arrived": "arrived"}))

    def test_passes_for_a_graph_with_no_edges(self):
        """An empty graph with no edges passes."""
        mission_graph = {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        verify_mission_structure(mission_graph)   # does not raise

    def test_mission_structural_error_is_a_value_error(self):
        """MissionStructuralError subclasses ValueError, so existing ValueError handlers catch it."""
        self.assertTrue(issubclass(MissionStructuralError, ValueError))


class TestBindingProblems(unittest.TestCase):
    """find_capability_problems()/find_binding_problems(): one check, fed either a graph's
    declarations or a live KnowledgeDatabase's types."""
    def setUp(self):
        """Build a move_to registry (target, tolerance -> arrived) and matching declared knowledge."""
        self.registry = CapabilityRegistry([Capability(
            "move_to", "d",
            inputs=(ParamSpec("target", Location, "t"), ParamSpec("tolerance", float, "m")),
            outputs=(ParamSpec("arrived", bool, "a"),))])
        self.knowledge = {"goal": {"type": Location, "value": Location(1.0, 2.0)},
                          "tolerance": {"type": float, "value": 1.0}, "arrived": {"type": bool, "value": False}}
        self.known_types = {key: declaration["type"] for key, declaration in self.knowledge.items()}

    def _problems(self, inputs, outputs=None, capability="move_to", known_types=None):
        """Return find_capability_problems() for one capability request, defaulting to the setUp key types."""
        capability_request = {"capability": capability, "inputs": inputs, "outputs": outputs or {}}
        return find_capability_problems(capability_request,self.known_types if known_types is None else known_types, self.registry)

    def test_declared_types_maps_each_key_to_its_declared_type(self):
        """declared_types() reads key -> type out of a graph's "knowledge" section."""
        self.assertEqual(declared_types({"knowledge": self.knowledge}), self.known_types)

    def test_a_correct_binding_has_no_problems(self):
        """A capability request bound to declared keys of the right types reports no problems."""
        self.assertEqual(self._problems({"target": "goal", "tolerance": "tolerance"}, {"arrived": "arrived"}), [])

    def test_undeclared_key_is_reported_with_the_fix(self):
        """Binding to an undeclared key yields one problem naming the key and telling to declare it first."""
        known_types = {key: value for key, value in self.known_types.items() if key != "tolerance"}
        problems = self._problems({"target": "goal", "tolerance": "tolerance"}, known_types=known_types)
        self.assertEqual(len(problems), 1)
        self.assertIn("'tolerance'", problems[0])
        self.assertIn("declare it first", problems[0])

    def test_wrong_key_type_is_reported(self):
        """Binding a float field to a bool key reports the expected and declared types."""
        problems = self._problems({"target": "goal", "tolerance": "arrived"})
        self.assertIn("expects float, but key 'arrived' is declared bool", problems[0])

    def test_missing_required_input_is_reported(self):
        """Leaving an input field unbound reports it as missing."""
        self.assertIn("missing required input 'tolerance'", self._problems({"target": "goal"})[0])

    def test_unknown_fields_are_reported_for_inputs_and_outputs(self):
        """Binding fields the capability doesn't have is reported for both inputs and outputs."""
        problems = self._problems({"target": "goal", "tolerance": "tolerance", "speed": "tolerance"}, {"done": "arrived"})
        self.assertTrue(any("'speed' is not an input" in problem for problem in problems))
        self.assertTrue(any("'done' is not an output" in problem for problem in problems))

    def test_outputs_are_optional(self):
        """Leaving every output unbound is not a problem."""
        self.assertEqual(self._problems({"target": "goal", "tolerance": "tolerance"}), [])

    def test_unknown_capability_lists_what_exists(self):
        """An unknown capability is reported along with the capabilities that do exist."""
        problems = self._problems({}, capability="fly")
        self.assertIn("does not exist", problems[0])
        self.assertIn("move_to", problems[0])

    def test_graph_level_check_names_the_node_and_capability_request_and_skips_an_unknown_registry(self):
        """find_binding_problems() prefixes each problem with node and capability request, and returns none without a registry."""
        graph = {"knowledge": self.knowledge, "start": "n1", "edges": {},
                 "nodes": {"n1": {"capabilities": {"go": {"capability": "move_to", "inputs": {"target": "goal"}, "outputs": {}}}}}}
        problems = find_binding_problems(graph, self.registry)
        self.assertTrue(problems[0].startswith("node 'n1' capability request 'go':"))
        self.assertEqual(find_binding_problems(graph, None), [])


if __name__ == "__main__":
    unittest.main()
