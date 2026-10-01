"""Tests for the assistant's tool wrappers, prompt rendering, and session history -- no Tk, no Ollama."""
import unittest

from mtofr.capability.capability import Capability, CapabilityRegistry, ParamSpec
from mtofr.database import Location
from mtofr.world.interface.mission_editor import graph_draft
from mtofr.maps.ground_map import RegionType, TraversabilityType
from mtofr.world.base import WorldState
from mtofr.world.interface.mission_editor.assistant_prompt import (
    SYSTEM_PROMPT, render_state, compose_user_message, describe_world, describe_live,
)
from mtofr.world.interface.mission_editor.assistant_session import AssistantSession
from mtofr.world.interface.mission_editor.assistant_tools import DraftToolbox


class _Holder:
    """A draft the toolbox reads and writes, standing in for the editor window."""
    def __init__(self, draft):
        self.draft = draft
        self.applied = 0

    def apply(self, new_draft):
        self.draft = new_draft
        self.applied += 1


def _toolbox(draft=None):
    holder = _Holder(draft if draft is not None else graph_draft.blank_graph("a"))
    return DraftToolbox(lambda: holder.draft, holder.apply), holder


class TestDraftToolbox(unittest.TestCase):
    def test_every_graph_draft_mutator_has_a_tool_and_schema(self):
        toolbox, _ = _toolbox()
        schema_names = {schema["function"]["name"] for schema in toolbox.schemas}
        self.assertEqual(schema_names, set(toolbox._functions))
        self.assertEqual(len(schema_names), 14)
        for name in schema_names:
            self.assertTrue(hasattr(graph_draft, name), name)

    def test_node_primitive_edge_knowledge_flow(self):
        toolbox, holder = _toolbox()
        self.assertTrue(toolbox.run("add_node", {"node_id": "b"}).startswith("ok"))
        self.assertTrue(toolbox.run("add_knowledge_key", {"key": "goal", "type": "Location", "value": {"x": 1, "y": 2}}).startswith("ok"))
        self.assertTrue(toolbox.run("add_knowledge_key", {"key": "arrived", "type": "bool", "value": "false"}).startswith("ok"))
        self.assertTrue(toolbox.run("add_primitive", {"node_id": "a", "primitive_name": "go", "capability": "move_to",
                                                      "inputs": {"target": "goal"}, "outputs": {"arrived": "arrived"}}).startswith("ok"))
        self.assertTrue(toolbox.run("add_edge", {"source_id": "a", "target_id": "b", "condition": ["arrived", "==", True]}).startswith("ok"))
        draft = holder.draft
        self.assertEqual(draft["knowledge"]["goal"]["value"].x, 1.0)
        self.assertEqual(draft["knowledge"]["arrived"]["value"], False)
        self.assertEqual(draft["nodes"]["a"]["primitives"]["go"]["inputs"], {"target": "goal"})
        self.assertEqual(draft["edges"]["a"][0]["to"], "b")

    def test_nested_arguments_accepted_as_json_strings(self):
        toolbox, holder = _toolbox()
        toolbox.run("add_primitive", {"node_id": "a", "primitive_name": "p", "capability": "stopwatch",
                                      "inputs": "{}", "outputs": '{"elapsed_time": "t"}'})
        self.assertEqual(holder.draft["nodes"]["a"]["primitives"]["p"]["outputs"], {"elapsed_time": "t"})
        toolbox.run("add_node", {"node_id": "b"})
        result = toolbox.run("add_edge", {"source_id": "a", "target_id": "b", "condition": '["t", ">", 5.0]'})
        self.assertTrue(result.startswith("ok"), result)

    def test_edit_and_remove_edge_by_index(self):
        toolbox, holder = _toolbox()
        toolbox.run("add_node", {"node_id": "b"})
        toolbox.run("add_edge", {"source_id": "a", "target_id": "b", "condition": ["x", "==", True]})
        toolbox.run("add_edge", {"source_id": "a", "target_id": "a", "condition": ["y", "==", True]})
        self.assertTrue(toolbox.run("edit_edge", {"source_id": "a", "index": 0, "new_source_id": "a",
                                                  "new_target_id": "b", "condition": ["z", "==", False]}).startswith("ok"))
        self.assertTrue(toolbox.run("remove_edge", {"source_id": "a", "index": "0"}).startswith("ok"))   # model sent a string
        self.assertEqual(len(holder.draft["edges"]["a"]), 1)

    def test_rename_knowledge_key_cascades(self):
        toolbox, holder = _toolbox()
        toolbox.run("add_knowledge_key", {"key": "k", "type": "float", "value": 1})
        toolbox.run("add_edge", {"source_id": "a", "target_id": "a", "condition": ["k", ">", 0.5]})
        toolbox.run("rename_knowledge_key", {"old_key": "k", "new_key": "level"})
        self.assertIn("level", holder.draft["knowledge"])
        self.assertEqual(holder.draft["edges"]["a"][0]["condition"][0], "level")

    def test_errors_come_back_as_text_and_do_not_touch_the_draft(self):
        toolbox, holder = _toolbox()
        cases = [
            ("add_node", {"node_id": "a"}),                                            # duplicate
            ("remove_node", {"node_id": "missing"}),
            ("add_primitive", {"node_id": "missing", "primitive_name": "p", "capability": "c"}),  # helper would KeyError
            ("remove_primitive", {"node_id": "a", "primitive_name": "nope"}),
            ("add_edge", {"source_id": "a", "target_id": "missing", "condition": []}),
            ("add_edge", {"source_id": "a", "target_id": "a", "condition": ["x", "=="]}),   # bad condition syntax
            ("remove_edge", {"source_id": "a", "index": 3}),
            ("add_knowledge_key", {"key": "k", "type": "banana", "value": 1}),
            ("add_knowledge_key", {"key": "k", "type": "float", "value": "abc"}),
            ("add_knowledge_key", {"key": "k", "type": "Location", "value": {"x": 1}}),
            ("edit_knowledge_key", {"key": "missing", "type": "float", "value": 1}),
            ("add_primitive", {"node_id": "a", "primitive_name": "p", "capability": "c", "inputs": {"f": 3}}),
            ("add_node", {}),                                                          # missing argument
            ("no_such_tool", {}),
        ]
        for name, arguments in cases:
            result = toolbox.run(name, arguments)
            self.assertTrue(result.startswith("Error"), f"{name}{arguments} -> {result}")
        self.assertEqual(holder.applied, 0)

    def test_scalar_types_round_trip(self):
        toolbox, holder = _toolbox()
        toolbox.run("add_knowledge_key", {"key": "n", "type": "int", "value": 3})
        toolbox.run("add_knowledge_key", {"key": "flag", "type": "bool", "value": True})
        toolbox.run("add_knowledge_key", {"key": "name", "type": "str", "value": "hi"})
        knowledge = holder.draft["knowledge"]
        self.assertEqual((knowledge["n"]["value"], knowledge["flag"]["value"], knowledge["name"]["value"]), (3, True, "hi"))


class TestToolboxBindingChecks(unittest.TestCase):
    """With a target platform's capabilities known, a primitive that platform couldn't bind is refused at the tool call."""
    def setUp(self):
        registry = CapabilityRegistry([Capability(
            "move_to", "d",
            inputs=(ParamSpec("target", Location, "t"), ParamSpec("tolerance", float, "m")),
            outputs=(ParamSpec("arrived", bool, "a"),))])
        self.holder = _Holder(graph_draft.blank_graph("a"))
        self.toolbox = DraftToolbox(lambda: self.holder.draft, self.holder.apply, get_capabilities=lambda: registry)
        self.toolbox.run("add_knowledge_key", {"key": "goal", "type": "Location", "value": {"x": 1, "y": 2}})
        self.toolbox.run("add_knowledge_key", {"key": "arrived", "type": "bool", "value": False})

    def _add(self, **inputs):
        return self.toolbox.run("add_primitive", {"node_id": "a", "primitive_name": "go", "capability": "move_to",
                                                  "inputs": inputs, "outputs": {"arrived": "arrived"}})

    def test_undeclared_key_is_refused_and_the_draft_is_untouched(self):
        applied_before = self.holder.applied
        result = self._add(target="goal", tolerance="tolerance")
        self.assertTrue(result.startswith("Error"))
        self.assertIn("declare it first", result)
        self.assertEqual(self.holder.applied, applied_before)

    def test_wrong_type_is_refused(self):
        self.assertIn("expects float", self._add(target="goal", tolerance="arrived"))

    def test_correct_binding_is_accepted_once_the_key_is_declared(self):
        self.toolbox.run("add_knowledge_key", {"key": "tolerance", "type": "float", "value": 1.0})
        self.assertTrue(self._add(target="goal", tolerance="tolerance").startswith("ok"))

    def test_unknown_capability_is_refused_with_the_available_ones(self):
        result = self.toolbox.run("add_primitive", {"node_id": "a", "primitive_name": "x", "capability": "fly"})
        self.assertIn("move_to", result)
        self.assertTrue(result.startswith("Error"))

    def test_retyping_a_key_that_primitives_use_warns(self):
        self.toolbox.run("add_knowledge_key", {"key": "tolerance", "type": "float", "value": 1.0})
        self._add(target="goal", tolerance="tolerance")
        result = self.toolbox.run("edit_knowledge_key", {"key": "tolerance", "type": "bool", "value": True})
        self.assertTrue(result.startswith("ok"))
        self.assertIn("WARNING", result)

    def test_unknown_capabilities_means_no_check(self):
        toolbox, holder = _toolbox()
        self.assertTrue(toolbox.run("add_primitive", {"node_id": "a", "primitive_name": "p", "capability": "anything",
                                                      "inputs": {"x": "undeclared"}}).startswith("ok"))


class TestPromptAndSession(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry([Capability(
            "move_to", "drive to a target",
            inputs=(ParamSpec("target", Location, "where"),), outputs=(ParamSpec("arrived", bool, "done"),))])
        draft = graph_draft.blank_graph("a")
        draft = graph_draft.add_knowledge_key(draft, "goal", Location, Location(1.0, 2.0))
        draft = graph_draft.add_primitive(draft, "a", "go", "move_to", {"target": "goal"}, {})
        draft = graph_draft.add_edge(draft, "a", "a", ["goal", "is", "not", None])
        self.draft = draft

    def test_render_state_lists_capabilities_nodes_and_numbered_edges(self):
        text = render_state(self.draft, self.registry, "ugv1")
        for expected in ("ugv1", "move_to", "target (Location: where)", "goal: Location", "start node: a",
                         "primitive go: move_to", "a edge 0: -> a when"):
            self.assertIn(expected, text)

    def test_render_state_handles_empty_draft_and_missing_registry(self):
        text = render_state(graph_draft.blank_graph(), None, "ugv1")
        self.assertIn("(unknown)", text)
        self.assertIn("(none)", text)

    def test_session_injects_state_but_keeps_only_plain_text_and_final_reply(self):
        toolbox, _ = _toolbox(self.draft)
        session = AssistantSession(toolbox)
        seen = []

        def fake_agent_turn(messages, think, emit, tools, run_tool, options, should_stop, detect_stall=None):
            seen.append(messages[-1]["content"])
            messages.append({"role": "assistant", "content": "", "tool_calls": ["x"]})
            messages.append({"role": "tool", "tool_name": "add_node", "content": "ok"})
            messages.append({"role": "assistant", "content": "Done."})

        session.run_turn("add a node", self.draft, self.registry, "ugv1", emit=lambda *a: None, agent_turn=fake_agent_turn)
        self.assertIn("SITUATION", seen[0])
        self.assertIn("Current draft graph:", seen[0])
        self.assertTrue(seen[0].rstrip().endswith("MISSION: add a node"))
        self.assertEqual([(m["role"], m["content"]) for m in session.messages[1:]],
                         [("user", "add a node"), ("assistant", "Done.")])
        session.reset()
        self.assertEqual(len(session.messages), 1)

    def test_detects_tool_calls_typed_as_text_only_at_line_start(self):
        toolbox, _ = _toolbox(self.draft)
        session = AssistantSession(toolbox)
        self.assertIsNotNone(session._detect_stall('Plan first.\nadd_node(node_id="a")\nmore'))
        self.assertIsNotNone(session._detect_stall('  add_edge(source_id="a", target_id="b", condition=[])'))
        self.assertIsNone(session._detect_stall("The graph uses add_node(...) calls inline, then finishes."))
        self.assertIsNone(session._detect_stall("Done. The start node now moves the vehicle."))

    def test_detects_a_reply_cut_off_by_the_length_cap(self):
        toolbox, _ = _toolbox(self.draft)
        session = AssistantSession(toolbox)
        self.assertIsNotNone(session._detect_stall("Wait, let me think about this again...", truncated=True))

    def test_detects_announce_then_stop_but_not_questions_or_finished_summaries(self):
        """Regressions from a real run: the turn ended on 'I will now add the waypoint node...' with nothing done."""
        toolbox, _ = _toolbox(self.draft)
        session = AssistantSession(toolbox)
        stalls = ["Declared the keys.\n\nI will now add the waypoint node and its primitive, then configure the edges.",
                  "Next, I need to update the primitive in phase_one so it targets target_alpha.",
                  "Let me add the second move_to now."]
        for content in stalls:
            self.assertIsNotNone(session._detect_stall(content), content)
        finished = ["I renamed the start node and gave it a move to (40, 0). The draft changes are in for approval.",
                    "I will assume a 1 m tolerance. Do you want a different one?",
                    "I'll use the existing start node.\n\nThe start node now drives the vehicle to (40, 0). It is in the draft, not pushed."]
        for content in finished:
            self.assertIsNone(session._detect_stall(content), content)

    def test_replies_are_capped_in_length(self):
        toolbox, _ = _toolbox(self.draft)
        self.assertGreater(AssistantSession(toolbox).options["num_predict"], 0)

    def test_session_compacts_even_if_the_turn_raises(self):
        toolbox, _ = _toolbox(self.draft)
        session = AssistantSession(toolbox)

        def failing_agent_turn(messages, *args, **kwargs):
            raise ConnectionError("down")

        with self.assertRaises(ConnectionError):
            session.run_turn("hi", self.draft, self.registry, "ugv1", emit=lambda *a: None, agent_turn=failing_agent_turn)
        self.assertEqual(session.messages[-1], {"role": "user", "content": "hi"})


class _FakeMap:
    """Just the GroundMap attributes describe_world reads: 200 m x 100 m at 0.5 m/pixel."""
    name = "testmap"
    meters_per_pixel = 0.5
    width_meters = 200.0
    height_meters = 100.0
    regions_lookup = {(1, 2, 3): RegionType("depot", center_x=0.0, center_y=0.0)}   # pixel (0, 0) is the top-left corner
    traversability_lookup = {(0, 0, 0): TraversabilityType("water", True, 0.0),
                             (9, 9, 9): TraversabilityType("road", False, 1.5)}


class TestWorldDescription(unittest.TestCase):
    def test_map_corners_regions_terrain_and_position(self):
        text = describe_world(_FakeMap(), WorldState(x=3.0, y=-4.0))
        for expected in ("x from -100 to 100", "y from -50 to 50", "top-left (-100, 50)", "bottom-right (100, -50)",
                         "Region 'depot': center (-100, 50)", "Terrain 'water': blocked", "Terrain 'road': speed x1.5",
                         "(3.0, -4.0)", "+y is up"):
            self.assertIn(expected, text)

    def test_mapless_and_stateless(self):
        text = describe_world(None, None)
        self.assertIn("no map", text)
        self.assertNotIn("currently at", text)

    def test_world_is_part_of_the_turn_message(self):
        message = compose_user_message("go", graph_draft.blank_graph(), None, "ugv1", describe_world(_FakeMap(), None))
        self.assertTrue(message.startswith("SITUATION"))
        self.assertIn("top-left (-100, 50)", message)


class TestLiveState(unittest.TestCase):
    class _Backseater:
        """Just what describe_live reads: the pushed graph and the active node."""
        def __init__(self, mission_graph):
            self.mission_graph = mission_graph

        def status(self):
            return {"active_node_id": "start"}

    def test_live_state_is_framed_as_information_only_and_omits_stale_values(self):
        text = describe_live(self._Backseater(graph_draft.blank_graph("start")))
        self.assertIn("node 'start'", text)
        self.assertIn("NOT what you edit", text)
        self.assertNotIn("arrived", text)
        self.assertEqual(describe_live(None), "")

    def test_says_when_the_draft_has_unpushed_changes_and_when_it_does_not(self):
        pushed = graph_draft.add_knowledge_key(graph_draft.blank_graph("start"), "goal", Location, Location(1.0, 2.0))
        backseater = self._Backseater(pushed)
        identical_copy = graph_draft.load_draft(pushed)
        self.assertIn("identical", describe_live(backseater, identical_copy))
        renamed = graph_draft.rename_node(identical_copy, "start", "phase_one")
        self.assertIn("unpushed changes", describe_live(backseater, renamed))
        self.assertIn("expected", describe_live(backseater, renamed))

    def test_capability_field_meanings_reach_the_model(self):
        registry = CapabilityRegistry([Capability("move_to", "d", inputs=(ParamSpec("tolerance", float, "reached distance in meters"),))])
        self.assertIn("tolerance (float: reached distance in meters)", render_state(graph_draft.blank_graph(), registry, "u"))


class TestSystemPrompt(unittest.TestCase):
    def test_prompt_stays_small_enough_for_the_context_window(self):
        self.assertLess(len(SYSTEM_PROMPT) / 4, 1500)   # rough token estimate; leaves room for schemas + draft in 8192

    def test_worked_example_runs_cleanly_through_the_real_toolbox(self):
        """The example in the prompt must stay valid as the tools evolve, or it teaches the model errors."""
        calls = [line for line in SYSTEM_PROMPT.splitlines() if line.startswith(("add_", "edit_", "remove_"))]
        self.assertGreaterEqual(len(calls), 4)
        toolbox, holder = _toolbox(graph_draft.blank_graph("start"))
        for line in calls:
            name, _, argument_text = line.partition("(")
            arguments = eval(f"dict({argument_text[:-1]})", {"true": True, "false": False})
            result = toolbox.run(name, arguments)
            self.assertTrue(result.startswith("ok"), f"{line} -> {result}")
        self.assertEqual(holder.draft["nodes"]["start"]["primitives"]["go"]["inputs"],
                         {"target": "goal", "tolerance": "tolerance"})


if __name__ == "__main__":
    unittest.main()
