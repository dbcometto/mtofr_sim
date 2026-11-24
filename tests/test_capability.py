"""Tests for capabilities: ParamSpec/Capability description, a running Capability's
read()/write() binding resolution, and the registry of Capability classes."""
import unittest

from mtofr.core.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import Location


class _MoveTo(Capability):
    """A declaration-only move_to with one input and one output."""
    ipl_type = "move_to"
    description = "Navigate to a target location."
    inputs = (ParamSpec("target", Location, "Location to navigate to"),)
    outputs = (ParamSpec("arrived", bool, "True once within tolerance"), ParamSpec("distance", float, "m left"))


class _Avoid(Capability):
    """A declaration-only avoid with no fields."""
    ipl_type = "avoid"
    description = "Add a persistent avoid-region."


class _FakeBackseater:
    """Records publishes and answers queries from a plain dict."""
    def __init__(self, knowledge: dict):
        """Serve `knowledge` (key -> value) to query()."""
        self.knowledge = knowledge
        self.published = []

    def query(self, database_name: str, key: str):
        """The value at `key`."""
        return self.knowledge[key]

    def publish(self, database_name: str, key: str, value) -> None:
        """Record the publish."""
        self.published.append((key, value))


class _FakeFrontseater:
    """Just a backseater attribute, all a Capability's read()/write() need."""
    def __init__(self, backseater: _FakeBackseater):
        """Hold `backseater`."""
        self.backseater = backseater


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
        """A running _MoveTo whose target is bound and only `arrived` is bound among its outputs."""
        self.backseater = _FakeBackseater({"goal": Location(1.0, 2.0)})
        request = {"capability": "move_to", "inputs": {"target": "goal"}, "outputs": {"arrived": "done"}}
        self.capability = _MoveTo(_FakeFrontseater(self.backseater), "nav", request)

    def test_describe_includes_inputs_and_outputs(self):
        """describe() (a classmethod) names the capability and its input and output fields."""
        description = _MoveTo.describe()
        self.assertIn("move_to", description)
        self.assertIn("target", description)
        self.assertIn("arrived", description)

    def test_read_queries_the_bound_key(self):
        """read() returns the current value of the Knowledge key the input is bound to."""
        self.assertEqual(self.capability.read("target").x, 1.0)

    def test_read_of_an_undeclared_input_raises(self):
        """read() of a field the capability doesn't declare as an input raises KeyError."""
        with self.assertRaises(KeyError):
            self.capability.read("arrived")

    def test_write_publishes_to_the_bound_key(self):
        """write() publishes to the Knowledge key the output is bound to."""
        self.capability.write("arrived", True)
        self.assertEqual(self.backseater.published, [("done", True)])

    def test_write_of_an_unbound_output_is_a_no_op(self):
        """write() of a declared output the request leaves unbound publishes nothing."""
        self.capability.write("distance", 3.0)
        self.assertEqual(self.backseater.published, [])

    def test_write_of_an_undeclared_output_raises(self):
        """write() of a field the capability doesn't declare as an output raises KeyError."""
        with self.assertRaises(KeyError):
            self.capability.write("target", 1.0)

    def test_default_status_is_running(self):
        """A capability that doesn't override status() reports "running"."""
        self.assertEqual(self.capability.status(), "running")


class TestCapabilityRegistry(unittest.TestCase):
    def setUp(self):
        """Build a registry holding the _MoveTo and _Avoid classes."""
        self.registry = CapabilityRegistry([_MoveTo, _Avoid])

    def test_get_known_ipl_type(self):
        """get() returns the registered Capability class for a known ipl_type."""
        self.assertIs(self.registry.get("move_to"), _MoveTo)

    def test_get_unknown_ipl_type_returns_none(self):
        """get() returns None for an ipl_type that isn't registered."""
        self.assertIsNone(self.registry.get("fly"))

    def test_describe_lists_every_capability(self):
        """The registry's describe() mentions every registered capability."""
        description = self.registry.describe()
        self.assertIn("move_to", description)
        self.assertIn("avoid", description)

    def test_a_class_without_an_ipl_type_is_refused(self):
        """A Capability subclass that never declares ipl_type can't be registered."""
        class Undeclared(Capability):
            """Forgot its declaration."""
        with self.assertRaises(TypeError):
            CapabilityRegistry([Undeclared])


if __name__ == "__main__":
    unittest.main()
