"""Tests for the capability registry: ParamSpec/Capability validation and description."""
import unittest

from mtofr.capability.capability import (
    Capability, ParamSpec, CapabilityRegistry, find_binding_problems, find_primitive_problems,
)
from mtofr.database import Location


class TestParamSpec(unittest.TestCase):
    def test_describe_includes_knowledge_entry_description_for_a_knowledge_entry_type(self):
        """describe() of a KnowledgeEntry-typed field includes the field name and the type's own describe()."""
        spec = ParamSpec("target", Location, "Location to navigate to")
        description = spec.describe()
        self.assertIn("target", description)
        self.assertIn(Location.describe(), description)

    def test_describe_omits_knowledge_entry_description_for_a_plain_type(self):
        """describe() of a plain-typed field shows the field name and the type name."""
        spec = ParamSpec("radius", float, "Avoid-region radius in meters")
        description = spec.describe()
        self.assertIn("radius", description)
        self.assertIn("float", description)


class TestCapability(unittest.TestCase):
    def setUp(self):
        """Build a move_to capability with one input and one output."""
        self.move_to = Capability(
            ipl_type="move_to",
            description="Navigate to a target location.",
            inputs=(ParamSpec("target", Location, "Location to navigate to"),),
            outputs=(ParamSpec("arrived", bool, "True once within tolerance"),),
        )

    def test_describe_includes_inputs_and_outputs(self):
        """describe() names the capability and its input and output fields."""
        description = self.move_to.describe()
        self.assertIn("move_to", description)
        self.assertIn("target", description)
        self.assertIn("arrived", description)


class TestCapabilityRegistry(unittest.TestCase):
    def setUp(self):
        """Build a registry holding move_to and avoid."""
        self.registry = CapabilityRegistry([
            Capability("move_to", "Navigate to a target location."),
            Capability("avoid", "Add a persistent avoid-region."),
        ])

    def test_get_known_ipl_type(self):
        """get() returns the registered capability for a known ipl_type."""
        self.assertEqual(self.registry.get("move_to").ipl_type, "move_to")

    def test_get_unknown_ipl_type_returns_none(self):
        """get() returns None for an ipl_type that isn't registered."""
        self.assertIsNone(self.registry.get("fly"))

    def test_describe_lists_every_capability(self):
        """The registry's describe() mentions every registered capability."""
        description = self.registry.describe()
        self.assertIn("move_to", description)
        self.assertIn("avoid", description)


class TestBindingProblems(unittest.TestCase):
    """find_primitive_problems()/find_binding_problems(): the graph-only mirror of Backseater's bind-time check."""
    def setUp(self):
        """Build a move_to registry (target, tolerance -> arrived) and matching declared knowledge."""
        self.registry = CapabilityRegistry([Capability(
            "move_to", "d",
            inputs=(ParamSpec("target", Location, "t"), ParamSpec("tolerance", float, "m")),
            outputs=(ParamSpec("arrived", bool, "a"),))])
        self.knowledge = {"goal": {"type": Location, "value": Location(1.0, 2.0)},
                          "tolerance": {"type": float, "value": 1.0}, "arrived": {"type": bool, "value": False}}

    def _problems(self, inputs, outputs=None, capability="move_to", knowledge=None):
        """Return find_primitive_problems() for one primitive, defaulting to the setUp knowledge."""
        primitive = {"capability": capability, "inputs": inputs, "outputs": outputs or {}}
        return find_primitive_problems(primitive, self.knowledge if knowledge is None else knowledge, self.registry)

    def test_a_correct_binding_has_no_problems(self):
        """A primitive bound to declared keys of the right types reports no problems."""
        self.assertEqual(self._problems({"target": "goal", "tolerance": "tolerance"}, {"arrived": "arrived"}), [])

    def test_undeclared_key_is_reported_with_the_fix(self):
        """Binding to an undeclared key yields one problem naming the key and telling to declare it first."""
        knowledge = {key: value for key, value in self.knowledge.items() if key != "tolerance"}
        problems = self._problems({"target": "goal", "tolerance": "tolerance"}, knowledge=knowledge)
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

    def test_graph_level_check_names_the_node_and_primitive_and_skips_an_unknown_registry(self):
        """find_binding_problems() prefixes each problem with node and primitive, and returns none without a registry."""
        graph = {"knowledge": self.knowledge, "start": "n1", "edges": {},
                 "nodes": {"n1": {"primitives": {"go": {"capability": "move_to", "inputs": {"target": "goal"}, "outputs": {}}}}}}
        problems = find_binding_problems(graph, self.registry)
        self.assertTrue(problems[0].startswith("node 'n1' primitive 'go':"))
        self.assertEqual(find_binding_problems(graph, None), [])


if __name__ == "__main__":
    unittest.main()
