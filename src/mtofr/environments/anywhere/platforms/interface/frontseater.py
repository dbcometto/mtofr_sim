"""Defines the mission-editor "interface" platform's Frontseater."""
from typing import Callable, Optional

from mtofr.environments.anywhere.platforms.interface.capabilities import ServeWebInterface, ShowInterface
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
    CAPABILITIES = (ShowInterface, ServeWebInterface)

    def __init__(self, hardware: ConsoleHardware, build_panels: Callable[[], list] = default_panels,
                 debug: bool = False):
        """The window factory comes later, from attach().  `build_panels` is the web UI's
        static panel registry (fresh panels per browser window)."""
        super().__init__(hardware, debug)
        self.build_panels = build_panels
        self.window_factory: Optional[Callable[[], object]] = None   # used by ShowInterface
        self.web_server_factory: Callable[[WebHost], object] = start_web_interface_server   # used by ServeWebInterface

    #===============# UI Wiring #===============#

    def set_window_factory(self, window_factory: Callable[[], object]) -> None:
        """Supplies the callable that builds this platform's Tk window -- normally
        called by attach() rather than directly; tests use it to inject a fake."""
        self.window_factory = window_factory

    def set_web_server_factory(self, web_server_factory: Callable[[WebHost], object]) -> None:
        """Replaces the callable that serves a WebHost (anything with .url and .close());
        defaults to start_web_interface_server, and tests use this to inject a fake."""
        self.web_server_factory = web_server_factory

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
