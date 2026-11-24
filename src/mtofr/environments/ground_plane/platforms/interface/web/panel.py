"""Defines the web UI's panel seam: WebPanel, the base every panel (built-in or custom)
implements, and PanelContext, what a panel is handed on each call. A panel is a whole UI
module: a Python half (this interface) plus a JavaScript half (its `script_path`, which
calls registerPanel() in the browser; see static/app.js)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mtofr.environments.ground_plane.platforms.interface.web.view import InterfaceView


class UnknownCommandError(LookupError):
    """A panel was asked to run a command it doesn't have."""


@dataclass(frozen=True)
class PanelContext:
    """Everything a panel may use, on one call:
    - `view`: the latest InterfaceView (read-only);
    - `target_platform_id`: the platform the UI's Target dropdown has selected (or None);
    - `submit(description, write)`: queues `write(backseater) -> str` to run on the sim
      thread at the interface platform's next tick, where it may publish() through the
      interface's own Backseater; returns at once, and the outcome goes to the console;
    - `log(message)`: appends a line to the console;
    - `editor_store`: mission name -> editor-only data (layout, key flags) for a pushed mission,
      shared by every window, so Load Live can restore what the mission graph doesn't carry."""
    view: InterfaceView
    target_platform_id: str | None
    submit: Callable[[str, Callable], None]
    log: Callable[[str], None]
    editor_store: dict


class WebPanel(ABC):
    """One tab of the web UI. Both methods run on a web server thread, one call at a time
    across all panels (WebHost serializes them), and may touch only the panel's own state
    and what the context offers -- never a Backseater directly."""
    name: str          # unique; the JS registerPanel() key and the URL segment
    title: str         # tab label
    script_path: Path  # this panel's JavaScript half, served at /panels/<name>.js

    @abstractmethod
    def state(self, context: PanelContext) -> dict:
        """This panel's JSON-native state for the browser, polled about once a second."""

    @abstractmethod
    def commands(self) -> dict:
        """command name -> method(context, **arguments) -> {"ok": bool, "message": str, ...}."""

    def asset(self, asset_name: str, view: InterfaceView) -> tuple[bytes, str] | None:
        """(body, content type) for a file this panel serves at /panels/<name>/assets/<asset_name>,
        or None (the default) if it has none by that name. Session-free, since an <img> can't send
        the session header: called on the WebHost's catalog panel, never a window's own panels."""
        return None

    def handle(self, command: str, arguments: dict, context: PanelContext) -> dict:
        """Runs one command; raises UnknownCommandError, or TypeError on bad arguments."""
        method = self.commands().get(command)
        if method is None:
            raise UnknownCommandError(f"panel '{self.name}' has no command '{command}'")
        return method(context, **arguments)


def reply(ok: bool, message: str, **extra) -> dict:
    """A command's result in the shape the browser expects."""
    return {"ok": ok, "message": message, **extra}
