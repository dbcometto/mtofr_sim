"""Defines AssistantWindow: a chat Toplevel whose LLM edits the same draft the MissionEditorWindow shows."""
import importlib.util
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from mtofr.world.interface.agent import config
from mtofr.world.interface.mission_editor.assistant_prompt import describe_live, describe_world
from mtofr.world.interface.mission_editor.assistant_session import AssistantSession
from mtofr.world.interface.mission_editor.assistant_tools import DraftToolbox

# How often the Tk thread drains events from the worker thread, in milliseconds.
EVENT_POLL_MS = 50


class _ToolRequest:
    """A tool call the worker thread needs run on the Tk thread, plus where its result goes."""
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments
        self.result = None
        self.done = threading.Event()


class AssistantWindow(tk.Toplevel):
    """Chat pane for the mission-editing assistant. The model runs on a worker thread (Ollama calls block);
    everything it reports, and every tool it calls, is handed back through one FIFO queue and applied on the
    Tk thread, since tools mutate the editor's draft via its `_set_draft()` choke point and so touch widgets.
    All edits from one user message form a single undo step in the editor."""

    def __init__(self, editor, agent_turn=None):
        super().__init__(editor)
        self.title("Mission Assistant")
        self.geometry("560x720")
        self.editor = editor
        self.agent_turn = agent_turn   # None = the real Ollama loop; tests inject a fake
        self.toolbox = DraftToolbox(get_draft=lambda: editor.draft, apply_draft=editor.apply_draft_edit,
                                    get_capabilities=self._target_capabilities)
        self.session = AssistantSession(self.toolbox)

        self._events = queue.Queue()        # worker -> Tk thread: ("emit", kind, data) / ("tool", request) / ("done", error)
        self._stop_requested = threading.Event()
        self._closed = threading.Event()
        self._busy = False
        self._poll_job = None
        self._phase = None                  # "reading" / "generating" / "tool" while a turn runs, for the live status line
        self._phase_started = 0.0           # time.monotonic() when the phase began
        self._segment = None                # kind of text last written ("thinking"/"content"/"tool"), for line breaks between kinds
        self._noted_target = editor.target_platform_id.get()   # last target platform written to the transcript
        self._pending_tool_arguments = ""   # formatted args of the tool call awaiting its result, for the Console line

        self.think = tk.BooleanVar(value=config.THINK)
        self.status_text = tk.StringVar()
        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self.close)
        # The platform dropdown here and the editor's top bar share one variable; either may change it.
        self._target_trace = editor.target_platform_id.trace_add("write", lambda *arguments: self._note_target_change())
        self._append(f"[target platform: {self._noted_target}]\n", "tool", segment="tool")
        if self.agent_turn is None and importlib.util.find_spec("ollama") is None:
            self._append("The 'ollama' Python package is not installed (pip install ollama), so the assistant is unavailable.\n", "error")
            self.send_button.config(state="disabled")
        elif self.agent_turn is None:
            self._start_warm_up()
        self._poll_job = self.after(EVENT_POLL_MS, self._poll)

    #==========# Layout #==========#

    def _build_layout(self) -> None:
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 0))
        ttk.Label(top, text="Target platform:").pack(side=tk.LEFT, padx=(0, 4))
        self.platform_dropdown = ttk.Combobox(top, values=list(self.editor.world.backseaters), state="readonly", width=14,
                                              textvariable=self.editor.target_platform_id)
        self.platform_dropdown.pack(side=tk.LEFT)
        self.platform_dropdown.bind("<<ComboboxSelected>>", lambda event: self.editor._on_target_platform_changed())

        bottom = ttk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=6)
        self.input_entry = ttk.Entry(bottom)
        self.input_entry.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        self.input_entry.bind("<Return>", lambda event: self._on_send())
        buttons = ttk.Frame(bottom)
        buttons.pack(side=tk.TOP, fill=tk.X)
        self.send_button = ttk.Button(buttons, text="Send", command=self._on_send)
        self.send_button.pack(side=tk.LEFT, padx=(0, 4))
        self.stop_button = ttk.Button(buttons, text="Stop", command=self._on_stop, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="New Chat", command=self._on_new_chat).pack(side=tk.LEFT, padx=4)
        ttk.Checkbutton(buttons, text="Enable thinking (slower)", variable=self.think).pack(side=tk.LEFT, padx=12)
        ttk.Label(buttons, textvariable=self.status_text).pack(side=tk.RIGHT)
        # Moves while a turn runs, so a long silent stretch (e.g. the model writing a tool call) still shows the window is alive.
        self.activity_bar = ttk.Progressbar(buttons, mode="indeterminate", length=70)
        self.activity_bar.pack(side=tk.RIGHT, padx=6)

        text_frame = ttk.Frame(self)
        text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))
        self.transcript = tk.Text(text_frame, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.transcript.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.transcript.tag_configure("user", foreground="#1a4fa0", font=("TkDefaultFont", 10, "bold"))
        self.transcript.tag_configure("tool", foreground="#6a6a6a", font=("TkFixedFont", 9))
        self.transcript.tag_configure("thinking", foreground="#9a9a9a", font=("TkDefaultFont", 9, "italic"))
        self.transcript.tag_configure("error", foreground="#b00020")
        self.transcript.tag_configure("separator", foreground="#2e7d32", font=("TkFixedFont", 9, "bold"))

    def _append(self, text: str, tag: str = None, segment: str = None) -> None:
        """Appends to the transcript. Follows the output only if the user was already scrolled to the bottom,
        so scrolling up to read earlier text isn't yanked back down. `segment` starts a new line (and, after
        thinking, a blank line) whenever the kind of text changes."""
        at_bottom = self.transcript.yview()[1] >= 0.999
        self.transcript.configure(state="normal")
        if segment is not None and segment != self._segment:
            if self.transcript.get("end-2c", "end-1c") not in ("\n", ""):
                self.transcript.insert(tk.END, "\n")
            if self._segment == "thinking":
                self.transcript.insert(tk.END, "\n")
            self._segment = segment
        self.transcript.insert(tk.END, text, tag)
        if at_bottom:
            self.transcript.see(tk.END)
        self.transcript.configure(state="disabled")

    def _target_capabilities(self):
        """The currently selected target platform's CapabilityRegistry, or None. Only called on the Tk thread (tools run there)."""
        backseater = self.editor.world.backseaters.get(self.editor.target_platform_id.get())
        return backseater.capabilities() if backseater is not None else None

    def _note_target_change(self) -> None:
        """Writes a transcript line when the target platform changes, since the draft and chat history carry over."""
        target_id = self.editor.target_platform_id.get()
        if target_id != self._noted_target and self.winfo_exists():
            self._noted_target = target_id
            self._append(f"[target platform: {target_id}]\n", "tool", segment="tool")

    #==========# User actions #==========#

    def _on_send(self) -> None:
        user_text = self.input_entry.get().strip()
        if not user_text or self._busy or str(self.send_button.cget("state")) == "disabled":
            return
        self.input_entry.delete(0, tk.END)
        self._append(f"\nYou: {user_text}\n", "user")
        self._segment = None
        self._set_busy(True)
        self._stop_requested.clear()
        self.editor.begin_undo_group()   # the whole turn becomes one Ctrl+Z

        # Everything the worker needs is captured here, on the Tk thread.
        target_id = self.editor.target_platform_id.get()
        backseater = self.editor.world.backseaters.get(target_id)
        registry = backseater.capabilities() if backseater is not None else None
        world_description = "\n".join(filter(None, (
            describe_world(getattr(self.editor.world.environment, "ground_map", None),
                           self.editor.world.get_states().get(target_id)),
            describe_live(backseater, self.editor.draft))))
        arguments = (user_text, self.editor.draft, registry, target_id, self.think.get(), world_description)
        threading.Thread(target=self._run_turn_worker, args=arguments, daemon=True).start()

    def _on_stop(self) -> None:
        self._stop_requested.set()
        self.status_text.set("Stopping...")

    def _on_new_chat(self) -> None:
        if self._busy:
            return
        self.session.reset()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", tk.END)
        self.transcript.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.stop_button.config(state="normal" if busy else "disabled")
        self.platform_dropdown.config(state="disabled" if busy else "readonly")   # the target is captured at Send
        self._phase = None
        if busy:
            self.activity_bar.start(15)
            self.status_text.set("Working...")
        else:
            self.activity_bar.stop()
            self.status_text.set("Ready")

    def _set_phase(self, phase: str) -> None:
        """Marks what the current turn is waiting on, so the status line can count up the wait."""
        self._phase = phase
        self._phase_started = time.monotonic()
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Status line with a live seconds counter. A tool call only appears once the model has finished writing it,
        so the 'generating' text says so rather than leaving a silent wait unexplained."""
        if not self._busy or self._phase is None:
            return
        seconds = int(time.monotonic() - self._phase_started)
        text = {"reading": f"Reading prompt... {seconds}s",
                "generating": f"Model writing (a tool call shows only when finished)... {seconds}s",
                "tool": "Applying tool..."}[self._phase]
        if self._stop_requested.is_set():
            text = "Stopping... " + text
        if self.status_text.get() != text:
            self.status_text.set(text)

    #==========# Worker thread #==========#
    # Nothing below this line may touch Tk widgets; it only puts events on self._events.

    def _run_turn_worker(self, user_text, draft, registry, target_id, think, world_description) -> None:
        error = None
        try:
            self.session.run_turn(
                user_text, draft, registry, target_id,
                emit=lambda kind, data: self._events.put(("emit", kind, data)),
                think=think, should_stop=self._stop_requested.is_set,
                run_tool=self._run_tool_on_tk_thread, agent_turn=self.agent_turn,
                world_description=world_description)
        except ConnectionError:
            error = "Could not reach Ollama. Is it running? (start the app, or run `ollama serve`)"
        except Exception as exception:
            error = f"{type(exception).__name__}: {exception}"
        self._events.put(("done", error))

    def _run_tool_on_tk_thread(self, name: str, arguments: dict) -> str:
        """Hands a tool call to the Tk thread and blocks until it has run."""
        request = _ToolRequest(name, arguments)
        self._events.put(("tool", request))
        while not request.done.wait(0.1):
            if self._closed.is_set():
                return "Error: the assistant window was closed."
        return request.result

    def _start_warm_up(self) -> None:
        """Loads the model in the background so the first request doesn't pay for it."""
        def warm_up_worker():
            try:
                from mtofr.world.interface.agent.agent import warm_up
                warm_up(self.session.messages, tools=self.toolbox.schemas, options=self.session.options)
            except Exception as exception:
                self._events.put(("emit", "warm_up_failed", f"{type(exception).__name__}: {exception}"))
        threading.Thread(target=warm_up_worker, daemon=True).start()

    #==========# Tk thread event handling #==========#

    def _poll(self) -> None:
        self._poll_job = None
        try:
            while True:
                self._handle_event(self._events.get_nowait())
        except queue.Empty:
            pass
        self._refresh_status()
        if not self._closed.is_set():
            self._poll_job = self.after(EVENT_POLL_MS, self._poll)

    def _handle_event(self, event: tuple) -> None:
        if event[0] == "tool":
            request = event[1]
            try:
                request.result = self.toolbox.run(request.name, request.arguments)
            except Exception as exception:   # run() shouldn't raise, but a tool must never kill the pump
                request.result = f"Error while running {request.name}: {exception}"
            request.done.set()
        elif event[0] == "done":
            self.editor.end_undo_group()
            self._set_busy(False)
            if event[1]:
                self._append(f"{event[1]}\n", "error")
                self.editor._log(f"[assistant] {event[1]}")
            self._append("\n" + "=" * 18 + " done -- waiting for you " + "=" * 18 + "\n", "separator", segment="separator")
        else:
            self._handle_emit(event[1], event[2])

    def _handle_emit(self, kind: str, data) -> None:
        if kind == "loop":
            self._set_phase("reading")   # the model processes its whole input before the first token
            if data["iteration"] == 1:
                self._append("Assistant:", "user", segment="label")
            else:   # a visible marker per model call, so a multi-call turn shows progress between tool results
                self._append(f"[model call {data['iteration']}/{data['max']}]\n", "tool", segment="tool")
        elif kind == "generating":
            self._set_phase("generating")
        elif kind == "thinking":   # always shown when the model produces any; the checkbox only decides whether it does
            self._append(data, "thinking", segment="thinking")
        elif kind == "content":
            self._append(data, segment="content")
        elif kind == "tool_call":
            self._set_phase("tool")
            self._pending_tool_arguments =", ".join(f"{name}={value!r}" for name, value in data["arguments"].items())
            self._append(f"  > {data['name']}({self._pending_tool_arguments})\n", "tool", segment="tool")
        elif kind == "tool_result":
            self._append(f"  = {data['result']}\n", "tool", segment="tool")
            self.editor._log(f"[assistant] {data['name']}({self._pending_tool_arguments}) -> {data['result']}")
        elif kind == "interrupted":
            self._append("[stopped]\n", "tool", segment="tool")
            self.editor._log("[assistant] stopped by user.")
        elif kind == "nudge":
            self._append(f"[nudge: {data}]\n", "tool", segment="tool")
            self.editor._log(f"[assistant] nudged the model (it stalled without tool calls): {data}")
        elif kind == "limit":
            self._append(f"[stopped: reached the maximum of {config.MAX_ITERATIONS} model calls]\n", "tool", segment="tool")
            self.editor._log(f"[assistant] stopped after {config.MAX_ITERATIONS} model calls without finishing.")
        elif kind == "stats":
            summary = (f"model call: read {data['prompt_tokens']} prompt tokens in {data['prompt_seconds']:.0f}s, "
                       f"wrote {data['tokens']} tokens in {data['seconds']:.0f}s ({data['rate']:.1f} tok/s); "
                       f"total {data['total_seconds']:.0f}s, of which model loading {data['load_seconds']:.0f}s")
            self.editor._log(f"[assistant] {summary}")
            self._append(f"  ({data['total_seconds']:.0f}s, {data['tokens']} tokens)\n", "tool", segment="tool")
        elif kind == "warm_up_failed":
            self._append(f"Model warm-up failed: {data}\n", "error")

    #==========# Lifecycle #==========#

    def close(self) -> None:
        """Stops any running turn and destroys the window; tolerant of Tk already being torn down."""
        self._closed.set()
        self._stop_requested.set()
        try:
            self.editor.target_platform_id.trace_remove("write", self._target_trace)
            if self._poll_job is not None:
                self.after_cancel(self._poll_job)
            if self._busy:
                self.editor.end_undo_group()
            self.destroy()
        except tk.TclError:
            pass
