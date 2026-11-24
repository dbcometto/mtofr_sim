"""Settings for the interface platform's web UI."""
from pathlib import Path

STATIC_DIRECTORY = Path(__file__).parent / "static"   # the page's own files
BUILT_IN_PANEL_SCRIPT_DIRECTORY = STATIC_DIRECTORY / "panels"   # the built-in panels' JavaScript halves

# NOTE: "0.0.0.0" would expose the UI (and its privilege-0 mission push) to the whole
# network with no authentication; keep localhost unless that is intended.
WEB_HOST = "127.0.0.1"
# TODO: one port for every interface platform, so two in one sim would collide.
WEB_PORT = 8765
OPEN_BROWSER_ON_START = True

CONSOLE_LINE_LIMIT = 500   # per window; oldest console lines are dropped past this

# Per-window sessions (each holds its own Target, draft, undo history, and console)
SESSION_IDLE_TIMEOUT = 3600.0   # s without a request before a window's session is dropped
MAX_SESSIONS = 32               # past this, the longest-idle session is dropped
