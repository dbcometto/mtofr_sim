"""The built-in web panels, plus default_panels(): the static panel registry an interface
platform starts with. A custom panel is a WebPanel subclass plus its JavaScript half;
add it to a list like default_panels() and pass that as interface(..., build_panels=...)."""
from mtofr.environments.ground_plane.platforms.interface.web.panel import WebPanel
from mtofr.environments.ground_plane.platforms.interface.web.panels.editor import EditorPanel
from mtofr.environments.ground_plane.platforms.interface.web.panels.graph import GraphPanel
from mtofr.environments.ground_plane.platforms.interface.web.panels.live_control import LiveControlPanel
from mtofr.environments.ground_plane.platforms.interface.web.panels.world_viewer import WorldViewerPanel


def default_panels() -> list[WebPanel]:
    """Fresh instances of the built-in panels, in tab order (panels hold state, so never share
    them): the graph editor first, then Live Control, then the World Viewer."""
    editor = EditorPanel()   # the window's draft; the graph panel edits it
    # NOTE: the table Editor tab is turned off for now (the user's call); add `editor` to the
    # list to bring it back. Its draft still exists either way, since GraphPanel edits it.
    return [GraphPanel(editor), LiveControlPanel(), WorldViewerPanel()]
