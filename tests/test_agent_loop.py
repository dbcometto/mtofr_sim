"""Tests for the agentic loop's message handling, with ollama.chat replaced by a canned stream."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mtofr.world.interface.agent import agent


def _chunk(thinking=None, content=None):
    return SimpleNamespace(message=SimpleNamespace(thinking=thinking, content=content, tool_calls=None),
                           eval_count=None, eval_duration=None)


class TestStreamReply(unittest.TestCase):
    def test_thinking_is_kept_on_the_message_so_the_next_loop_does_not_redo_it(self):
        with patch.object(agent.ollama, "chat", return_value=iter([_chunk(thinking="hmm "), _chunk(thinking="ok"), _chunk(content="Done.")])):
            message, interrupted = agent.stream_reply([], True, lambda kind, data: None, tools=[])
        self.assertEqual(message, {"role": "assistant", "content": "Done.", "thinking": "hmm ok"})
        self.assertFalse(interrupted)

    def test_generating_is_emitted_once_when_the_first_chunk_arrives_even_if_it_is_empty(self):
        events = []
        with patch.object(agent.ollama, "chat", return_value=iter([_chunk(), _chunk(content="a"), _chunk(content="b")])):
            agent.stream_reply([], False, lambda kind, data: events.append(kind), tools=[])
        self.assertEqual(events[0], "generating")
        self.assertEqual(events.count("generating"), 1)

    def test_meta_reports_a_reply_that_hit_the_length_cap(self):
        capped = SimpleNamespace(message=SimpleNamespace(thinking=None, content="long", tool_calls=None),
                                 eval_count=None, eval_duration=None, done_reason="length")
        meta = {}
        with patch.object(agent.ollama, "chat", return_value=iter([capped])):
            agent.stream_reply([], False, lambda kind, data: None, tools=[], meta=meta)
        self.assertTrue(meta["truncated"])
        meta = {}
        with patch.object(agent.ollama, "chat", return_value=iter([_chunk(content="ok")])):
            agent.stream_reply([], False, lambda kind, data: None, tools=[], meta=meta)
        self.assertFalse(meta["truncated"])

    def test_no_thinking_key_when_the_model_did_not_think(self):
        with patch.object(agent.ollama, "chat", return_value=iter([_chunk(content="Hi")])):
            message, _ = agent.stream_reply([], False, lambda kind, data: None, tools=[])
        self.assertNotIn("thinking", message)

    def test_should_stop_interrupts_and_keeps_partial_text(self):
        stops = iter([False, True])
        with patch.object(agent.ollama, "chat", return_value=iter([_chunk(content="part"), _chunk(content="ial")])):
            message, interrupted = agent.stream_reply([], False, lambda kind, data: None, tools=[], should_stop=lambda: next(stops))
        self.assertTrue(interrupted)
        self.assertIn("part", message["content"])
        self.assertIn("[interrupted by user]", message["content"])


class TestTextCallNudge(unittest.TestCase):
    def _run(self, replies, detector):
        events = []
        with patch.object(agent, "stream_reply", side_effect=[(reply, False) for reply in replies]):
            messages = [{"role": "user", "content": "go"}]
            agent.run_agent_turn(messages, False, lambda kind, data: events.append(kind), tools=[],
                                 run_tool=lambda name, arguments: "ok", detect_stall=detector)
        return messages, events

    def test_text_calls_trigger_one_retry_message(self):
        typed = {"role": "assistant", "content": 'add_node(node_id="a")'}
        done = {"role": "assistant", "content": "Done."}
        messages, events = self._run([typed, done],
                                     lambda content, truncated: "make real calls" if "add_node(" in content else None)
        self.assertEqual(events.count("nudge"), 1)
        self.assertEqual(messages[-2:], [{"role": "user", "content": "make real calls"}, done])

    def test_the_detector_is_told_when_the_reply_was_cut_off_by_the_length_cap(self):
        seen = []

        def fake_stream_reply(messages, think, emit, tools, options, should_stop, meta):
            meta["truncated"] = True
            return {"role": "assistant", "content": "rambling"}, False

        with patch.object(agent, "stream_reply", side_effect=fake_stream_reply):
            agent.run_agent_turn([{"role": "user", "content": "go"}], False, lambda kind, data: None, tools=[],
                                 run_tool=lambda name, arguments: "ok",
                                 detect_stall=lambda content, truncated: seen.append(truncated))
        self.assertEqual(seen, [True])

    def test_nudges_are_capped(self):
        typed = {"role": "assistant", "content": 'add_node(node_id="a")'}
        messages, events = self._run([dict(typed) for _ in range(5)], lambda content, truncated: "retry")
        self.assertEqual(events.count("nudge"), agent.config.MAX_NUDGES)

    def test_no_detector_means_no_nudge(self):
        messages, events = self._run([{"role": "assistant", "content": 'add_node(node_id="a")'}], None)
        self.assertNotIn("nudge", events)


if __name__ == "__main__":
    unittest.main()
