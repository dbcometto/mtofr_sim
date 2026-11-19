"""Tests for the platform_id identity chain: Backseater owns it and it cascades
down through Frontseater to Hardware, so any layer can identify its own platform."""
import unittest

from mtofr.database import KnowledgeDatabase
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater
from mtofr.platform.backseater import Backseater


class TestPlatformIdentityCascade(unittest.TestCase):
    def test_platform_id_cascades_from_backseater_to_frontseater_and_hardware(self):
        """A platform_id given to the Backseater is set on its Frontseater and Hardware too."""
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        backseater = Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

        self.assertEqual(backseater.platform_id, "ugv1")
        self.assertEqual(frontseater.platform_id, "ugv1")
        self.assertEqual(hardware.platform_id, "ugv1")

    def test_no_platform_id_leaves_hardware_and_frontseater_untouched(self):
        """Without a platform_id, the Frontseater and Hardware keep platform_id None."""
        hardware = BicycleHardware()
        frontseater = BicycleFrontseater(hardware=hardware)
        self.addCleanup(frontseater.shutdown)
        Backseater(frontseater=frontseater, knowledge_database=KnowledgeDatabase())

        self.assertIsNone(frontseater.platform_id)
        self.assertIsNone(hardware.platform_id)

    def test_two_platforms_built_independently_keep_distinct_ids(self):
        """Two separately built stacks each keep their own platform_id on their Hardware."""
        hardware_1 = BicycleHardware()
        frontseater_1 = BicycleFrontseater(hardware=hardware_1)
        self.addCleanup(frontseater_1.shutdown)
        Backseater(frontseater=frontseater_1, knowledge_database=KnowledgeDatabase(), platform_id="ugv1")

        hardware_2 = BicycleHardware()
        frontseater_2 = BicycleFrontseater(hardware=hardware_2)
        self.addCleanup(frontseater_2.shutdown)
        Backseater(frontseater=frontseater_2, knowledge_database=KnowledgeDatabase(), platform_id="ugv2")

        self.assertEqual(hardware_1.platform_id, "ugv1")
        self.assertEqual(hardware_2.platform_id, "ugv2")


if __name__ == "__main__":
    unittest.main()