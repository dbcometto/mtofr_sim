"""Defines the mission-editor "interface" platform's Frontseater."""
from typing import Callable, Optional

from mtofr.core.capability import Capability, CapabilityRegistry
from mtofr.core.state import State
from mtofr.environments.anywhere.platforms.interface.hardware import ConsoleHardware
from mtofr.environments.anywhere.platforms.interface.web.host import WebHost
from mtofr.environments.anywhere.platforms.interface.web.panels import default_panels
from mtofr.environments.anywhere.platforms.interface.web.server import start_web_interface_server
from mtofr.platform.frontseater import Frontseater


class _NullWindow:
    """Stand-in for MissionEditorWindow when running headless (no Tk root exists) --
    lets show_interface start/stop without crashing, with nothing actually shown."""
    def close(self) -> None:
        """Nothing to close."""


class MissionEditorFrontseater(Frontseater):
    """Hosts the mission-editor UIs as side effects of its two capabilities, rather than
    modeling graph-editing itself as capabilities: editing is entirely user-driven, not
    part of the mission-graph/capability machinery any other platform uses.
    - show_interface opens the Tk MissionEditorWindow (see the sibling mission_editor
      package). It is a sim-only direct path: it reads World and writes other platforms'
      Backseaters itself.
    - serve_web_interface runs the web UI (see the sibling web package), which reads and
      writes only through this platform's own Backseater, so it carries over to hardware.
    Never computes real controls; ConsoleHardware ignores them regardless."""

    def __init__(self, hardware: ConsoleHardware, build_panels: Callable[[], list] = default_panels,
                 debug: bool = False):
        """Registers both capabilities; the window factory comes later, from attach().
        `build_panels` is the web UI's static panel registry (fresh panels per browser window)."""
        self.hardware = hardware
        self.backseater = None   # set by Backseater's constructor
        self.debug = debug
        self._build_panels = build_panels
        self._request_names = {}   # ipl_type -> the active request name running it, for describe_status()

        self._window = None
        self._window_factory: Optional[Callable[[], object]] = None

        self._web_host: Optional[WebHost] = None
        self._web_server = None
        self._web_server_factory: Callable[[WebHost], object] = start_web_interface_server
        self._web_start_error: Optional[str] = None   # why the last serve_web_interface start failed, if it did

        self._capability_registry = CapabilityRegistry([
            Capability(
                ipl_type="show_interface",
                description="Opens the Tk mission-editor window while active; closes it when stopped.",
            ),
            Capability(
                ipl_type="serve_web_interface",
                description="Serves the mission-editor web UI while active; stops the server when stopped.",
            ),
        ])

    #===============# UI Wiring #===============#

    def set_window_factory(self, window_factory: Callable[[], object]) -> None:
        """Supplies the callable that builds this platform's Tk window -- normally
        called by attach() rather than directly; tests use it to inject a fake."""
        self._window_factory = window_factory

    def set_web_server_factory(self, web_server_factory: Callable[[WebHost], object]) -> None:
        """Replaces the callable that serves a WebHost (anything with .url and .close());
        defaults to start_web_interface_server, and tests use this to inject a fake."""
        self._web_server_factory = web_server_factory

    def attach(self, world, window_root=None) -> None:
        """Installs the Tk window factory, now that World and (unless headless) the
        dashboard's Tk root exist: a real MissionEditorWindow under window_root,
        or a do-nothing _NullWindow when window_root is None. The web UI needs
        neither, so it is unaffected."""
        if window_root is None:
            self.set_window_factory(_NullWindow)
            return
        # NOTE: imported here rather than at module top: window.py pulls in Tk/matplotlib
        # (and forces the TkAgg backend), which a headless run never needs.
        from mtofr.environments.anywhere.platforms.interface.mission_editor.window import MissionEditorWindow
        self.set_window_factory(lambda: MissionEditorWindow(window_root, world, self.platform_id))





    #===============# Capability Discovery #===============#

    def capabilities(self) -> CapabilityRegistry:
        """show_interface and serve_web_interface."""
        return self._capability_registry

    def default_mission_graph(self) -> dict:
        """Always active: a single node with no edges, serving the web UI
        unconditionally (the "interface platform" pattern)."""
        return {
            "knowledge": {},
            "nodes": {"operating": {"capabilities": {
                "web_interface": {"capability": "serve_web_interface", "inputs": {}, "outputs": {}},
            }}},
            "edges": {},
            "start": "operating",
        }





    #===============# Capability Lifecycle #===============#

    def set_active_capabilities(self, capability_requests: dict) -> None:
        """The one entry point Backseater calls -- diffs by which capabilities are requested
        (whatever the requests are named), opening/closing the window and starting/stopping
        the web server rather than running anything per-tick."""
        self._request_names = {request["capability"]: name for name, request in capability_requests.items()}
        self._set_window_open("show_interface" in self._request_names)
        self._set_web_interface_serving("serve_web_interface" in self._request_names)

    def _set_window_open(self, showing: bool) -> None:
        """Opens or closes the Tk window to match `showing`."""
        if showing and self._window is None:
            if self._window_factory is None:
                raise RuntimeError(
                    "MissionEditorFrontseater has no window_factory set -- call attach() first"
                )
            self._window = self._window_factory()
            if self.debug:
                print("[Frontseater] show_interface -> window opened")
        elif not showing and self._window is not None:
            self._window.close()
            self._window = None
            if self.debug:
                print("[Frontseater] show_interface -> window closed")

    def _set_web_interface_serving(self, serving: bool) -> None:
        """Starts or stops the web server to match `serving`. A start failure (e.g. the port
        is taken) is reported in describe_status() rather than raised, so it can't halt the
        interface platform's mission."""
        if serving and self._web_server is None:
            web_host = WebHost(self.platform_id, self._build_panels)
            try:
                self._web_server = self._web_server_factory(web_host)
            except OSError as error:
                self._web_start_error = str(error)
                print(f"[Frontseater] serve_web_interface failed to start: {error}")
                return
            self._web_host, self._web_start_error = web_host, None
            if self.debug:
                print(f"[Frontseater] serve_web_interface -> serving at {self._web_server.url}")
        elif not serving:
            self._close_web_interface()

    def _close_web_interface(self) -> None:
        """Stops the web server, if running."""
        if self._web_server is not None:
            self._web_server.close()
            if self.debug:
                print("[Frontseater] serve_web_interface -> server stopped")
        self._web_server, self._web_host, self._web_start_error = None, None, None





    #===============# Status Introspection #===============#

    def describe_status(self) -> dict:
        """One overall phrase and one request status per running UI, else "idle"."""
        overall_parts = []
        request_statuses = {}
        if self._window is not None:
            overall_parts.append("showing interface")
            request_statuses[self._request_names.get("show_interface")] = "open"
        if self._web_server is not None:
            overall_parts.append(f"serving web interface at {self._web_server.url}")
            request_statuses[self._request_names.get("serve_web_interface")] = f"serving at {self._web_server.url}"
        elif self._web_start_error is not None:
            overall_parts.append("web interface failed to start")
            request_statuses[self._request_names.get("serve_web_interface")] = f"failed: {self._web_start_error}"
        return {"overall": "; ".join(overall_parts) or "idle", "capabilities": request_statuses}





    #===============# Controls #===============#

    def compute_controls(self, state: State) -> dict:
        """No controls: the console never moves."""
        return {}

    def begin_update(self) -> None:
        """Hands the web UI its tick first -- the one place its queued writes run and its
        view of this platform's databases is refreshed, on the sim thread -- then
        computes (no) controls as usual."""
        if self._web_host is not None:
            self._web_host.on_tick(self.backseater)
        super().begin_update()





    #===============# Lifecycle #===============#

    def shutdown(self) -> None:
        """Closes the window and stops the web server, if either is running, since Tk
        widgets should be destroyed (and the port released) before interpreter exit.
        Platform.shutdown() calls shutdown() on every Frontseater at exit, so this must
        exist."""
        if self._window is not None:
            self._window.close()
            self._window = None
        self._close_web_interface()
