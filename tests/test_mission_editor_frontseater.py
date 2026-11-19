"""Tests for MissionEditorFrontseater: opens/closes a window (via an injected
factory) as its one capability, show_interface, starts/stops -- rather than
running anything per-tick like a normal capability. No real Tk window is
involved; a fake window stands in for MissionEditorWindow."""
import unittest

from mtofr.world.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.world.anywhere.platforms.interface.frontseater import MissionEditorFrontseater


class _FakeWindow:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class TestMissionEditorFrontseater(unittest.TestCase):
    def setUp(self):
        self.frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        self.windows_built = []
        self.frontseater.set_window_factory(self._build_window)

    def _build_window(self):
        window = _FakeWindow()
        self.windows_built.append(window)
        return window

    def test_capabilities_advertises_show_interface(self):
        self.assertIsNotNone(self.frontseater.capabilities().get("show_interface"))

    def test_default_mission_graph_always_runs_show_interface_with_no_edges(self):
        graph = self.frontseater.default_mission_graph()
        primitives = graph["nodes"][graph["start"]]["primitives"]
        self.assertEqual(next(iter(primitives.values()))["capability"], "show_interface")
        self.assertEqual(graph["edges"], {})

    def test_starting_show_interface_opens_a_window(self):
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(len(self.windows_built), 1)

    def test_starting_show_interface_twice_does_not_open_a_second_window(self):
        primitives = {"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}}
        self.frontseater.set_active_primitives(primitives)
        self.frontseater.set_active_primitives(dict(primitives))
        self.assertEqual(len(self.windows_built), 1)

    def test_stopping_show_interface_closes_the_window(self):
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        window = self.windows_built[0]
        self.frontseater.set_active_primitives({})
        self.assertTrue(window.closed)

    def test_describe_status_reflects_window_state(self):
        self.assertEqual(self.frontseater.describe_status()["overall"], "idle")
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(self.frontseater.describe_status()["overall"], "showing interface")

    def test_starting_without_a_window_factory_raises(self):
        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        with self.assertRaises(RuntimeError):
            frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})

    def test_shutdown_closes_an_open_window(self):
        self.frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        window = self.windows_built[0]
        self.frontseater.shutdown()
        self.assertTrue(window.closed)

    def test_shutdown_with_no_window_open_is_a_no_op(self):
        self.frontseater.shutdown()   # must not raise

    def test_attach_without_a_window_root_installs_a_null_window(self):
        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        frontseater.attach(world=object(), window_root=None)
        frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(frontseater.describe_status()["overall"], "showing interface")
        frontseater.set_active_primitives({})   # the null window's close() must not raise
        self.assertEqual(frontseater.describe_status()["overall"], "idle")

    def test_attach_with_a_window_root_builds_a_mission_editor_window_from_it(self):
        import mtofr.world.anywhere.platforms.interface.mission_editor.window as window_module
        built_with = []
        original_window = window_module.MissionEditorWindow
        window_module.MissionEditorWindow = lambda root, world, platform_id: built_with.append(
            (root, world, platform_id)) or _FakeWindow()
        self.addCleanup(setattr, window_module, "MissionEditorWindow", original_window)

        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        frontseater.platform_id = "interface"
        world = object()
        frontseater.attach(world, window_root="root")
        frontseater.set_active_primitives({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(built_with, [("root", world, "interface")])


if __name__ == "__main__":
    unittest.main()