"""Defines WebInterfaceServer: a stdlib HTTP server in front of one WebHost.

Routes:
- GET  /                               the page (static/index.html)
- GET  /static/<file>                  the page's own files (an allowlist, no path traversal)
- GET  /panels/<name>.js               a panel's JavaScript half (its script_path)
- GET  /panels/<name>/assets/<file>    a file the panel serves itself (WebPanel.asset()), e.g. a map image
- GET  /api/panels                     [{"name", "title"}, ...]
- GET  /api/state                      WebHost.state()
- POST /api/target                     {"platform_id"}
- POST /api/panels/<name>/<command>    the command's arguments as a JSON object
Every /api/ request except /api/panels carries the window's session id in an X-Session-Id
header. Bad requests (including a missing or malformed session id) get 400 and unknown
routes 404, each with a JSON {"ok": false, "message"}."""
import json
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from mtofr.environments.ground_plane.platforms.interface.web.config import (
    OPEN_BROWSER_ON_START, STATIC_DIRECTORY, WEB_HOST, WEB_PORT,
)
from mtofr.environments.ground_plane.platforms.interface.web.host import WebHost
from mtofr.environments.ground_plane.platforms.interface.web.panel import UnknownCommandError


#========================================#
# Config
#========================================#

INDEX_FILE = "index.html"
PANEL_SCRIPT_PREFIX = "/panels/"
PANEL_SCRIPT_SUFFIX = ".js"
PANEL_ASSET_SEGMENT = "assets"   # /panels/<name>/assets/<file>
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}
DEFAULT_CONTENT_TYPE = "application/octet-stream"
SESSION_HEADER = "X-Session-Id"
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9-]{1,64}")   # what the page generates (a UUID), with room to spare

# Every file under static/, as its URL-relative posix path: the only files GET /static/ serves
STATIC_FILES = {path.relative_to(STATIC_DIRECTORY).as_posix(): path
                for path in STATIC_DIRECTORY.rglob("*") if path.is_file()}

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500







#========================================#
# Server
#========================================#

class _HttpServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that never blocks shutdown on an in-flight request."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, address: tuple, web_host: WebHost):
        """Binds `address` (raising OSError if it's taken) and holds the WebHost the handler serves."""
        self.web_host = web_host
        super().__init__(address, _RequestHandler)


class WebInterfaceServer:
    """Serves one WebHost on a background thread, from construction until close()."""

    def __init__(self, web_host: WebHost, host: str = WEB_HOST, port: int = WEB_PORT):
        """Binds and starts serving; raises OSError if the address is taken. Port 0 picks a free port (see url)."""
        self._http_server = _HttpServer((host, port), web_host)
        self._thread = threading.Thread(target=self._http_server.serve_forever, name="web-interface", daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        """The address actually bound, e.g. http://127.0.0.1:8765."""
        host, port = self._http_server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        """Stops serving and releases the port."""
        self._http_server.shutdown()
        self._http_server.server_close()


def start_web_interface_server(web_host: WebHost) -> WebInterfaceServer:
    """The interface Frontseater's default server factory: serves on the configured address,
    announces it, and opens a browser on it if OPEN_BROWSER_ON_START."""
    server = WebInterfaceServer(web_host)
    # NOTE: not gated by a debug flag: the operator needs this address to open the UI.
    print(f"[Frontseater] '{web_host.own_platform_id}' web interface at {server.url}")
    if OPEN_BROWSER_ON_START:
        webbrowser.open(server.url)
    return server







#========================================#
# Request Handling
#========================================#

class _RequestHandler(BaseHTTPRequestHandler):
    """Routes one request to the server's WebHost (see the module docstring for the routes)."""

    def log_message(self, message_format, *args) -> None:
        """Silenced: a per-request log line (about one a second, per open tab) would flood the sim's console."""

    #===============# GET #===============#

    def do_GET(self) -> None:
        """Serves the page, its static files, panel scripts and assets, and the read-only API."""
        path = urlsplit(self.path).path
        web_host = self.server.web_host
        segments = path.strip("/").split("/")
        if path == "/":
            self._send_file(STATIC_FILES[INDEX_FILE])
        elif path.startswith("/static/") and path.removeprefix("/static/") in STATIC_FILES:
            self._send_file(STATIC_FILES[path.removeprefix("/static/")])
        elif path.startswith(PANEL_SCRIPT_PREFIX) and path.endswith(PANEL_SCRIPT_SUFFIX):
            panel = web_host.panels.get(path.removeprefix(PANEL_SCRIPT_PREFIX).removesuffix(PANEL_SCRIPT_SUFFIX))
            if panel is None:
                self._send_json({"ok": False, "message": f"no panel script at {path}"}, HTTP_NOT_FOUND)
            else:
                self._send_file(panel.script_path)
        elif len(segments) == 4 and segments[0] == "panels" and segments[2] == PANEL_ASSET_SEGMENT:
            self._send_panel_asset(segments[1], segments[3])
        elif path == "/api/panels":
            self._send_json(web_host.describe_panels())
        elif path == "/api/state":
            session_id = self._session_id()
            if session_id is not None:
                self._send_json(web_host.state(session_id))
        else:
            self._send_json({"ok": False, "message": f"no such route: GET {path}"}, HTTP_NOT_FOUND)





    #===============# POST #===============#

    def do_POST(self) -> None:
        """Runs a Target change or a panel command, each with a JSON object body."""
        path = urlsplit(self.path).path
        web_host = self.server.web_host
        session_id = self._session_id()
        if session_id is None:
            return
        try:
            arguments = self._read_json_object()
        except ValueError as error:
            self._send_json({"ok": False, "message": str(error)}, HTTP_BAD_REQUEST)
            return

        segments = path.strip("/").split("/")
        try:
            if segments == ["api", "target"]:
                web_host.set_target(session_id, arguments.get("platform_id"))
                self._send_json({"ok": True, "message": f"target is now '{arguments.get('platform_id')}'"})
            elif len(segments) == 4 and segments[:2] == ["api", "panels"]:
                self._send_json(web_host.command(session_id, segments[2], segments[3], arguments))
            else:
                self._send_json({"ok": False, "message": f"no such route: POST {path}"}, HTTP_NOT_FOUND)
        except UnknownCommandError as error:
            self._send_json({"ok": False, "message": str(error)}, HTTP_NOT_FOUND)
        except (TypeError, ValueError) as error:   # bad or missing arguments
            self._send_json({"ok": False, "message": str(error)}, HTTP_BAD_REQUEST)
        # NOTE: anything else is a panel bug; report it to the browser rather than dropping the connection.
        except Exception as error:
            self._send_json({"ok": False, "message": f"internal error: {error}"}, HTTP_SERVER_ERROR)





    #===============# Helpers #===============#

    def _send_panel_asset(self, panel_name: str, asset_name: str) -> None:
        """Serves one panel's own asset against the latest view, or 404s."""
        web_host = self.server.web_host
        panel = web_host.panels.get(panel_name)
        asset = None if panel is None else panel.asset(asset_name, web_host.view)
        if asset is None:
            self._send_json({"ok": False, "message": f"no asset '{asset_name}' for panel '{panel_name}'"}, HTTP_NOT_FOUND)
            return
        body, content_type = asset
        self._send_bytes(body, content_type)

    def _session_id(self) -> str | None:
        """The request's window session id; None (after answering 400) if it's missing or malformed."""
        session_id = self.headers.get(SESSION_HEADER, "")
        if SESSION_ID_PATTERN.fullmatch(session_id) is None:
            self._send_json({"ok": False, "message": f"missing or malformed {SESSION_HEADER} header"}, HTTP_BAD_REQUEST)
            return None
        return session_id

    def _read_json_object(self) -> dict:
        """The request body parsed as a JSON object (an empty body is {}); raises ValueError otherwise."""
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            raise ValueError(f"request body is not valid JSON: {error}")
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    def _send_json(self, payload, status: int = HTTP_OK) -> None:
        """Writes `payload` as a JSON response."""
        self._send_bytes(json.dumps(payload).encode("utf-8"), CONTENT_TYPES[".json"], status)

    def _send_file(self, file_path: Path) -> None:
        """Writes a file, typed by its extension."""
        self._send_bytes(file_path.read_bytes(), CONTENT_TYPES.get(file_path.suffix, DEFAULT_CONTENT_TYPE))

    def _send_bytes(self, body: bytes, content_type: str, status: int = HTTP_OK) -> None:
        """Writes one complete, uncached response."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
