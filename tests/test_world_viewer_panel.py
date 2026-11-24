"""Tests for WorldViewerPanel: its state (the sensed map's extent and every Pose in Knowledge)
and its PNG map-layer assets, over hand-built InterfaceViews (no Backseater or server)."""
import unittest

from mtofr.database import Location, Pose
from mtofr.environments.ground_plane.maps.ground_map import TraversabilityType
from mtofr.environments.ground_plane.platforms.interface.web.panel import PanelContext
from mtofr.environments.ground_plane.platforms.interface.web.panels.world_viewer import WorldViewerPanel
from mtofr.environments.ground_plane.platforms.interface.web.view import InterfaceView, KnowledgeRow
from tests.test_ground_plane_env import uniform_ground_map


PNG_SIGNATURE = b"\x89PNG"
CLEAR = TraversabilityType(name="clear", blocking=False, speed_multiplier=1.0)


def _context(view: InterfaceView) -> PanelContext:
    """A PanelContext over `view` that ignores writes and logs."""
    return PanelContext(view=view, target_platform_id=None, submit=lambda description, write: None,
                        log=lambda message: None, editor_store={})


class TestWorldViewerPanel(unittest.TestCase):
    def setUp(self):
        """A panel, and a view holding two poses and one non-pose key."""
        self.panel = WorldViewerPanel()
        self.knowledge = {
            "ugv2/pose": KnowledgeRow(Pose, Pose(3.0, 4.0, 1.5), "ugv2", 9.0),
            "ugv1/pose": KnowledgeRow(Pose, Pose(1.0, 2.0, 0.5), "ugv1", 10.0),
            "ugv1/goal": KnowledgeRow(Location, Location(5.0, 5.0), "ugv1", 10.0),
        }

    def test_state_lists_every_pose_sorted_by_key(self):
        """Only Pose rows appear, with their origin, coordinates, and age (s since written)."""
        view = InterfaceView("interface", time=12.0, knowledge=self.knowledge)
        poses = self.panel.state(_context(view))["poses"]
        self.assertEqual([pose["key"] for pose in poses], ["ugv1/pose", "ugv2/pose"])
        self.assertEqual(poses[0], {"key": "ugv1/pose", "origin": "ugv1", "x": 1.0, "y": 2.0, "theta": 0.5, "age": 2.0})

    def test_state_without_a_map_has_no_map(self):
        """A view with no sensed map gives map None, and no assets."""
        view = InterfaceView("interface", knowledge=self.knowledge)
        self.assertIsNone(self.panel.state(_context(view))["map"])
        self.assertIsNone(self.panel.asset("cosmetic.png", view))

    def test_state_with_a_map_gives_its_extent(self):
        """The map's name and size (m) are what the browser places the images by."""
        view = InterfaceView("interface", ground_map=uniform_ground_map(CLEAR))
        described = self.panel.state(_context(view))["map"]
        self.assertEqual((described["name"], described["width_meters"], described["height_meters"]), ("uniform", 20.0, 20.0))

    def test_every_listed_layer_is_served_as_a_png(self):
        """Each layer the state lists is a PNG asset; an unknown name is None."""
        view = InterfaceView("interface", ground_map=uniform_ground_map(CLEAR))
        for layer in self.panel.state(_context(view))["layers"]:
            body, content_type = self.panel.asset(layer, view)
            self.assertEqual(content_type, "image/png")
            self.assertTrue(body.startswith(PNG_SIGNATURE), layer)
        self.assertIsNone(self.panel.asset("secret.png", view))

    def test_a_new_map_is_encoded_afresh(self):
        """The encoding cache is per map: a different map's layer isn't the old bytes object."""
        first = self.panel.asset("cosmetic.png", InterfaceView("interface", ground_map=uniform_ground_map(CLEAR)))[0]
        again = self.panel.asset("cosmetic.png", InterfaceView("interface", ground_map=uniform_ground_map(CLEAR)))[0]
        self.assertIsNot(first, again)


if __name__ == "__main__":
    unittest.main()
