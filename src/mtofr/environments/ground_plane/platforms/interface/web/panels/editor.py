"""Defines EditorPanel: the web mission editor's draft. Holds one EditorDocument (a mission
graph plus editor-only data) with undo/redo, edits it locally, and pushes the graph alone as
a mesh write through the interface's own Backseater."""
import json

from mtofr.environments.ground_plane.platforms.interface.mission_editor import editor_document, graph_draft
from mtofr.environments.ground_plane.platforms.interface.mission_editor.assistant_tools import DraftToolbox, as_knowledge_value
from mtofr.environments.ground_plane.platforms.interface.mission_editor.draft_history import DraftHistory
from mtofr.environments.ground_plane.platforms.interface.mission_editor.editor_document import EditorDocument
from mtofr.environments.ground_plane.platforms.interface.web.config import BUILT_IN_PANEL_SCRIPT_DIRECTORY
from mtofr.environments.ground_plane.platforms.interface.web.encoding import condition_rows, encode_capabilities, knowledge_type_fields
from mtofr.environments.ground_plane.platforms.interface.web.panel import PanelContext, WebPanel, reply
from mtofr.mission.serialization import (
    JSON_INDENT, KNOWLEDGE_TYPES_BY_NAME, decode_mission_graph, default_knowledge_value, encode_mission_graph,
)
from mtofr.mission.validation import (
    MissionStructuralError, declared_types, find_binding_problems, find_capability_problems,
    find_condition_problems, verify_mission_structure,
)

TOOL_ERROR_PREFIX = "Error"   # DraftToolbox.run() returns "ok: ..." or "Error: ..."
EDITOR_FILE_SECTION = "editor"   # a saved file's editor-only section (plain mission loaders ignore it)
UNSET_KEY_MESSAGE = "no value yet: set it in Knowledge before pushing"
NO_START_MESSAGE = "the start node doesn't exist: set a start node"


class EditorPanel(WebPanel):
    """Load (live/blank/file), edit, validate, save, and push one draft.

    The draft is an EditorDocument: the mission graph plus the editor's own data about it
    (node positions, unset and following-Target key flags), undone as a whole. Graph edits go
    through DraftToolbox, the same 1:1 graph_draft command layer the LLM assistant uses, but
    with require_bindable off: an incomplete capability request is allowed while drafting and
    reported in `problems` instead (Validate and Push still refuse it). Editor-only steps
    (layout, key flags, the mission name, Retarget) run beside them in edit_batch.

    Only the graph is ever pushed. The editor data is kept in the shared editor store under
    the mission's name, and in a saved file's "editor" section."""
    name = "editor"
    title = "Editor"
    script_path = BUILT_IN_PANEL_SCRIPT_DIRECTORY / "editor.js"

    def __init__(self):
        """Starts on a blank draft."""
        self.history = DraftHistory(EditorDocument(graph_draft.blank_graph()))
        self.draft_source_platform_id = None   # platform_id the draft was loaded from, or None (new/from-file)

    @property
    def document(self) -> EditorDocument:
        """The current draft."""
        return self.history.draft

    def state(self, context: PanelContext) -> dict:
        """The encoded draft and its editor data, undo/redo availability, live problems, and
        what the forms need: the Target, its capabilities, and every knowledge type's fields."""
        document = self.document
        graph = document.graph
        return {
            "draft": encode_mission_graph(graph),
            "name": graph.get("name", ""),
            "draft_source": self.draft_source_platform_id,
            "target": context.target_platform_id,
            "can_undo": self.history.can_undo,
            "can_redo": self.history.can_redo,
            "layout": {node_id: list(position) for node_id, position in document.layout.items()},
            "unset_keys": sorted(document.unset_keys),
            "following_keys": sorted(document.following_keys),
            "draft_namespace": document.namespace_to_retarget(),
            "problems": self._live_problems(context),
            "edge_rows": {f"{source}#{index}": condition_rows(edge["condition"])
                          for source, edges in graph["edges"].items() for index, edge in enumerate(edges)},
            "target_capabilities": encode_capabilities(context.view.capabilities_of(context.target_platform_id)),
            "knowledge_types": knowledge_type_fields(),
        }

    def commands(self) -> dict:
        """Draft lifecycle, editing, undo/redo, validate, and push."""
        return {
            "load_live": self.load_live, "new_blank": self.new_blank,
            "load_file": self.load_file, "save_file": self.save_file,
            "edit": self.edit, "edit_batch": self.edit_batch,
            "move_nodes": self.move_nodes, "move_edge": self.move_edge, "retarget": self.retarget,
            "undo": self.undo, "redo": self.redo,
            "validate": self.validate, "push": self.push,
        }





    #===============# Draft Lifecycle #===============#

    def _start_new_draft(self, document: EditorDocument, source_platform_id: str | None) -> None:
        """Replaces the whole draft (an undoable action), recording where it came from."""
        self.draft_source_platform_id = source_platform_id
        self.history.set(document)

    def load_live(self, context: PanelContext) -> dict:
        """Loads a copy of the Target's mission graph, as gossiped to the interface platform, with
        the editor data stored under its name at push (if any) restored."""
        target_id = context.target_platform_id
        mission_graph = context.view.missions.get(target_id)
        if mission_graph is None:
            return self._fail(context, f"Load Live failed: no mission graph known here for '{target_id}'.")
        graph = graph_draft.load_draft(mission_graph)
        stored = context.editor_store.get(graph.get("name"))
        self._start_new_draft(editor_document.document_from_json(graph, stored), source_platform_id=target_id)
        restored = " (with its saved layout)" if stored is not None else ""
        context.log(f"Loaded live mission graph from '{target_id}'{restored}.")
        return reply(True, f"Loaded '{target_id}'s mission graph{restored}.")

    def new_blank(self, context: PanelContext) -> dict:
        """Starts a blank draft."""
        self._start_new_draft(EditorDocument(graph_draft.blank_graph()), source_platform_id=None)
        context.log("Started a new blank draft.")
        return reply(True, "Started a new blank draft.")

    def load_file(self, context: PanelContext, text: str, file_name: str = "the uploaded file") -> dict:
        """Loads a draft (and its "editor" section, if the file has one) from a mission-graph JSON file's text."""
        try:
            encoded = json.loads(text)
            document = editor_document.document_from_json(decode_mission_graph(encoded), encoded.get(EDITOR_FILE_SECTION))
        except (ValueError, KeyError, TypeError, AttributeError) as error:   # bad JSON, or not a mission graph
            return self._fail(context, f"Load failed for {file_name}: {error}")
        self._start_new_draft(document, source_platform_id=None)
        context.log(f"Loaded draft from {file_name}.")
        return reply(True, f"Loaded {file_name}.")

    def save_file(self, context: PanelContext) -> dict:
        """The draft as mission-graph JSON text plus its "editor" section, for the browser to download."""
        encoded = encode_mission_graph(self.document.graph)
        encoded[EDITOR_FILE_SECTION] = editor_document.sidecar_to_json(self.document)
        context.log("Saved draft to a downloaded file.")
        return reply(True, "Saved.", text=json.dumps(encoded, indent=JSON_INDENT))





    #===============# Editing #===============#

    def edit(self, context: PanelContext, tool: str, arguments: dict) -> dict:
        """Runs one step (see edit_batch) on the draft."""
        return self.edit_batch(context, steps=[{"tool": tool, "arguments": arguments}])

    def edit_batch(self, context: PanelContext, steps: list) -> dict:
        """Runs steps ([{"tool", "arguments"}, ...]) in order on a scratch copy of the draft,
        committing the result as one undo step only if every step succeeds (atomic: a failing
        step leaves the draft untouched, and its message is the reply). A step is a DraftToolbox
        tool, or an editor-only step (see _run_editor_step), which isn't an assistant tool."""
        document = self.document
        scratch = {"graph": document.graph}
        toolbox = DraftToolbox(
            get_draft=lambda: scratch["graph"],
            apply_draft=lambda new_graph: scratch.update(graph=new_graph),
            get_capabilities=lambda: context.view.capabilities_of(context.target_platform_id),
            require_bindable=False,
        )
        messages = []
        for step in steps:
            tool, arguments = step["tool"], step.get("arguments", {})
            if tool in self._editor_steps():
                document, message = self._run_editor_step(document, tool, arguments)
            else:
                scratch["graph"] = document.graph
                message = toolbox.run(tool, arguments)
                if not message.startswith(TOOL_ERROR_PREFIX):
                    document = editor_document.with_graph(document, scratch["graph"], tool, arguments)
            if message.startswith(TOOL_ERROR_PREFIX):
                return reply(False, message)
            messages.append(message)
        if document is not self.document:
            self.history.set(document)
        return reply(True, "; ".join(messages))

    def _editor_steps(self) -> dict:
        """Editor-only step name -> function(document, **arguments) -> (document, message)."""
        return {
            "move_nodes": self._move_nodes_step, "move_edge": self._move_edge_step,
            "declare_key": self._declare_key_step, "set_key_flags": self._set_key_flags_step,
            "set_mission_name": self._set_mission_name_step, "retarget": self._retarget_step,
        }

    def _run_editor_step(self, document: EditorDocument, tool: str, arguments: dict) -> tuple:
        """Applies one editor-only step, reporting like DraftToolbox.run() ("ok: ..." or "Error: ...")."""
        try:
            return self._editor_steps()[tool](document, **arguments)
        # An unknown node, key, or edge; a missing argument; or a value that isn't the right shape
        except (ValueError, IndexError, KeyError, TypeError) as error:
            return document, f"{TOOL_ERROR_PREFIX}: {tool} failed: {error}"

    @staticmethod
    def _move_nodes_step(document: EditorDocument, positions: dict) -> tuple:
        """Places nodes (node_id -> [x, y], layout units)."""
        return editor_document.move_nodes(document, positions), f"ok: moved {len(positions)} node(s)"

    @staticmethod
    def _move_edge_step(document: EditorDocument, source_id: str, index: int, new_index: int) -> tuple:
        """Changes an edge's priority within its source's list."""
        new_graph = graph_draft.move_edge(document.graph, source_id, index, new_index)
        return (editor_document.with_graph(document, new_graph, "move_edge", {}),
                f"ok: edge {index} of '{source_id}' is now edge {new_index}")

    @staticmethod
    def _declare_key_step(document: EditorDocument, key: str, type_name: str, value=None, unset: bool = False,
                          follows_target: bool = False) -> tuple:
        """Declares a key with `value` (a scalar's text or a field-text dict, as the forms send it),
        or, with no value, an unset placeholder holding its type's neutral default."""
        entry_type = KNOWLEDGE_TYPES_BY_NAME[type_name]
        if value is None:
            entry_value, unset = default_knowledge_value(entry_type), True
        else:
            entry_value = as_knowledge_value(entry_type, value)
        new_document = editor_document.declare_key(document, key, entry_type, entry_value, unset=unset, follows_target=follows_target)
        return new_document, f"ok: declared knowledge key '{key}' ({type_name}){' with no value yet' if unset else ''}"

    @staticmethod
    def _set_key_flags_step(document: EditorDocument, key: str, unset: bool | None = None,
                            follows_target: bool | None = None) -> tuple:
        """Sets or clears a key's editor flags."""
        return editor_document.set_key_flags(document, key, unset, follows_target), f"ok: updated '{key}'"

    @staticmethod
    def _set_mission_name_step(document: EditorDocument, name: str) -> tuple:
        """Renames the mission (empty clears the name)."""
        new_graph = graph_draft.set_mission_name(document.graph, name)
        return editor_document.with_graph(document, new_graph, "set_mission_name", {}), f"ok: mission name is now '{name.strip()}'"

    @staticmethod
    def _retarget_step(document: EditorDocument, old_namespace: str, new_namespace: str) -> tuple:
        """Renames every following key from `old_namespace` into `new_namespace`."""
        new_document, skipped = editor_document.retarget(document, old_namespace, new_namespace)
        skipped_note = f"; skipped (name already taken): {skipped}" if skipped else ""
        return new_document, f"ok: retargeted '{old_namespace}/' keys to '{new_namespace}/'{skipped_note}"

    def move_nodes(self, context: PanelContext, positions: dict) -> dict:
        """Places nodes (node_id -> [x, y], layout units) as one undo step: a whole drag, however many nodes moved."""
        return self.edit(context, "move_nodes", {"positions": positions})

    def move_edge(self, context: PanelContext, source_id: str, index: int, new_index: int) -> dict:
        """Changes an edge's priority within its source's list (edges are checked in order, first match wins)."""
        return self.edit(context, "move_edge", {"source_id": source_id, "index": index, "new_index": new_index})

    def retarget(self, context: PanelContext) -> dict:
        """Renames the draft's following keys from their namespace into the current Target's,
        as one undo step: the explicit "Retarget draft" action (a Target change alone never does)."""
        old_namespace = self.document.namespace_to_retarget()
        new_namespace = context.target_platform_id
        if old_namespace is None or new_namespace is None or old_namespace == new_namespace:
            return reply(True, "Nothing to retarget.")
        result = self.edit(context, "retarget", {"old_namespace": old_namespace, "new_namespace": new_namespace})
        context.log(f"Retarget: {result['message'].removeprefix('ok: ')}.")
        return result

    def undo(self, context: PanelContext) -> dict:
        """Restores the previous draft, if any."""
        message = "Undid last change." if self.history.undo() else "Nothing to undo."
        context.log(message)
        return reply(True, message)

    def redo(self, context: PanelContext) -> dict:
        """Re-applies the last undone draft, if any."""
        message = "Redid change." if self.history.redo() else "Nothing to redo."
        context.log(message)
        return reply(True, message)





    #===============# Problems #===============#

    def _live_problems(self, context: PanelContext) -> dict:
        """Everything currently wrong with the draft, for warning markers (each list holds messages):
        "requests" node -> request name -> list, "edges" edge key -> list, "keys" key -> list,
        "graph" a list. Capability checks need the Target's gossiped registry; without it they're skipped."""
        document = self.document
        graph = document.graph
        known_types = declared_types(graph)
        registry = context.view.capabilities_of(context.target_platform_id)

        requests = {}
        for node_id, node in graph["nodes"].items():
            for request_name, request in node["capabilities"].items():
                bound_keys = {*request.get("inputs", {}).values(), *request.get("outputs", {}).values()}
                messages = find_capability_problems(request, known_types, registry) if registry is not None else []
                messages += [f"key '{key}' has {UNSET_KEY_MESSAGE}" for key in sorted(bound_keys & document.unset_keys)]
                if messages:
                    requests.setdefault(node_id, {})[request_name] = messages

        edges = {}
        for source, edge_list in graph["edges"].items():
            for index, edge in enumerate(edge_list):
                messages = find_condition_problems(edge["condition"], known_types)
                if messages:
                    edges[f"{source}#{index}"] = messages

        return {
            "requests": requests,
            "edges": edges,
            "keys": {key: [UNSET_KEY_MESSAGE] for key in sorted(document.unset_keys)},
            "graph": [] if graph["start"] in graph["nodes"] else [NO_START_MESSAGE],
        }

    def _find_problems(self, context: PanelContext) -> list[str]:
        """The checks a push enforces, run here against the view: structure, bindings on the Target
        (if its capabilities are known), condition literal types, unset keys, and the start node."""
        graph = self.document.graph
        try:
            verify_mission_structure(graph)
        except MissionStructuralError as error:
            return [str(error)]
        problems = find_binding_problems(graph, context.view.capabilities_of(context.target_platform_id))
        live = self._live_problems(context)
        problems += [f"edge {key}: {message}" for key, messages in live["edges"].items() for message in messages]
        problems += [f"key '{key}' has {UNSET_KEY_MESSAGE}" for key in live["keys"]]
        return problems + live["graph"]





    #===============# Validate and Push #===============#

    def validate(self, context: PanelContext) -> dict:
        """Checks the draft as a push would."""
        target_id = context.target_platform_id
        problems = self._find_problems(context)
        if problems:
            return self._fail(context, f"Validation failed for '{target_id}':\n" + "\n".join(f"  - {problem}" for problem in problems))
        if context.view.capabilities_of(target_id) is None:
            message = f"Draft is structurally valid ('{target_id}'s capabilities aren't known here, so bindings weren't checked)."
        else:
            message = f"Draft is structurally valid and binds on '{target_id}'."
        context.log(message)
        return reply(True, message)

    def push(self, context: PanelContext) -> dict:
        """Queues the draft's graph as a mesh write to the Target's Mission entry (privilege-checked
        when it runs), and keeps its editor data in the editor store under the mission's name."""
        target_id = context.target_platform_id
        if target_id is None:
            return self._fail(context, "Push failed: no target platform selected.")
        problems = self._find_problems(context)
        if problems:
            return self._fail(context, f"Push failed for '{target_id}':\n" + "\n".join(f"  - {problem}" for problem in problems))
        if self.draft_source_platform_id is not None and self.draft_source_platform_id != target_id:
            # NOTE: doesn't block the push (reusing a draft across platforms may be
            # intentional), just makes the mismatch visible, since pushing an
            # unmodified draft to the wrong target once silently duplicated a mission.
            context.log(f"Warning: pushing a draft loaded from '{self.draft_source_platform_id}' "
                        f"to a different platform '{target_id}'.")
        document = self.document
        graph = document.graph
        name = graph.get("name")
        if name:
            # NOTE: recorded when queued, not when the write lands: the sim thread must not touch the store.
            context.editor_store[name] = editor_document.sidecar_to_json(document)
        else:
            context.log("Note: this mission has no name, so its layout won't come back on Load Live. Name it to keep it.")

        def write_draft(backseater) -> str:
            """Writes the graph to the Target's Mission entry through the interface's own Backseater."""
            backseater.publish("mission", target_id, graph)
            return "written here; it reaches the target on the next mesh sync"

        context.submit(f"Push draft to '{target_id}'", write_draft)
        return reply(True, f"Queued push to '{target_id}'.")

    @staticmethod
    def _fail(context: PanelContext, message: str) -> dict:
        """Logs `message` and returns it as a failed reply."""
        context.log(message)
        return reply(False, message)
