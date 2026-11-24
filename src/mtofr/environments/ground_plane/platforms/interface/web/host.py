"""Defines WebHost: the hand-off point between the sim thread (which owns the interface
platform's Backseater) and the web server's threads (which serve the panels, one set per
browser window)."""
import queue
import threading
import time
from collections import deque
from typing import Callable

from mtofr.environments.ground_plane.maps import GroundMap
from mtofr.environments.ground_plane.platforms.interface.web.config import (
    CONSOLE_LINE_LIMIT, MAX_SESSIONS, SESSION_IDLE_TIMEOUT,
)
from mtofr.environments.ground_plane.platforms.interface.web.panel import PanelContext, UnknownCommandError, WebPanel
from mtofr.environments.ground_plane.platforms.interface.web.view import InterfaceView


class _Session:
    """One browser window's own state: a fresh set of panels (so its own draft and undo
    history), its Target, and its console."""

    def __init__(self, panels: list[WebPanel], now: float):
        """Starts with no Target chosen and an empty console."""
        self.panels = {panel.name: panel for panel in panels}
        self.target_platform_id = None   # what this window's Target dropdown chose; None until set
        self.last_seen = now              # s, WebHost's clock
        self._console = deque(maxlen=CONSOLE_LINE_LIMIT)
        self._console_lock = threading.Lock()   # the sim thread logs this window's write outcomes too

    def log(self, message: str) -> None:
        """Appends a console line (from either thread)."""
        with self._console_lock:
            self._console.append(message)

    def console(self) -> list[str]:
        """A copy of the console lines, oldest first."""
        with self._console_lock:
            return list(self._console)


class WebHost:
    """Owns the latest InterfaceView, a queue of pending writes, and one _Session per
    browser window (keyed by the id the page sends with every request).

    Threading: on_tick() runs on the sim thread (from the interface Frontseater's tick) and
    is the only code that touches the Backseater: it runs every queued write, then captures
    a fresh view. Everything else runs on web server threads, reading the latest view, which
    every session shares. Session and panel calls are serialized by `lock`, which is never
    held while waiting on the sim thread (writes are queued, not awaited), so a paused sim
    can't deadlock the UI: reads just stay as of the last tick, and writes wait in the queue."""

    def __init__(self, own_platform_id: str, build_panels: Callable[[], list[WebPanel]],
                 clock: Callable[[], float] = time.monotonic):
        """Starts with an empty view until the first tick; raises ValueError on duplicate panel names.
        `clock` (s) times session idleness; tests inject a fake one."""
        catalog = build_panels()   # one set never used for state: names, titles, and script paths
        names = [panel.name for panel in catalog]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate web panel names: {names}")
        self.own_platform_id = own_platform_id
        self.panels = {panel.name: panel for panel in catalog}
        self.view = InterfaceView(own_platform_id)   # replaced (by assignment, atomically) every tick
        self.lock = threading.Lock()   # serializes session and panel calls
        self._build_panels = build_panels
        self._clock = clock
        self._sessions = {}   # session id -> _Session, oldest-created first
        self._pending_writes = queue.Queue()   # (description, write(backseater) -> str, log)
        # NOTE: in memory only: a restart forgets it (a saved file keeps its own copy).
        self.editor_store = {}   # mission name -> editor sidecar JSON, recorded at push (see PanelContext)

    #===============# Sim Thread #===============#

    def on_tick(self, backseater, ground_map: GroundMap | None = None) -> None:
        """Runs every queued write through `backseater`, logging each outcome to the window that
        queued it, then captures a fresh view (with `ground_map`, the hardware's sensed map)."""
        # NOTE: get_nowait() after empty() is safe here: this is the queue's only consumer.
        while not self._pending_writes.empty():
            description, write, log = self._pending_writes.get_nowait()
            # NOTE: catches everything: one bad write must not cost the interface its tick.
            try:
                log(f"{description}: {write(backseater)}")
            except Exception as error:
                log(f"{description} failed: {error}")
        self.view = InterfaceView.capture(backseater, ground_map)





    #===============# Web Server Threads #===============#

    def queue_write(self, description: str, write, log: Callable[[str], None]) -> None:
        """Queues `write(backseater) -> str` for the next tick; its outcome goes to `log`."""
        self._pending_writes.put((description, write, log))
        log(f"Queued: {description} (applies on the next tick)")

    def describe_panels(self) -> list[dict]:
        """[{"name", "title"}, ...] in tab order, for the browser to load each panel's script."""
        return [{"name": panel.name, "title": panel.title} for panel in self.panels.values()]

    def state(self, session_id: str) -> dict:
        """Everything one window polls: the platforms, its Target, its console, and each of its panels' state."""
        with self.lock:
            session = self._session(session_id)
            context = self._context(session)
            return {
                "own_platform_id": self.own_platform_id,
                "platforms": sorted(context.view.platforms),
                "target": context.target_platform_id,
                "target_sync_age": context.view.sync_age(context.target_platform_id),   # s, or None
                "console": session.console(),
                "panels": {name: panel.state(context) for name, panel in session.panels.items()},
            }

    def set_target(self, session_id: str, platform_id: str) -> None:
        """Selects the Target one window's panels work against; raises ValueError if it isn't known yet."""
        with self.lock:
            session = self._session(session_id)
            if platform_id not in self.view.platforms:
                raise ValueError(f"unknown platform '{platform_id}'")
            session.target_platform_id = platform_id

    def command(self, session_id: str, panel_name: str, command: str, arguments: dict) -> dict:
        """Runs one panel command in one window; raises UnknownCommandError for an unknown panel or command."""
        with self.lock:
            session = self._session(session_id)
            panel = session.panels.get(panel_name)
            if panel is None:
                raise UnknownCommandError(f"no panel '{panel_name}'")
            return panel.handle(command, arguments, self._context(session))

    def session_count(self) -> int:
        """How many windows currently have a session."""
        with self.lock:
            return len(self._sessions)

    def _session(self, session_id: str) -> _Session:
        """The session for `session_id` (created on first sight), marked as just seen; sweeps
        idle sessions and enforces MAX_SESSIONS first. Call with `lock` held."""
        now = self._clock()
        self._sessions = {known_id: session for known_id, session in self._sessions.items()
                          if now - session.last_seen <= SESSION_IDLE_TIMEOUT}
        session = self._sessions.get(session_id)
        if session is None:
            if len(self._sessions) >= MAX_SESSIONS:
                longest_idle_id = min(self._sessions, key=lambda known_id: self._sessions[known_id].last_seen)
                del self._sessions[longest_idle_id]
            session = _Session(self._build_panels(), now)
            self._sessions[session_id] = session
        session.last_seen = now
        return session

    def _context(self, session: _Session) -> PanelContext:
        """A PanelContext for `session` over the latest view; call with `lock` held."""
        view = self.view

        def submit(description: str, write) -> None:
            """Queues `write` with its outcome bound for this window's console."""
            self.queue_write(description, write, session.log)

        return PanelContext(view=view, target_platform_id=self._resolve_target(session, view),
                            submit=submit, log=session.log, editor_store=self.editor_store)

    def _resolve_target(self, session: _Session, view: InterfaceView) -> str | None:
        """The window's chosen Target if the view knows it, else the first other platform known (None if none)."""
        if session.target_platform_id in view.platforms:
            return session.target_platform_id
        other_platform_ids = sorted(platform_id for platform_id in view.platforms if platform_id != self.own_platform_id)
        return other_platform_ids[0] if other_platform_ids else None
