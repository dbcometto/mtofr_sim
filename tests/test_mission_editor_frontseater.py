"""Tests for MissionEditorFrontseater: opens/closes a window (via an injected
factory) as its one capability, show_interface, starts/stops -- rather than
running anything per-tick like a normal capability. No real Tk window is
involved; a fake window stands in for MissionEditorWindow."""
import unittest

from mtofr.world.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.world.anywhere.platforms.interface.frontseater import MissionEditorFrontseater


class _FakeWindow:
    """Stands in for MissionEditorWindow, recording whether close() was called."""
    def __init__(self):
        """Start open."""
        self.closed = False

    def close(self):
        """Record that the window was closed."""
        self.closed = True


class TestMissionEditorFrontseater(unittest.TestCase):
    def setUp(self):
        """Build a MissionEditorFrontseater whose window factory records every fake window it builds."""
        self.frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        self.windows_built = []
        self.frontseater.set_window_factory(self._build_window)

    def _build_window(self):
        """Window factory: build a fake window and record it."""
        window = _FakeWindow()
        self.windows_built.append(window)
        return window

    def test_capabilities_advertises_show_interface(self):
        """The registry contains show_interface."""
        self.assertIsNotNone(self.frontseater.capabilities().get("show_interface"))

    def test_default_mission_graph_always_runs_show_interface_with_no_edges(self):
        """The default graph's start node runs show_interface and the graph has no edges."""
        graph = self.frontseater.default_mission_graph()
        primitives = graph["nodes"][graph["start"]]["primitives"]
        self.assertEqual(next(iter(primitives.values()))["capability"], "show_interface")
        self.assertEqual(graph["edges"], {})

    def test_starting_show_interface_opens_a_window(self):
        """Activating show_interface builds one window."""
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(len(self.windows_built), 1)

    def test_starting_show_interface_twice_does_not_open_a_second_window(self):
        """Re-sending an equal primitives dict leaves the existing window and builds no second one."""
        primitives = {"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}}
        self.frontseater.set_active_primitives(primitives)
        self.frontseater.set_active_primitives(dict(primitives))
        self.assertEqual(len(self.windows_built), 1)

    def test_stopping_show_interface_closes_the_window(self):
        """Deactivating show_interface closes its window."""
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        window = self.windows_built[0]
        self.frontseater.set_active_primitives({})
        self.assertTrue(window.closed)

    def test_describe_status_reflects_window_state(self):
        """Overall status reads "idle" with no window and "showing interface" with one open."""
        self.assertEqual(self.frontseater.describe_status()["overall"], "idle")
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(self.frontseater.describe_status()["overall"], "showing interface")

    def test_starting_without_a_window_factory_raises(self):
        """Activating show_interface before any window factory is installed raises RuntimeError."""
        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        with self.assertRaises(RuntimeError):
            frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})

    def test_shutdown_closes_an_open_window(self):
        """shutdown() closes a window that is open."""
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        window = self.windows_built[0]
        self.frontseater.shutdown()
        self.assertTrue(window.closed)

    def test_shutdown_with_no_window_open_is_a_no_op(self):
        """shutdown() with no window open does not raise."""
        self.frontseater.shutdown()   # must not raise

    def test_attach_without_a_window_root_installs_a_null_window(self):
        """attach() with no window root installs a null window that opens and closes without raising."""
        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        frontseater.attach(world=object(), window_root=None)
        frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(frontseater.describe_status()["overall"], "showing interface")
        frontseater.set_active_primitives({})   # the null window's close() must not raise
        self.assertEqual(frontseater.describe_status()["overall"], "idle")

    def test_attach_with_a_window_root_builds_a_mission_editor_window_from_it(self):
        """attach() with a window root builds MissionEditorWindow from that root, the world, and the platform id."""
        import mtofr.world.anywhere.platforms.interface.mission_editor.window as window_module
        built_with = []

        def fake_mission_editor_window(root, world, platform_id):
            """Record the constructor arguments and return a fake window."""
            built_with.append((root, world, platform_id))
            return _FakeWindow()

        original_window = window_module.MissionEditorWindow
        window_module.MissionEditorWindow = fake_mission_editor_window
        self.addCleanup(setattr, window_module, "MissionEditorWindow", original_window)

        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        frontseater.platform_id = "interface"
        world = object()
        frontseater.attach(world, window_root="root")
        frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(built_with, [("root", world, "interface")])


if __name__ == "__main__":
    unittest.main()