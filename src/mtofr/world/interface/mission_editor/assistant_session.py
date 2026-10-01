"""Defines AssistantSession: the LLM conversation history for the mission editor, with no Tk dependency."""
import re

from mtofr.world.interface.agent import config
from mtofr.world.interface.mission_editor.assistant_prompt import SYSTEM_PROMPT, compose_user_message


TEXT_CALL_NUDGE = ("Those tool calls were written as text, so nothing happened. "
                  "Make each one now as a real tool call, without repeating the explanation.")
TRUNCATED_NUDGE = ("Your reply was cut off because it ran too long, and no tool call was made. "
                   "Make the tool calls now, with no explanation.")
INTENT_NUDGE = ("You said what you will do next but did not do it, and a message without a tool call ends your turn. "
                "Make the tool calls now, without repeating the explanation.")

# Future-tense openers a stalled reply ends on ("I will now add the waypoint node ..."), as opposed to a finished
# summary, which reports what the graph now does and that it is in the draft.
_INTENT_PATTERN = re.compile(r"\b(?:I will|I'll|I am going to|I'm going to|I need to|Let me|Now I|Next,? I|First,? I)\b", re.IGNORECASE)


class AssistantSession:
    """Owns the message history across turns. Each turn the model sees the full current draft (injected into
    that turn's user message), but only the plain request text and the final reply are kept afterward --
    otherwise every past turn would carry a stale copy of the draft and its tool exchanges in the context window."""

    def __init__(self, toolbox, options: dict = None):
        self.toolbox = toolbox
        self.options = options or {"num_ctx": config.NUM_CTX, "temperature": config.TEMPERATURE,
                                   "num_predict": config.MAX_REPLY_TOKENS}
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def run_turn(self, user_text: str, draft: dict, capability_registry, target_platform_id: str, emit,
                 think: bool = False, should_stop=None, run_tool=None, agent_turn=None,
                 world_description: str = "") -> None:
        """Runs one agentic turn. `run_tool` defaults to the toolbox directly; the GUI passes a wrapper that
        executes it on the Tk thread. `agent_turn` defaults to the real Ollama loop, imported lazily so this
        module (and the editor) work without the `ollama` package installed."""
        if agent_turn is None:
            from mtofr.world.interface.agent.agent import run_agent_turn as agent_turn
        turn_start = len(self.messages)
        self.messages.append({"role": "user", "content": compose_user_message(
            user_text, draft, capability_registry, target_platform_id, world_description)})
        try:
            agent_turn(self.messages, think, emit, tools=self.toolbox.schemas,
                       run_tool=run_tool or self.toolbox.run, options=self.options, should_stop=should_stop,
                       detect_stall=self._detect_stall)
        finally:
            self._compact_turn(turn_start, user_text)

    def _detect_stall(self, content: str, truncated: bool = False):
        """A retry message if a reply with no real tool calls looks like a stall rather than a finished answer:
        calls typed as text (e.g. `add_node(node_id="a")`), a reply cut off by the length cap, or a last paragraph
        that announces a next step. A question to the user, or a summary saying the change is in the draft, is not a stall."""
        pattern = r"^\s*(?:" + "|".join(re.escape(name) for name in self.toolbox.names) + r")\("
        if re.search(pattern, content, re.MULTILINE):
            return TEXT_CALL_NUDGE
        if truncated:
            return TRUNCATED_NUDGE
        paragraphs = [paragraph.strip() for paragraph in content.strip().split("\n\n") if paragraph.strip()]
        last_paragraph = paragraphs[-1] if paragraphs else ""
        if (_INTENT_PATTERN.search(last_paragraph) and not last_paragraph.endswith("?")
                and "draft" not in last_paragraph.lower()):
            return INTENT_NUDGE
        return None

    def _compact_turn(self, turn_start: int, user_text: str) -> None:
        """Replaces this turn's messages with just the plain request and the model's last text reply."""
        final_reply = next((message for message in reversed(self.messages[turn_start:])
                            if message["role"] == "assistant" and message.get("content")), None)
        del self.messages[turn_start:]
        self.messages.append({"role": "user", "content": user_text})
        if final_reply is not None:
            self.messages.append({"role": "assistant", "content": final_reply["content"]})

    def reset(self) -> None:
        """Forgets the conversation (the draft itself is untouched)."""
        del self.messages[1:]
