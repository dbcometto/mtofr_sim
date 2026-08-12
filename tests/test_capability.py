"""Tests for the capability registry: ParamSpec/Capability validation and description."""
import unittest

from mtofr.capability.capability import Capability, ParamSpec, CapabilityRegistry
from mtofr.memory.memory import Location


class TestCapability(unittest.TestCase):
    def setUp(self):
        self.move_to = Capability(
            ipl_type="move_to",
            description="Navigate to a target location.",
            params=(ParamSpec("target", Location, "Location to navigate to", is_memory_ref=True),),
        )

    def test_validate_accepts_correct_types(self):
        self.move_to.validate({"target": Location(1.0, 2.0)})   # should not raise

    def test_validate_rejects_missing_param(self):
        with self.assertRaises(ValueError):
            self.move_to.validate({})

    def test_validate_rejects_wrong_type(self):
        with self.assertRaises(ValueError):
            self.move_to.validate({"target": (1.0, 2.0)})   # tuple, not a Location

    def test_describe_includes_memory_entry_description(self):
        description = self.move_to.describe()
        self.assertIn("move_to", description)
        self.assertIn(Location.describe(), description)


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
