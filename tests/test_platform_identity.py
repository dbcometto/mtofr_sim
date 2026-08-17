"""Tests for the platform_id identity chain: Backseater owns it and it cascades
down through Frontseater to Hardware, so any layer can identify its own platform."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.knowledge.knowledge import Knowledge
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater


class TestPlatformIdentityCascade(unittest.TestCase):
    def test_platform_id_cascades_from_backseater_to_frontseater_and_hardware(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        backseater = Backseater(frontseater=frontseater, knowledge=Knowledge(), platform_id="ugv1")

        self.assertEqual(backseater.platform_id, "ugv1")
        self.assertEqual(frontseater.platform_id, "ugv1")
        self.assertEqual(hardware.platform_id, "ugv1")

    def test_no_platform_id_leaves_hardware_and_frontseater_untouched(self):
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        Backseater(frontseater=frontseater, knowledge=Knowledge())

        self.assertIsNone(frontseater.platform_id)
        self.assertIsNone(hardware.platform_id)

    def test_two_platforms_built_independently_keep_distinct_ids(self):
        hardware_1 = BicycleHardware()
        frontseater_1 = BicycleFrontseater(hardware=hardware_1)
        Backseater(frontseater=frontseater_1, knowledge=Knowledge(), platform_id="ugv1")

        hardware_2 = BicycleHardware()
        frontseater_2 = BicycleFrontseater(hardware=hardware_2)
        Backseater(frontseater=frontseater_2, knowledge=Knowledge(), platform_id="ugv2")

        self.assertEqual(hardware_1.platform_id, "ugv1")
        self.assertEqual(hardware_2.platform_id, "ugv2")


if __name__ == "__main__":
    unittest.main()