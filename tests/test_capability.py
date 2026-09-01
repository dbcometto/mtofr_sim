"""Tests for the capability registry: ParamSpec/Capability validation and description."""
import unittest

from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.database import Location


class TestParamSpec(unittest.TestCase):
    def test_describe_includes_knowledge_entry_description_for_a_knowledge_entry_type(self):
        spec = ParamSpec("target", Location, "Location to navigate to")
        description = spec.describe()
        self.assertIn("target", description)
        self.assertIn(Location.describe(), description)

    def test_describe_omits_knowledge_entry_description_for_a_plain_type(self):
        spec = ParamSpec("radius", float, "Avoid-region radius in meters")
        description = spec.describe()
        self.assertIn("radius", description)
        self.assertIn("float", description)


class TestCapability(unittest.TestCase):
    def setUp(self):
        self.move_to = Capability(
            ipl_type="move_to",
            description="Navigate to a target location.",
            inputs=(ParamSpec("target", Location, "Location to navigate to"),),
            outputs=(ParamSpec("arrived", bool, "True once within tolerance"),),
        )

    def test_describe_includes_inputs_and_outputs(self):
        description = self.move_to.describe()
        self.assertIn("move_to", description)
        self.assertIn("target", description)
        self.assertIn("arrived", description)


class TestCapabilityRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry([
            Capability("move_to", "Navigate to a target location."),
            Capability("avoid", "Add a persistent avoid-region."),
        ])

    def test_get_known_ipl_type(self):
        self.assertEqual(self.registry.get("move_to").ipl_type, "move_to")

    def test_get_unknown_ipl_type_returns_none(self):
        self.assertIsNone(self.registry.get("fly"))

    def test_describe_lists_every_capability(self):
        description = self.registry.describe()
        self.assertIn("move_to", description)
        self.assertIn("avoid", description)


if __name__ == "__main__":
    unittest.main()
