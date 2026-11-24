"""The interface platform's capabilities: each hosts one mission-editor UI while it runs."""
from mtofr.core.capability import Capability
from mtofr.environments.anywhere.platforms.interface.web.host import WebHost


class ShowInterface(Capability):
    """Opens the Tk mission-editor window while running; closes it when stopped."""
    ipl_type = "show_interface"
    description = "Opens the Tk mission-editor window while active; closes it when stopped."

    def start(self) -> None:
        """Opens the window through the Frontseater's window factory (installed by attach())."""
        if self.frontseater.window_factory is None:
            raise RuntimeError("MissionEditorFrontseater has no window_factory set -- call attach() first")
        self.window = self.frontseater.window_factory()

    def stop(self) -> None:
        """Closes the window."""
        self.window.close()

    def status(self) -> str:
        """Always "open"."""
        return "open"


class ServeWebInterface(Capability):
    """Serves the mission-editor web UI while running; stops the server when stopped."""
    ipl_type = "serve_web_interface"
    description = "Serves the mission-editor web UI while active; stops the server when stopped."

    def start(self) -> None:
        """Starts the server.  A start failure (e.g. the port is taken) is reported in
        status() rather than raised, so it can't halt the interface platform's mission."""
        self.web_host = WebHost(self.frontseater.platform_id, self.frontseater.build_panels)
        self.web_server = None
        self.start_error = None   # why the server failed to start, if it did
        try:
            self.web_server = self.frontseater.web_server_factory(self.web_host)
        except OSError as error:
            self.start_error = str(error)
            print(f"[Frontseater] serve_web_interface failed to start: {error}")
            return
        if self.frontseater.debug:
            print(f"[Frontseater] serve_web_interface -> serving at {self.web_server.url}")

    def tick(self) -> None:
        """Hands the web UI its tick: the one place its queued writes run and its view of
        this platform's databases is refreshed, on the sim thread."""
        if self.web_server is not None:
            self.web_host.on_tick(self.frontseater.backseater)

    def stop(self) -> None:
        """Stops the server, if it started."""
        if self.web_server is not None:
            self.web_server.close()

    def status(self) -> str:
        """The URL served, or why it failed."""
        if self.web_server is None:
            return f"failed: {self.start_error}"
        return f"serving at {self.web_server.url}"
