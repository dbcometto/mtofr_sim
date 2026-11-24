"""Tests for the web UI's WebHost and its built-in panels, driven through WebHost.state()/
command()/on_tick() exactly as the server and the interface Frontseater drive them. Uses
real Backseaters over fake Frontseaters, synced directly (no World, server, or MPC):
everything the panels read must come from the interface's own databases, every write
must reach a peer only by mesh sync, and each browser window (session id) keeps its own
Target, draft, and console. The draft is edited through the graph panel, which delegates
every command to the window's (unlisted) EditorPanel."""
import json
import unittest

from mtofr.core.capability import Capability, CapabilityRegistry, ParamSpec
from mtofr.database import KnowledgeDatabase, Location
from mtofr.environments.ground_plane.platforms.interface.web.config import MAX_SESSIONS, SESSION_IDLE_TIMEOUT
from mtofr.environments.ground_plane.platforms.interface.web.host import WebHost
from mtofr.environments.ground_plane.platforms.interface.web.panel import UnknownCommandError
from mtofr.environments.ground_plane.platforms.interface.web.panels import default_panels
from mtofr.environments.ground_plane.platforms.interface.web.panels.editor import EditorPanel
from mtofr.environments.ground_plane.maps.ground_map import TraversabilityType
from mtofr.mission.serialization import encode_mission_graph
from mtofr.platform.backseater import Backseater
from mtofr.platform.frontseater import Frontseater
from tests.test_ground_plane_env import uniform_ground_map

SESSION = "window-1"
OTHER_SESSION = "window-2"
EDITOR = "graph"   # the panel that edits the draft by default
FLAG_CONDITION = '["flag", "==", true]'   # a condition as the browser sends it (JSON tokens)


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _Idle(Capability):
    """A capability that does nothing."""
    ipl_type = "idle"
    description = "Does nothing."


class _Goto(Capability):
    """A declaration-only capability with one Location input."""
    ipl_type = "goto"
    description = "Goes somewhere."
    inputs = (ParamSpec("target", Location, "Where to go"),)


class _FakeFrontseater(Frontseater):
    """Advertises "idle" (no fields) and "goto" (a required Location input); runs nothing."""
    def __init__(self):
        """Advertise the two capabilities."""
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([_Idle, _Goto])

    def compute_controls(self, state) -> dict:
        """Command nothing."""
        return {}

    def capabilities(self) -> CapabilityRegistry:
        """Return the two-capability registry."""
        return self._registry

    def set_active_capabilities(self, capability_requests: dict) -> None:
        """Ignore capability request changes; nothing runs."""

    def describe_status(self) -> dict:
        """Report a fixed idle status."""
        return {"overall": "idle", "capabilities": {}}


class _FakeClock:
    """A settable clock (s) for session idleness."""
    def __init__(self):
        """Starts at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """The current fake time."""
        return self.now


def _ugv_boot_graph() -> dict:
    """ugv1's boot mission: one idle node, declaring a float and a Location key."""
    return {
        "knowledge": {
            "ugv1/speed": {"type": float, "value": 0.5},
            "ugv1/goal": {"type": Location, "value": Location(1.0, 2.0)},
        },
        "nodes": {"boot": {"capabilities": {"rest": {"capability": "idle", "inputs": {}, "outputs": {}}}}},
        "edges": {},
        "start": "boot",
    }


def _make_backseater(platform_id: str, privilege_level: int, mission_graph: dict = None) -> Backseater:
    """A Backseater over a fake Frontseater (mission_graph None boots the inert default)."""
    return Backseater(frontseater=_FakeFrontseater(), knowledge_database=KnowledgeDatabase(),
                       mission_graph=mission_graph, platform_id=platform_id, privilege_level=privilege_level)


class TestWebHost(unittest.TestCase):
    def setUp(self):
        """An interface (privilege 0) and ugv1 (privilege 1), synced once, and a WebHost on the interface after one tick."""
        self.interface = _make_backseater("interface", privilege_level=0)
        self.ugv1 = _make_backseater("ugv1", privilege_level=1, mission_graph=_ugv_boot_graph())
        self.interface.sync_with(self.ugv1)
        self.clock = _FakeClock()
        self.host = WebHost("interface", default_panels, clock=self.clock)
        self.host.on_tick(self.interface)

    def _command(self, panel: str, command: str, arguments: dict = None, session_id: str = SESSION) -> dict:
        """Runs one panel command in a window (SESSION by default)."""
        return self.host.command(session_id, panel, command, arguments or {})

    def _edit(self, tool: str, session_id: str = SESSION, **arguments) -> dict:
        """Runs one editor step in a window."""
        return self._command(EDITOR, "edit", {"tool": tool, "arguments": arguments}, session_id)

    def _editor_state(self, session_id: str = SESSION) -> dict:
        """A window's editor state, as its browser sees it."""
        return self.host.state(session_id)["panels"][EDITOR]

    def _draft(self, session_id: str = SESSION) -> dict:
        """A window's encoded draft graph."""
        return self._editor_state(session_id)["draft"]

    def _tick_and_sync(self) -> None:
        """One interface tick (queued writes run), then a sync to ugv1 and ugv1's own update()."""
        self.host.on_tick(self.interface)
        self.interface.sync_with(self.ugv1)
        self.ugv1.update()

    def _console(self, session_id: str = SESSION) -> str:
        """A window's console as one string."""
        return "\n".join(self.host.state(session_id)["console"])

    #===============# Host #===============#

    def test_state_lists_the_platforms_the_interface_knows_and_defaults_the_target_to_a_peer(self):
        """Peers come from the interface's own PlatformDatabase; the Target defaults to the first other platform."""
        state = self.host.state(SESSION)
        self.assertEqual(state["platforms"], ["interface", "ugv1"])
        self.assertEqual(state["target"], "ugv1")

    def test_state_reports_how_long_since_the_target_synced(self):
        """target_sync_age is the seconds since the interface last synced with the Target."""
        age = self.host.state(SESSION)["target_sync_age"]
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0.0)

    def test_state_is_json_serializable(self):
        """The whole polled state (Location knowledge, layouts, problems, condition rows, registries) survives json.dumps()."""
        json.dumps(self.host.state(SESSION))

    def test_set_target_refuses_an_unknown_platform(self):
        """Selecting a platform the interface hasn't heard of raises ValueError."""
        with self.assertRaises(ValueError):
            self.host.set_target(SESSION, "ugv9")

    def test_unknown_panels_and_commands_raise(self):
        """An unknown panel (the table Editor is off by default) or command raises UnknownCommandError (the server's 404)."""
        with self.assertRaises(UnknownCommandError):
            self._command("editor", "undo")
        with self.assertRaises(UnknownCommandError):
            self._command(EDITOR, "nope")

    def test_duplicate_panel_names_are_refused(self):
        """Two panels with one name raise ValueError at construction."""
        with self.assertRaises(ValueError):
            WebHost("interface", lambda: [EditorPanel(), EditorPanel()])

    def test_a_tick_carries_the_sensed_map_into_the_view(self):
        """on_tick()'s ground_map lands in the view (no map by default), and the World Viewer shows it."""
        self.assertIsNone(self.host.view.ground_map)
        ground_map = uniform_ground_map(TraversabilityType(name="clear", blocking=False, speed_multiplier=1.0))
        self.host.on_tick(self.interface, ground_map)
        self.assertIs(self.host.view.ground_map, ground_map)
        self.assertEqual(self.host.state(SESSION)["panels"]["world_viewer"]["map"]["name"], "uniform")

    def test_a_failed_write_is_logged_not_raised(self):
        """A queued write that raises is reported in its log, and the tick carries on."""
        lines = []

        def failing_write(backseater):
            """Fail like a refused publish."""
            raise PermissionError("nope")
        self.host.queue_write("Probe", failing_write, lines.append)
        self.host.on_tick(self.interface)   # must not raise
        self.assertIn("Probe failed: nope", lines)

    #===============# Sessions #===============#

    def test_each_window_keeps_its_own_draft_and_undo_history(self):
        """An edit in one window doesn't appear in another, and undo only walks back its own window's edits."""
        self._edit("add_node", node_id="mine")
        self._edit("add_node", session_id=OTHER_SESSION, node_id="theirs")
        self.assertIn("mine", self._draft()["nodes"])
        self.assertNotIn("theirs", self._draft()["nodes"])
        self._command(EDITOR, "undo", session_id=OTHER_SESSION)
        self.assertNotIn("theirs", self._draft(OTHER_SESSION)["nodes"])
        self.assertIn("mine", self._draft()["nodes"])

    def test_each_window_keeps_its_own_target_over_one_shared_view(self):
        """Two windows can point at different platforms, while both see the same platforms."""
        self.host.set_target(SESSION, "ugv1")
        self.host.set_target(OTHER_SESSION, "interface")
        self.assertEqual(self.host.state(SESSION)["target"], "ugv1")
        self.assertEqual(self.host.state(OTHER_SESSION)["target"], "interface")
        self.assertEqual(self.host.state(SESSION)["platforms"], self.host.state(OTHER_SESSION)["platforms"])

    def test_a_queued_writes_outcome_goes_only_to_its_own_windows_console(self):
        """A push's queued and outcome lines land in the pushing window's console, not another's."""
        self._command(EDITOR, "load_live")
        self._command(EDITOR, "push")
        self.host.state(OTHER_SESSION)   # make sure the other window exists
        self.host.on_tick(self.interface)
        self.assertIn("Push draft to 'ugv1'", self._console())
        self.assertNotIn("Push draft", self._console(OTHER_SESSION))

    def test_an_idle_window_session_expires(self):
        """A window not heard from for longer than SESSION_IDLE_TIMEOUT starts over with a blank draft."""
        self._edit("add_node", node_id="mine")
        self.clock.now += SESSION_IDLE_TIMEOUT + 1
        self.assertNotIn("mine", self._draft()["nodes"])

    def test_sessions_past_the_cap_evict_the_longest_idle(self):
        """Opening more than MAX_SESSIONS windows drops the one heard from least recently."""
        self._edit("add_node", node_id="oldest")
        for index in range(MAX_SESSIONS):
            self.clock.now += 1
            self.host.state(f"window-extra-{index}")
        self.assertEqual(self.host.session_count(), MAX_SESSIONS)
        self.assertNotIn("oldest", self._draft()["nodes"])

    #===============# Editing #===============#

    def test_load_live_copies_the_targets_gossiped_boot_mission(self):
        """Load Live drafts ugv1's boot mission as the interface holds it, tagged with its source."""
        self.assertTrue(self._command(EDITOR, "load_live")["ok"])
        self.assertEqual(self._draft(), encode_mission_graph(_ugv_boot_graph()))
        self.assertEqual(self._editor_state()["draft_source"], "ugv1")

    def test_edits_go_through_the_toolbox_and_undo_restores(self):
        """An edit tool changes the draft; undo returns to the draft before it."""
        result = self._edit("add_node", node_id="patrol")
        self.assertTrue(result["ok"], result["message"])
        self.assertIn("patrol", self._draft()["nodes"])
        self._command(EDITOR, "undo")
        self.assertNotIn("patrol", self._draft()["nodes"])

    def test_a_failed_edit_comes_back_as_not_ok(self):
        """A tool error (here, a missing node) is an ok=False reply, not an exception."""
        self.assertFalse(self._edit("remove_node", node_id="ghost")["ok"])

    def test_an_edit_batch_is_one_undo_step(self):
        """Every step of a batch lands together (editor-only layout steps included), and one undo removes them all."""
        result = self._command(EDITOR, "edit_batch", {"steps": [
            {"tool": "add_node", "arguments": {"node_id": "a"}},
            {"tool": "move_nodes", "arguments": {"positions": {"a": [2.0, 3.0]}}},
            {"tool": "add_edge", "arguments": {"source_id": "start", "target_id": "a", "condition": FLAG_CONDITION}},
        ]})
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(self._editor_state()["layout"]["a"], [2.0, 3.0])
        self._command(EDITOR, "undo")
        self.assertNotIn("a", self._draft()["nodes"])

    def test_an_edit_batch_is_atomic(self):
        """A failing step leaves the draft exactly as it was, earlier steps included."""
        before = self._draft()
        result = self._command(EDITOR, "edit_batch", {"steps": [
            {"tool": "add_node", "arguments": {"node_id": "a"}},
            {"tool": "remove_node", "arguments": {"node_id": "ghost"}},
        ]})
        self.assertFalse(result["ok"])
        self.assertEqual(self._draft(), before)
        self.assertFalse(self._editor_state()["can_undo"])

    def test_move_nodes_is_one_undo_step_and_refuses_unknown_nodes(self):
        """Moving several nodes is one undoable step; placing a node that doesn't exist is refused."""
        self._edit("add_node", node_id="a")
        self.assertTrue(self._command(EDITOR, "move_nodes", {"positions": {"start": [0, 0], "a": [1, 1]}})["ok"])
        self.assertEqual(self._editor_state()["layout"], {"start": [0.0, 0.0], "a": [1.0, 1.0]})
        self._command(EDITOR, "undo")
        self.assertEqual(self._editor_state()["layout"], {})
        self.assertFalse(self._command(EDITOR, "move_nodes", {"positions": {"ghost": [0, 0]}})["ok"])

    def test_a_node_rename_keeps_its_position(self):
        """Renaming a placed node carries its position to the new id."""
        self._command(EDITOR, "move_nodes", {"positions": {"start": [4.0, 5.0]}})
        self._edit("rename_node", old_id="start", new_id="home")
        self.assertEqual(self._editor_state()["layout"], {"home": [4.0, 5.0]})

    def test_move_edge_changes_which_edge_is_checked_first(self):
        """move_edge reorders a source's edges (first match wins)."""
        self._edit("add_node", node_id="a")
        self._edit("add_node", node_id="b")
        self._edit("add_edge", source_id="start", target_id="a", condition=FLAG_CONDITION)
        self._edit("add_edge", source_id="start", target_id="b", condition=FLAG_CONDITION)
        self.assertTrue(self._command(EDITOR, "move_edge", {"source_id": "start", "index": 1, "new_index": 0})["ok"])
        self.assertEqual([edge["to"] for edge in self._draft()["edges"]["start"]], ["b", "a"])
        self.assertFalse(self._command(EDITOR, "move_edge", {"source_id": "start", "index": 5, "new_index": 0})["ok"])

    def test_set_mission_name_is_an_undoable_edit(self):
        """The mission name is set through an editor step and undone like any edit."""
        self._edit("set_mission_name", name="patrol east")
        self.assertEqual(self._editor_state()["name"], "patrol east")
        self._command(EDITOR, "undo")
        self.assertEqual(self._editor_state()["name"], "")

    #===============# Incomplete Requests, Unset Keys, Problems #===============#

    def test_an_incomplete_capability_request_is_allowed_and_flagged(self):
        """The editor accepts a request missing its required input and lists why, per node and request."""
        result = self._edit("add_capability", node_id="start", request_name="go", capability="goto", inputs={}, outputs={})
        self.assertTrue(result["ok"], result["message"])
        problems = self._editor_state()["problems"]["requests"]
        self.assertIn("go", problems["start"])
        self.assertIn("missing required input 'target'", problems["start"]["go"][0])

    def test_validate_and_push_refuse_an_incomplete_request(self):
        """Validate and Push both refuse a draft whose request couldn't bind, and nothing is queued."""
        self._edit("add_capability", node_id="start", request_name="go", capability="goto", inputs={}, outputs={})
        self.assertFalse(self._command(EDITOR, "validate")["ok"])
        self.assertFalse(self._command(EDITOR, "push")["ok"])
        self.assertNotIn("Queued", self._console())

    def test_a_placeholder_key_stays_flagged_until_its_value_is_set(self):
        """A new key with no value binds but keeps the request flagged and Push refused, until a value is entered."""
        result = self._command(EDITOR, "edit_batch", {"steps": [
            {"tool": "declare_key", "arguments": {"key": "ugv1/target", "type_name": "Location", "follows_target": True}},
            {"tool": "add_capability", "arguments": {"node_id": "start", "request_name": "go", "capability": "goto",
                                                     "inputs": {"target": "ugv1/target"}, "outputs": {}}},
        ]})
        self.assertTrue(result["ok"], result["message"])
        state = self._editor_state()
        self.assertEqual(state["unset_keys"], ["ugv1/target"])
        self.assertIn("ugv1/target", state["problems"]["keys"])
        self.assertIn("no value yet", state["problems"]["requests"]["start"]["go"][0])
        self.assertFalse(self._command(EDITOR, "push")["ok"])

        self._edit("edit_knowledge_key", key="ugv1/target", type="Location", value={"x": "5", "y": "-2"})
        state = self._editor_state()
        self.assertEqual(state["unset_keys"], [])
        self.assertEqual(state["problems"]["requests"], {})
        self.assertTrue(self._command(EDITOR, "push")["ok"])

    def test_a_pushed_graph_carries_no_editor_data(self):
        """Only the mission graph reaches the Target: no layout or flags."""
        self._command(EDITOR, "load_live")
        self._command(EDITOR, "move_nodes", {"positions": {"boot": [1.0, 1.0]}})
        self._command(EDITOR, "push")
        self.host.on_tick(self.interface)
        pushed = self.interface.mission_database.get("ugv1")
        self.assertEqual(set(pushed), {"knowledge", "nodes", "edges", "start"})

    def test_an_edge_comparing_a_bool_key_with_a_string_is_flagged_and_refused(self):
        """The "true" (string) trap is a live edge problem, and Validate refuses it."""
        self._edit("add_knowledge_key", key="flag", type="bool", value="false")
        self._edit("add_edge", source_id="start", target_id="start", condition='["flag", "==", "true"]')
        self.assertIn("start#0", self._editor_state()["problems"]["edges"])
        self.assertFalse(self._command(EDITOR, "validate")["ok"])

    def test_state_offers_builder_rows_for_simple_conditions(self):
        """edge_rows carries the builder form of each edge's condition."""
        self._edit("add_knowledge_key", key="flag", type="bool", value="false")
        self._edit("add_edge", source_id="start", target_id="start", condition=FLAG_CONDITION)
        self.assertEqual(self._editor_state()["edge_rows"]["start#0"],
                         {"match": "all", "rows": [{"key": "flag", "operator": "==", "value": True, "negated": False}]})

    #===============# Namespaces and Retarget #===============#

    def test_a_target_change_alone_renames_nothing(self):
        """Switching the Target (e.g. just to look at another platform) leaves following keys alone."""
        self._edit("declare_key", key="ugv1/goal2", type_name="float", value="1.0", follows_target=True)
        self.host.set_target(SESSION, "interface")
        self.assertIn("ugv1/goal2", self._draft()["knowledge"])
        self.assertEqual(self._editor_state()["draft_namespace"], "ugv1")

    def test_retarget_renames_only_following_keys_as_one_undo_step(self):
        """Retarget moves default-namespace keys to the Target's namespace (bindings follow); edited ones stay."""
        self._command(EDITOR, "edit_batch", {"steps": [
            {"tool": "declare_key", "arguments": {"key": "ugv1/goal", "type_name": "Location", "value": {"x": "1", "y": "1"}, "follows_target": True}},
            {"tool": "declare_key", "arguments": {"key": "shared/flag", "type_name": "bool", "value": "false"}},
            {"tool": "add_capability", "arguments": {"node_id": "start", "request_name": "go", "capability": "goto",
                                                     "inputs": {"target": "ugv1/goal"}, "outputs": {}}},
        ]})
        self.host.set_target(SESSION, "interface")
        self.assertTrue(self._command(EDITOR, "retarget")["ok"])
        draft = self._draft()
        self.assertEqual(set(draft["knowledge"]), {"interface/goal", "shared/flag"})
        self.assertEqual(draft["nodes"]["start"]["capabilities"]["go"]["inputs"], {"target": "interface/goal"})
        self._command(EDITOR, "undo")
        self.assertIn("ugv1/goal", self._draft()["knowledge"])

    def test_retarget_skips_a_key_whose_new_name_is_taken(self):
        """A following key that would collide is left in place, and the skip is logged."""
        self._command(EDITOR, "edit_batch", {"steps": [
            {"tool": "declare_key", "arguments": {"key": "ugv1/x", "type_name": "float", "value": "1", "follows_target": True}},
            {"tool": "declare_key", "arguments": {"key": "interface/x", "type_name": "float", "value": "2"}},
        ]})
        self.host.set_target(SESSION, "interface")
        self._command(EDITOR, "retarget")
        self.assertEqual(set(self._draft()["knowledge"]), {"ugv1/x", "interface/x"})
        self.assertIn("skipped", self._console())

    #===============# Files and the Editor Store #===============#

    def test_save_and_load_file_round_trip_the_draft_and_its_editor_data(self):
        """save_file's text loads back (via load_file) into the same draft, layout and flags included."""
        self._command(EDITOR, "load_live")
        self._command(EDITOR, "move_nodes", {"positions": {"boot": [4.0, -1.5]}})
        self._edit("declare_key", key="ugv1/x", type_name="float", follows_target=True)
        saved_state = self._editor_state()
        saved_text = self._command(EDITOR, "save_file")["text"]
        self._command(EDITOR, "new_blank")
        self.assertTrue(self._command(EDITOR, "load_file", {"text": saved_text, "file_name": "saved.json"})["ok"])
        state = self._editor_state()
        for field in ("draft", "layout", "unset_keys", "following_keys"):
            self.assertEqual(state[field], saved_state[field], field)

    def test_load_file_refuses_text_that_is_not_a_mission_graph(self):
        """Bad JSON is an ok=False reply."""
        self.assertFalse(self._command(EDITOR, "load_file", {"text": "{not json"})["ok"])

    def test_a_named_pushed_mission_restores_its_layout_on_load_live_in_any_window(self):
        """Pushing a named mission stores its editor data; Load Live in another window gets the layout back."""
        self._command(EDITOR, "load_live")
        self._edit("set_mission_name", name="patrol")
        self._command(EDITOR, "move_nodes", {"positions": {"boot": [3.0, 3.0]}})
        self.assertTrue(self._command(EDITOR, "push")["ok"])
        self._tick_and_sync()
        self.interface.sync_with(self.ugv1)
        self.host.on_tick(self.interface)

        self._command(EDITOR, "load_live", session_id=OTHER_SESSION)
        self.assertEqual(self._editor_state(OTHER_SESSION)["layout"], {"boot": [3.0, 3.0]})
        self.assertEqual(self.host.state(OTHER_SESSION)["panels"][EDITOR]["live"]["layout"]["boot"], [3.0, 3.0])

    #===============# Push #===============#

    def test_validate_reports_problems_and_success(self):
        """Validate fails a graph with an undeclared condition key, and passes ugv1's own mission."""
        self._edit("add_node", node_id="next")
        self._edit("add_edge", source_id="start", target_id="next", condition='["undeclared", "==", true]')
        self.assertFalse(self._command(EDITOR, "validate")["ok"])
        self._command(EDITOR, "load_live")
        self.assertTrue(self._command(EDITOR, "validate")["ok"])

    def test_push_is_queued_then_reaches_the_target_only_by_sync(self):
        """A push writes nothing until the interface ticks, lands in the interface's own Mission database, and ugv1 adopts it after sync."""
        self._command(EDITOR, "load_live")
        self._edit("rename_node", old_id="boot", new_id="patrol")
        self.assertTrue(self._command(EDITOR, "push")["ok"])
        self.assertEqual(self.interface.mission_database.get("ugv1")["start"], "boot")   # not yet: only queued

        self._tick_and_sync()
        self.assertEqual(self.interface.mission_database.origin_of("ugv1"), "interface")
        self.assertEqual(self.ugv1.active_node_id, "patrol")
        self.assertIn("Push draft to 'ugv1'", self._console())

    def test_a_push_the_privilege_check_refuses_is_logged(self):
        """A WebHost on an equal-privilege platform queues the push, but the write is refused and logged."""
        peer = _make_backseater("ugv2", privilege_level=1)
        peer.sync_with(self.ugv1)
        host = WebHost("ugv2", default_panels)
        host.on_tick(peer)
        host.set_target(SESSION, "ugv1")
        host.command(SESSION, EDITOR, "load_live", {})
        host.command(SESSION, EDITOR, "push", {})
        host.on_tick(peer)
        self.assertIn("Push draft to 'ugv1' failed", "\n".join(host.state(SESSION)["console"]))
        self.assertEqual(peer.mission_database.origin_of("ugv1"), "ugv1")

    #===============# Live Control #===============#

    def _live_rows(self) -> dict:
        """Live Control's rows by key."""
        return {row["key"]: row for row in self.host.state(SESSION)["panels"]["live_control"]["rows"]}

    def test_live_control_shows_the_whole_mesh_knowledge_with_origins_and_sync_ages(self):
        """Rows come from the interface's own Knowledge, with ugv1's keys, their origin, and its sync age."""
        row = self._live_rows()["ugv1/goal"]
        self.assertEqual(row["value"], {"x": 1.0, "y": 2.0})
        self.assertEqual((row["type"], row["origin"]), ("Location", "ugv1"))
        self.assertIsNotNone(row["synced_age"])
        self.assertFalse(row["pending"])

    def test_a_queued_live_value_is_pending_until_the_tick_applies_it(self):
        """A set value shows (pending) right away, and settles once the interface ticks."""
        self._command("live_control", "set_value", {"key": "ugv1/speed", "value": "0.9"})
        row = self._live_rows()["ugv1/speed"]
        self.assertEqual((row["value"], row["pending"]), (0.9, True))
        self._tick_and_sync()
        row = self._live_rows()["ugv1/speed"]
        self.assertEqual((row["value"], row["pending"]), (0.9, False))
        self.assertEqual(self.ugv1.knowledge_database.get("ugv1/speed"), 0.9)

    def test_a_pushed_missions_unseen_keys_are_pending_until_they_arrive(self):
        """Keys a pushed mission declares show as pending rows until the Target adopts it and syncs back."""
        self._command(EDITOR, "load_live")
        self._edit("add_knowledge_key", key="ugv1/new", type="float", value="2.0")
        self._command(EDITOR, "push")
        self.host.on_tick(self.interface)   # the push lands in the interface's own Mission database
        self.assertTrue(self._live_rows()["ugv1/new"]["pending"])
        self.interface.sync_with(self.ugv1)
        self.ugv1.update()   # ugv1 adopts the mission and declares the key
        self.interface.sync_with(self.ugv1)
        self.host.on_tick(self.interface)
        self.assertFalse(self._live_rows()["ugv1/new"]["pending"])

    def test_a_compound_live_value_is_built_from_its_field_texts(self):
        """A Location value arrives as field texts and is published as a Location."""
        self._command("live_control", "set_value", {"key": "ugv1/goal", "value": {"x": "3", "y": "4.5"}})
        self.host.on_tick(self.interface)
        goal = self.interface.knowledge_database.get("ugv1/goal")
        self.assertEqual((goal.x, goal.y), (3.0, 4.5))

    def test_a_bad_live_value_is_refused_before_queueing(self):
        """Text that isn't the key's type is an ok=False reply, and nothing is queued."""
        self.assertFalse(self._command("live_control", "set_value", {"key": "ugv1/speed", "value": "fast"})["ok"])
        self.assertNotIn("Queued", self._console())

    #===============# Graph #===============#

    def test_graph_state_places_every_draft_node(self):
        """draft_layout has a position for every node, honoring placed ones exactly."""
        self._edit("add_node", node_id="a")
        self._command(EDITOR, "move_nodes", {"positions": {"a": [3.0, 1.0]}})
        layout = self._editor_state()["draft_layout"]
        self.assertEqual(set(layout), {"start", "a"})
        self.assertEqual(layout["a"], [3.0, 1.0])

    def test_graph_state_shows_the_targets_live_mission_status_values_and_sync_age(self):
        """live carries the Target's gossiped mission, its layout, active node, key values, and sync age."""
        self.ugv1.update()   # publishes its live status into its PlatformRecord
        self.interface.sync_with(self.ugv1)
        self.host.on_tick(self.interface)
        live = self._editor_state()["live"]
        self.assertEqual(live["graph"]["start"], "boot")
        self.assertEqual(set(live["layout"]), {"boot"})
        self.assertEqual(live["active_node_id"], "boot")
        self.assertEqual(live["values"]["ugv1/speed"], 0.5)
        self.assertIsNotNone(live["last_sync_age"])


if __name__ == "__main__":
    unittest.main()
