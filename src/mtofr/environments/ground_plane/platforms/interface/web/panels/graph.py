"""Defines GraphPanel: the graphical mission editor. It edits the same draft as the window's
EditorPanel, and also shows the Target's live mission read-only."""
from mtofr.environments.ground_plane.platforms.interface.mission_editor import editor_document
from mtofr.environments.ground_plane.platforms.interface.web.config import BUILT_IN_PANEL_SCRIPT_DIRECTORY
from mtofr.environments.ground_plane.platforms.interface.web.panel import PanelContext, WebPanel
from mtofr.environments.ground_plane.platforms.interface.web.panels.editor import EditorPanel
from mtofr.mission.serialization import encode_mission_graph, encode_value
from mtofr.viz.mission_graph_view import compute_graph_layout


def _encode_layout(mission_graph: dict, pinned_positions: dict) -> dict:
    """Every node's position (pinned, or auto-placed for nodes without one) as node_id -> [x, y]."""
    return {node_id: list(position) for node_id, position in compute_graph_layout(mission_graph, pinned_positions).items()}


class GraphPanel(WebPanel):
    """A canvas editor over its EditorPanel's draft: every command is the EditorPanel's own
    (delegated, so there is one implementation and one undo history per window), and the
    state adds where each node sits. The browser draws the graph itself; node positions are
    the draft's editor data (EditorDocument.layout), auto-placed for nodes that have none."""
    name = "graph"
    title = "Graph"
    script_path = BUILT_IN_PANEL_SCRIPT_DIRECTORY / "graph.js"

    def __init__(self, editor: EditorPanel):
        """Edits `editor`'s draft."""
        self.editor = editor

    def state(self, context: PanelContext) -> dict:
        """The editor's state, plus every draft node's position, plus the Target's live mission
        (graph, positions, current values of its declared keys, gossiped status, and how long
        since the interface last synced with the Target), or None for "live" if no mission is known."""
        live = None
        view = context.view
        target_id = context.target_platform_id
        live_mission = view.missions.get(target_id)
        record = view.platforms.get(target_id)
        if live_mission is not None and record is not None:
            status = record.status
            stored = context.editor_store.get(live_mission.get("name"))
            live_document = editor_document.document_from_json(live_mission, stored)
            live = {
                "graph": encode_mission_graph(live_mission),
                "name": live_mission.get("name", ""),
                "layout": _encode_layout(live_mission, live_document.layout),
                "values": {key: encode_value(view.knowledge[key].value)
                           for key in live_mission["knowledge"] if key in view.knowledge},
                "active_node_id": status.active_node_id,
                "blocked": status.blocked,
                "overall_status": status.status,
                "capability_statuses": status.capability_statuses,
                "last_sync_age": view.sync_age(target_id),
            }
        document = self.editor.document
        return {
            **self.editor.state(context),
            "draft_layout": _encode_layout(document.graph, document.layout),
            "live": live,
        }

    def commands(self) -> dict:
        """Exactly the EditorPanel's commands."""
        return self.editor.commands()
