"""Tests for WebInterfaceServer's routing: a real server on a free port (port 0), driven
over raw HTTP (http.client, so paths reach the server exactly as written), in front of a
WebHost with the built-in panels and no ticks yet (an empty view)."""
import http.client
import json
import unittest
from urllib.parse import urlsplit

from mtofr.environments.anywhere.platforms.interface.web.host import WebHost
from mtofr.environments.anywhere.platforms.interface.web.panels import default_panels
from mtofr.environments.anywhere.platforms.interface.web.server import SESSION_HEADER, WebInterfaceServer

HOST = "127.0.0.1"
FREE_PORT = 0   # lets the OS pick
TIMEOUT_SECONDS = 5
SESSION = "3f1c2a9e-7b4d-4e1a-9c2b-5d6e7f8a9b0c"   # shaped like the page's crypto.randomUUID()


class TestWebInterfaceServer(unittest.TestCase):
    def setUp(self):
        """Serve a fresh WebHost on a free port, closed after each test."""
        self.web_host = WebHost("interface", default_panels)
        self.server = WebInterfaceServer(self.web_host, host=HOST, port=FREE_PORT)
        self.addCleanup(self.server.close)
        self.port = urlsplit(self.server.url).port

    def _request(self, method: str, path: str, body: bytes = None, session_id: str | None = SESSION) -> tuple:
        """Sends one request with `path` verbatim, as `session_id` (None sends no session header);
        returns (status, content type, body bytes)."""
        connection = http.client.HTTPConnection(HOST, self.port, timeout=TIMEOUT_SECONDS)
        self.addCleanup(connection.close)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if session_id is not None:
            headers[SESSION_HEADER] = session_id
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()

    def _post_json(self, path: str, payload) -> tuple:
        """POSTs `payload` as JSON; returns (status, parsed reply)."""
        status, _, body = self._request("POST", path, json.dumps(payload).encode())
        return status, json.loads(body)

    #===============# GET #===============#

    def test_root_serves_the_page(self):
        """GET / is the HTML page."""
        status, content_type, body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertTrue(content_type.startswith("text/html"))
        self.assertIn(b"<title>", body)

    def test_static_files_and_panel_scripts_are_served(self):
        """The page's own script and a panel's script are served as JavaScript."""
        for path in ("/static/app.js", "/panels/graph.js"):
            status, content_type, _ = self._request("GET", path)
            self.assertEqual(status, 200, path)
            self.assertTrue(content_type.startswith("text/javascript"), path)

    def test_paths_outside_the_allowlist_are_not_found(self):
        """Traversal out of static/, an unknown panel script, and an unknown route are all 404s."""
        for path in ("/static/../server.py", "/static/%2e%2e/server.py", "/panels/nope.js", "/nowhere"):
            status, _, _ = self._request("GET", path)
            self.assertEqual(status, 404, path)

    def test_api_lists_the_panels_in_tab_order(self):
        """GET /api/panels names every default panel, in order: the graph editor first, then Live Control."""
        _, _, body = self._request("GET", "/api/panels")
        self.assertEqual([panel["name"] for panel in json.loads(body)], ["graph", "live_control"])

    def test_api_state_is_json(self):
        """GET /api/state returns WebHost.state() as JSON."""
        status, content_type, body = self._request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(content_type.startswith("application/json"))
        self.assertEqual(json.loads(body)["own_platform_id"], "interface")

    #===============# POST #===============#

    def test_a_panel_command_round_trips(self):
        """POSTing a graph edit changes the draft that the next GET /api/state shows."""
        status, reply = self._post_json("/api/panels/graph/edit", {"tool": "add_node", "arguments": {"node_id": "patrol"}})
        self.assertEqual(status, 200)
        self.assertTrue(reply["ok"], reply["message"])
        _, _, body = self._request("GET", "/api/state")
        self.assertIn("patrol", json.loads(body)["panels"]["graph"]["draft"]["nodes"])

    def test_bad_bodies_and_arguments_are_bad_requests(self):
        """Invalid JSON, a non-object body, missing arguments, and an unknown Target are all 400s."""
        status, _, _ = self._request("POST", "/api/panels/graph/undo", b"{not json")
        self.assertEqual(status, 400)
        self.assertEqual(self._post_json("/api/panels/graph/undo", [1, 2])[0], 400)
        self.assertEqual(self._post_json("/api/panels/graph/edit", {})[0], 400)
        self.assertEqual(self._post_json("/api/target", {"platform_id": "ugv9"})[0], 400)

    def test_a_missing_or_malformed_session_id_is_a_bad_request(self):
        """State and commands need a well-formed X-Session-Id; the panel list (loaded before any session) doesn't."""
        self.assertEqual(self._request("GET", "/api/state", session_id=None)[0], 400)
        self.assertEqual(self._request("GET", "/api/state", session_id="not a valid id!")[0], 400)
        self.assertEqual(self._request("POST", "/api/panels/graph/undo", b"{}", session_id=None)[0], 400)
        self.assertEqual(self._request("GET", "/api/panels", session_id=None)[0], 200)

    def test_each_session_id_gets_its_own_draft(self):
        """An edit made as one session id doesn't show in another's state."""
        self._post_json("/api/panels/graph/edit", {"tool": "add_node", "arguments": {"node_id": "mine"}})
        _, _, body = self._request("GET", "/api/state", session_id="another-window")
        self.assertNotIn("mine", json.loads(body)["panels"]["graph"]["draft"]["nodes"])

    def test_unknown_panels_commands_and_routes_are_not_found(self):
        """An unknown panel (the table Editor is off by default), an unknown command, and an unknown POST route are all 404s."""
        self.assertEqual(self._post_json("/api/panels/editor/edit", {})[0], 404)
        self.assertEqual(self._post_json("/api/panels/graph/nope", {})[0], 404)
        self.assertEqual(self._post_json("/api/elsewhere", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
