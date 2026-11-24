"""Tests for MissionEditorFrontseater: opens/closes a window and starts/stops a web
server (each via an injected factory) as its two capabilities, show_interface and
serve_web_interface, start/stop -- rather than running anything per-tick like a normal
capability -- and hands the web UI its tick. No real Tk window or server is involved;
fakes stand in for MissionEditorWindow and WebInterfaceServer."""
import unittest

from mtofr.core.clock import Clock
from mtofr.database import KnowledgeDatabase, MissionDatabase, PlatformDatabase
from mtofr.environments.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.environments.anywhere.platforms.interface.frontseater import MissionEditorFrontseater

_WEB_REQUESTS = {"web_interface": {"capability": "serve_web_interface", "inputs": {}, "outputs": {}}}
_FAKE_URL = "http://fake:1"


class _FakeWindow:
    """Stands in for MissionEditorWindow, recording whether close() was called."""
    def __init__(self):
        """Start open."""
        self.closed = False

    def close(self):
        """Record that the window was closed."""
        self.closed = True


class _FakeWebServer:
    """Stands in for WebInterfaceServer: holds the WebHost it was given, records close()."""
    url = _FAKE_URL

    def __init__(self, web_host):
        """Start serving `web_host` (nothing actually listens)."""
        self.web_host = web_host
        self.closed = False

    def close(self):
        """Record that the server was stopped."""
        self.closed = True


class _FakeBackseater:
    """Just enough of a Backseater for WebHost.on_tick() to capture a view."""
    platform_id = "interface"

    def __init__(self):
        """Empty databases and a clock."""
        self.clock = Clock()
        self.knowledge_database = KnowledgeDatabase()
        self.mission_database = MissionDatabase()
        self.platform_database = PlatformDatabase()

    def last_sync_times(self) -> dict:
        """No peers synced yet."""
        return {}


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

    def _build_web_server(self, web_host):
        """Web server factory: build a fake server and record it."""
        server = _FakeWebServer(web_host)
        self.web_servers_built.append(server)
        return server

    def _use_fake_web_server(self):
        """Installs the recording fake web server factory."""
        self.web_servers_built = []
        self.frontseater.set_web_server_factory(self._build_web_server)

    def test_capabilities_advertises_show_interface_and_serve_web_interface(self):
        """The registry contains both UI capabilities."""
        self.assertIsNotNone(self.frontseater.capabilities().get("show_interface"))
        self.assertIsNotNone(self.frontseater.capabilities().get("serve_web_interface"))

    def test_default_mission_graph_always_runs_only_the_web_interface_with_no_edges(self):
        """The default graph's start node runs serve_web_interface alone and the graph has no edges."""
        graph = self.frontseater.default_mission_graph()
        capability_requests = graph["nodes"][graph["start"]]["capabilities"]
        self.assertEqual([request["capability"] for request in capability_requests.values()], ["serve_web_interface"])
        self.assertEqual(graph["edges"], {})

    #===============# serve_web_interface #===============#

    def test_starting_serve_web_interface_starts_a_server_and_stopping_closes_it(self):
        """Activating serve_web_interface builds one server; deactivating it closes that server."""
        self._use_fake_web_server()
        self.frontseater.set_active_capabilities(_WEB_REQUESTS)
        self.assertEqual(len(self.web_servers_built), 1)
        self.frontseater.set_active_capabilities({})
        self.assertTrue(self.web_servers_built[0].closed)

    def test_both_capabilities_run_side_by_side(self):
        """A node requesting both opens the window and starts the server, and the status names both."""
        self._use_fake_web_server()
        self.frontseater.set_active_capabilities({
            "interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}, **_WEB_REQUESTS,
        })
        self.assertEqual((len(self.windows_built), len(self.web_servers_built)), (1, 1))
        status = self.frontseater.describe_status()
        self.assertEqual(status["overall"], f"showing interface; serving web interface at {_FAKE_URL}")
        self.assertEqual(status["capabilities"], {"interface": "open", "web_interface": f"serving at {_FAKE_URL}"})

    def test_a_server_start_failure_is_reported_not_raised(self):
        """An OSError from the server factory (e.g. port taken) shows in describe_status() instead of propagating."""
        def failing_factory(web_host):
            """Fail the way a taken port does."""
            raise OSError("address already in use")
        self.frontseater.set_web_server_factory(failing_factory)
        self.frontseater.set_active_capabilities(_WEB_REQUESTS)   # must not raise
        status = self.frontseater.describe_status()
        self.assertEqual(status["overall"], "web interface failed to start")
        self.assertIn("address already in use", status["capabilities"]["web_interface"])

    def test_begin_update_hands_the_web_host_its_tick(self):
        """While serving, begin_update() runs the WebHost's tick: its queued writes run against this platform's Backseater."""
        self._use_fake_web_server()
        self.frontseater.backseater = _FakeBackseater()
        self.frontseater.set_active_capabilities(_WEB_REQUESTS)
        web_host = self.web_servers_built[0].web_host
        seen = []
        web_host.queue_write("probe", lambda backseater: seen.append(backseater) or "ran", log=lambda message: None)
        self.frontseater.begin_update()
        self.assertEqual(seen, [self.frontseater.backseater])

    def test_shutdown_stops_a_running_server(self):
        """shutdown() closes a running web server."""
        self._use_fake_web_server()
        self.frontseater.set_active_capabilities(_WEB_REQUESTS)
        self.frontseater.shutdown()
        self.assertTrue(self.web_servers_built[0].closed)

    #===============# show_interface #===============#

    def test_starting_show_interface_opens_a_window(self):
        """Activating show_interface builds one window."""
        self.frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(len(self.windows_built), 1)

    def test_starting_show_interface_twice_does_not_open_a_second_window(self):
        """Re-sending an equal capability requests dict leaves the existing window and builds no second one."""
        capability_requests = {"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}}
        self.frontseater.set_active_capabilities(capability_requests)
        self.frontseater.set_active_capabilities(dict(capability_requests))
        self.assertEqual(len(self.windows_built), 1)

    def test_stopping_show_interface_closes_the_window(self):
        """Deactivating show_interface closes its window."""
        self.frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        window = self.windows_built[0]
        self.frontseater.set_active_capabilities({})
        self.assertTrue(window.closed)

    def test_describe_status_reflects_window_state(self):
        """Overall status reads "idle" with no window and "showing interface" with one open."""
        self.assertEqual(self.frontseater.describe_status()["overall"], "idle")
        self.frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(self.frontseater.describe_status()["overall"], "showing interface")

    def test_starting_without_a_window_factory_raises(self):
        """Activating show_interface before any window factory is installed raises RuntimeError."""
        frontseater = MissionEditorFrontseater(hardware=ConsoleHardware())
        with self.assertRaises(RuntimeError):
            frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})

    def test_shutdown_closes_an_open_window(self):
        """shutdown() closes a window that is open."""
        self.frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
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
        frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(frontseater.describe_status()["overall"], "showing interface")
        frontseater.set_active_capabilities({})   # the null window's close() must not raise
        self.assertEqual(frontseater.describe_status()["overall"], "idle")

    def test_attach_with_a_window_root_builds_a_mission_editor_window_from_it(self):
        """attach() with a window root builds MissionEditorWindow from that root, the world, and the platform id."""
        import mtofr.environments.anywhere.platforms.interface.mission_editor.window as window_module
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
        frontseater.set_active_capabilities({"interface": {"capability": "show_interface", "inputs": {}, "outputs": {}}})
        self.assertEqual(built_with, [("root", world, "interface")])


if __name__ == "__main__":
    unittest.main()