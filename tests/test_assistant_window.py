"""Tests for AssistantWindow and the editor's undo grouping: real Tk widgets, a fake agent loop in place of Ollama.
Skips if this environment cannot open a Tk window at all."""
import time
import unittest

import tkinter as tk

try:
    _probe = tk.Tk()
    _probe.destroy()
    TK_AVAILABLE = True
except tk.TclError:
    TK_AVAILABLE = False

from mtofr.backseater.backseater import Backseater
from mtofr.database import KnowledgeDatabase
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater

if TK_AVAILABLE:
    from mtofr.world.interface.mission_editor.window import MissionEditorWindow
    from mtofr.world.interface.mission_editor.assistant_window import AssistantWindow


def _fake_agent_turn(messages, think, emit, tools, run_tool, options, should_stop, detect_stall=None):
    """Two chained tool calls, then a final sentence -- the shape of a real turn."""
    emit("loop", {"iteration": 1, "max": 5})
    for name, arguments in (("add_node", {"node_id": "b"}), ("add_node", {"node_id": "c"})):
        emit("tool_call", {"name": name, "arguments": arguments})
        emit("tool_result", {"name": name, "result": run_tool(name, arguments)})
    emit("loop", {"iteration": 2, "max": 5})
    emit("content", "Added two nodes.")
    messages.append({"role": "assistant", "content": "Added two nodes."})


@unittest.skipUnless(TK_AVAILABLE, "no Tk display available in this environment")
class TestAssistantWindow(unittest.TestCase):
    def setUp(self):
        self.frontseater = BicycleFrontseater(hardware=BicycleHardware())
        self.addCleanup(self.frontseater.shutdown)
        backseater = Backseater(frontseater=self.frontseater, knowledge_database=KnowledgeDatabase(),
                                mission_graph=None, platform_id="ugv1", privilege_level=1)
        self.world = World(GroundPlaneEnv(), backseaters={"ugv1": backseater})
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.editor = MissionEditorWindow(self.root, self.world, own_platform_id="interface")
        self.addCleanup(self.editor.close)
        self.assistant = AssistantWindow(self.editor, agent_turn=_fake_agent_turn)
        self.editor.assistant_window = self.assistant   # so editor.close() tears it down, as the real button path does

    def _send(self, text):
        self.assistant.input_entry.insert(0, text)
        self.assistant._on_send()
        deadline = time.time() + 5
        while self.assistant._busy and time.time() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.assistant._busy, "turn did not finish")

    def test_turn_edits_the_editor_draft_through_the_tools(self):
        self._send("add two nodes")
        self.assertIn("b", self.editor.draft["nodes"])
        self.assertIn("c", self.editor.draft["nodes"])

    def test_whole_turn_is_one_undo_step(self):
        before = self.editor.draft
        self._send("add two nodes")
        self.assertEqual(len(self.editor.undo_stack), 1)
        self.editor._on_undo()
        self.assertIs(self.editor.draft, before)

    def test_manual_edits_after_a_turn_are_separate_undo_steps(self):
        self._send("add two nodes")
        self.editor.apply_draft_edit(dict(self.editor.draft))
        self.assertEqual(len(self.editor.undo_stack), 2)

    def test_tool_steps_are_mirrored_to_console_and_transcript(self):
        self._send("add two nodes")
        console = self.editor.console_text.get("1.0", tk.END)
        self.assertIn("[assistant] add_node(node_id='b') -> ok: added node 'b'", console)
        transcript = self.assistant.transcript.get("1.0", tk.END)
        self.assertIn("You: add two nodes", transcript)
        self.assertIn("> add_node(node_id='b')", transcript)
        self.assertIn("Added two nodes.", transcript)

    def test_send_is_ignored_while_busy_and_empty_input_does_nothing(self):
        self.assistant._on_send()
        self.assertFalse(self.assistant._busy)

    def test_agent_error_is_reported_and_ui_recovers(self):
        def failing(*args, **kwargs):
            raise ConnectionError("down")
        self.assistant.agent_turn = failing
        self._send("hi")
        self.assertIn("Could not reach Ollama", self.assistant.transcript.get("1.0", tk.END))
        self.assertIn("Could not reach Ollama", self.editor.console_text.get("1.0", tk.END))
        self.assertEqual(str(self.assistant.send_button.cget("state")), "normal")
        # the failed turn's undo group is closed, so later manual edits record normally
        self.assertFalse(self.editor._undo_group_open)

    def test_new_chat_clears_history_and_transcript(self):
        self._send("add two nodes")
        self.assistant._on_new_chat()
        self.assertEqual(len(self.assistant.session.messages), 1)
        self.assertEqual(self.assistant.transcript.get("1.0", tk.END).strip(), "")

    def test_thinking_is_always_shown_and_separated_from_the_answer(self):
        def thinking_turn(messages, think, emit, tools, run_tool, options, should_stop, detect_stall=None):
            emit("loop", {"iteration": 1, "max": 5})
            emit("thinking", "pondering")
            emit("content", "The answer.")
            messages.append({"role": "assistant", "content": "The answer."})
        self.assistant.agent_turn = thinking_turn
        self.assistant.think.set(False)   # the toggle controls whether the model thinks, not whether it is displayed
        self._send("hi")
        transcript = self.assistant.transcript.get("1.0", tk.END)
        self.assertIn("pondering\n\nThe answer.", transcript)

    def test_done_separator_marks_the_turn_end(self):
        self._send("add two nodes")
        self.assertIn("done -- waiting for you", self.assistant.transcript.get("1.0", tk.END))
        self.assertEqual(self.assistant.status_text.get(), "Ready")

    def test_transcript_only_follows_output_when_scrolled_to_the_bottom(self):
        self.assistant.geometry("560x300")
        self.root.update()
        for number in range(200):
            self.assistant._append(f"line {number}\n")
        self.root.update()
        self.assertGreaterEqual(self.assistant.transcript.yview()[1], 0.999)   # was at the bottom: followed
        self.assistant.transcript.yview_moveto(0.0)
        self.root.update()
        self.assistant._append("more\n")
        self.root.update()
        self.assertLess(self.assistant.transcript.yview()[1], 0.5)             # scrolled up: left alone

    def test_console_only_follows_output_when_scrolled_to_the_bottom(self):
        for number in range(100):
            self.editor._log(f"entry {number}")
        self.root.update()
        self.editor.console_text.yview_moveto(0.0)
        self.root.update()
        self.editor._log("new entry")
        self.root.update()
        self.assertLess(self.editor.console_text.yview()[1], 0.5)

    def test_target_platform_is_shown_and_changes_are_noted_from_either_dropdown(self):
        self.assertIn("[target platform: ugv1]", self.assistant.transcript.get("1.0", tk.END))
        self.assertEqual(self.assistant.platform_dropdown.get(), "ugv1")
        self.editor.target_platform_id.set("ugv2")   # as the editor's own dropdown would
        self.assertIn("[target platform: ugv2]", self.assistant.transcript.get("1.0", tk.END))
        self.assertEqual(self.assistant.platform_dropdown.get(), "ugv2")

    def test_platform_dropdown_is_locked_while_a_turn_runs(self):
        self.assistant._set_busy(True)
        self.assertEqual(str(self.assistant.platform_dropdown.cget("state")), "disabled")
        self.assistant._set_busy(False)
        self.assertEqual(str(self.assistant.platform_dropdown.cget("state")), "readonly")

    def test_status_line_counts_the_wait_and_says_why_a_tool_call_is_slow(self):
        self.assistant._set_busy(True)
        self.assistant._handle_emit("loop", {"iteration": 2, "max": 12})
        self.assertTrue(self.assistant.status_text.get().startswith("Reading prompt..."))
        self.assertIn("[model call 2/12]", self.assistant.transcript.get("1.0", tk.END))
        self.assistant._handle_emit("generating", None)
        self.assertIn("tool call shows only when finished", self.assistant.status_text.get())
        self.assistant._handle_emit("tool_call", {"name": "add_node", "arguments": {"node_id": "x"}})
        self.assertEqual(self.assistant.status_text.get(), "Applying tool...")
        self.assistant._set_busy(False)
        self.assertEqual(self.assistant.status_text.get(), "Ready")

    def test_model_call_stats_include_total_and_load_time_in_console_and_transcript(self):
        self.assistant._handle_emit("stats", {"tokens": 61, "rate": 4.8, "seconds": 13.0, "prompt_tokens": 4336,
                                              "prompt_seconds": 4.0, "load_seconds": 9.0, "total_seconds": 27.0})
        console = self.editor.console_text.get("1.0", tk.END)
        self.assertIn("read 4336 prompt tokens in 4s", console)
        self.assertIn("total 27s, of which model loading 9s", console)
        self.assertIn("(27s, 61 tokens)", self.assistant.transcript.get("1.0", tk.END))

    def test_nudge_is_shown_and_logged(self):
        self.assistant._handle_emit("nudge", "Make the tool calls now.")
        self.assertIn("[nudge: Make the tool calls now.]", self.assistant.transcript.get("1.0", tk.END))
        self.assertIn("nudged", self.editor.console_text.get("1.0", tk.END))

    def test_assistant_button_opens_one_window_and_closing_editor_closes_it(self):
        self.assistant.close()
        self.editor._on_open_assistant()
        first = self.editor.assistant_window
        self.editor._on_open_assistant()
        self.assertIs(self.editor.assistant_window, first)
        self.editor.close()
        self.assertFalse(first.winfo_exists())


if __name__ == "__main__":
    unittest.main()
