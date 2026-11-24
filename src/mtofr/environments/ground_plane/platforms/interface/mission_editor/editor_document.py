"""Defines EditorDocument: a draft mission graph plus the web editor's own data about it (where
each node sits, and per-key flags), which never goes into the mission graph itself. UI-free,
so it is testable without a browser and reusable by another editor."""
from collections import Counter
from dataclasses import dataclass, field, replace

from mtofr.environments.ground_plane.platforms.interface.mission_editor import graph_draft


#========================================#
# Config
#========================================#

NAMESPACE_SEPARATOR = "/"
RENAME_NODE_TOOL = "rename_node"
RENAME_KEY_TOOL = "rename_knowledge_key"
EDIT_KEY_TOOL = "edit_knowledge_key"







#========================================#
# Keys and Namespaces
#========================================#

def split_key(key: str) -> tuple[str, str]:
    """A knowledge key as (namespace, name), split at its last "/" ("" namespace if it has none)."""
    namespace, _, name = key.rpartition(NAMESPACE_SEPARATOR)
    return namespace, name


def join_key(namespace: str, name: str) -> str:
    """namespace + "/" + name, or just name for an empty namespace."""
    return f"{namespace}{NAMESPACE_SEPARATOR}{name}" if namespace else name







#========================================#
# Editor Document
#========================================#

@dataclass(frozen=True)
class EditorDocument:
    """One draft as the web editor holds it (and undoes it, as a whole):
    - `graph`: the mission graph itself, exactly what a push sends;
    - `layout`: node_id -> (x, y), where the operator placed each node (layout units, +y up);
    - `unset_keys`: placeholder keys made by "+ New key..." whose value the operator hasn't
      set yet (a push is refused while any remain: a default like Location(0, 0) must never
      pass for a real value);
    - `following_keys`: keys whose namespace was left at the default (the Target), which
      "Retarget draft" renames to a new Target's namespace.
    Like the graph, a document is never changed in place."""
    graph: dict
    layout: dict = field(default_factory=dict)
    unset_keys: frozenset = frozenset()
    following_keys: frozenset = frozenset()

    def namespace_to_retarget(self) -> str | None:
        """The namespace most following keys use (the Target the draft's default keys were made
        for), or None if no key follows the Target."""
        counts = Counter(split_key(key)[0] for key in self.following_keys)
        return counts.most_common(1)[0][0] if counts else None


def with_graph(document: EditorDocument, new_graph: dict, tool: str, arguments: dict) -> EditorDocument:
    """`document` after a graph edit by `tool` (a DraftToolbox tool name, with its arguments):
    carries positions and flags through renames, clears `unset` when a key's value is edited,
    and drops entries for nodes and keys that no longer exist."""
    layout = dict(document.layout)
    unset_keys = set(document.unset_keys)
    following_keys = set(document.following_keys)

    if tool == RENAME_NODE_TOOL and arguments.get("old_id") in layout:
        layout[arguments["new_id"]] = layout.pop(arguments["old_id"])
    elif tool == RENAME_KEY_TOOL:
        for flagged in (unset_keys, following_keys):
            if arguments.get("old_key") in flagged:
                flagged.discard(arguments["old_key"])
                flagged.add(arguments["new_key"])
    elif tool == EDIT_KEY_TOOL:
        unset_keys.discard(arguments.get("key"))   # the operator gave it a value

    node_ids = set(new_graph["nodes"])
    keys = set(new_graph["knowledge"])
    return EditorDocument(
        graph=new_graph,
        layout={node_id: position for node_id, position in layout.items() if node_id in node_ids},
        unset_keys=frozenset(unset_keys & keys),
        following_keys=frozenset(following_keys & keys),
    )


def move_nodes(document: EditorDocument, positions: dict) -> EditorDocument:
    """Places each node in `positions` (node_id -> (x, y)), keeping every other node's position;
    raises ValueError naming any node that doesn't exist."""
    unknown_node_ids = sorted(set(positions) - set(document.graph["nodes"]))
    if unknown_node_ids:
        raise ValueError(f"can't place node(s) that don't exist: {unknown_node_ids}")
    placed = {node_id: (float(x), float(y)) for node_id, (x, y) in positions.items()}
    return replace(document, layout={**document.layout, **placed})


def declare_key(document: EditorDocument, key: str, entry_type: type, value, unset: bool = False,
                follows_target: bool = False) -> EditorDocument:
    """Declares a knowledge key, flagged unset (a placeholder) and/or following the Target;
    raises ValueError if it already exists."""
    new_graph = graph_draft.add_knowledge_key(document.graph, key, entry_type, value)
    return replace(
        document, graph=new_graph,
        unset_keys=document.unset_keys | {key} if unset else document.unset_keys,
        following_keys=document.following_keys | {key} if follows_target else document.following_keys,
    )


def set_key_flags(document: EditorDocument, key: str, unset: bool | None = None,
                  follows_target: bool | None = None) -> EditorDocument:
    """Sets (True), clears (False), or leaves (None) each flag on `key`; raises ValueError for an undeclared key."""
    if key not in document.graph["knowledge"]:
        raise ValueError(f"knowledge key '{key}' is not declared")

    def updated(flagged: frozenset, wanted: bool | None) -> frozenset:
        """`flagged` with `key` added, removed, or untouched."""
        if wanted is None:
            return flagged
        return flagged | {key} if wanted else flagged - {key}

    return replace(document, unset_keys=updated(document.unset_keys, unset),
                   following_keys=updated(document.following_keys, follows_target))


def retarget(document: EditorDocument, old_namespace: str, new_namespace: str) -> tuple[EditorDocument, list[str]]:
    """Renames every following key in `old_namespace` into `new_namespace` (cascading to its
    bindings and conditions). Returns the new document and the keys skipped because their new
    name already exists."""
    skipped = []
    for key in sorted(document.following_keys):
        namespace, name = split_key(key)
        new_key = join_key(new_namespace, name)
        if namespace == old_namespace and new_key != key:
            if new_key in document.graph["knowledge"]:
                skipped.append(key)
            else:
                document = with_graph(document, graph_draft.rename_knowledge_key(document.graph, key, new_key),
                                      RENAME_KEY_TOOL, {"old_key": key, "new_key": new_key})
    return document, skipped







#========================================#
# JSON (a saved file's "editor" section)
#========================================#

def sidecar_to_json(document: EditorDocument) -> dict:
    """The editor-only data as a JSON-native dict (the graph itself is saved separately)."""
    return {
        "layout": {node_id: list(position) for node_id, position in document.layout.items()},
        "unset_keys": sorted(document.unset_keys),
        "following_keys": sorted(document.following_keys),
    }


def document_from_json(graph: dict, sidecar: dict | None) -> EditorDocument:
    """An EditorDocument for `graph` with a saved sidecar's data (None or {} for none), keeping
    only entries for nodes and keys the graph actually has."""
    sidecar = sidecar or {}
    node_ids = set(graph["nodes"])
    keys = set(graph["knowledge"])
    return EditorDocument(
        graph=graph,
        layout={node_id: (float(x), float(y)) for node_id, (x, y) in sidecar.get("layout", {}).items() if node_id in node_ids},
        unset_keys=frozenset(key for key in sidecar.get("unset_keys", []) if key in keys),
        following_keys=frozenset(key for key in sidecar.get("following_keys", []) if key in keys),
    )
