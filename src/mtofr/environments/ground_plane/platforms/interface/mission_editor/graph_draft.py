"""Defines mutation helpers for a draft mission-graph dict, used by the mission
editors (Tk and web) and the assistant's tools. They touch mission semantics only;
editor-only data (node layout, key flags) lives in the web editor's EditorDocument
(editor_document.py). Each helper returns a new top-level dict object rather than
mutating in place, so MissionGraphViewer's identity-keyed layout cache
(mtofr.viz.mission_graph_view.compute_graph_layout) recomputes a fresh layout
after every edit instead of returning a stale one keyed off the old identity.
No Tk dependency -- independently testable from the GUI that calls it."""
import copy

from mtofr.mission.condition import KEY_FOLLOWER_TOKENS


#========================================#
# Config
#========================================#

DEFAULT_START_NODE_ID = "start"







#========================================#
# Loading
#========================================#

def blank_graph(start_node_id: str = DEFAULT_START_NODE_ID) -> dict:
    """A brand-new draft graph: one empty node, no edges."""
    return {"knowledge": {}, "nodes": {start_node_id: {"capabilities": {}}}, "edges": {}, "start": start_node_id}


def load_draft(mission_graph: dict) -> dict:
    """Deep-copies a live/loaded mission graph into an independent draft, so
    editing it never mutates the platform (or file) it was loaded from."""
    return copy.deepcopy(mission_graph)







#========================================#
# Nodes
#========================================#

def add_node(draft: dict, node_id: str) -> dict:
    """Adds an empty node; raises ValueError if `node_id` already exists."""
    if node_id in draft["nodes"]:
        raise ValueError(f"Node '{node_id}' already exists")
    new_draft = dict(draft)
    new_draft["nodes"] = {**draft["nodes"], node_id: {"capabilities": {}}}
    return new_draft


def remove_node(draft: dict, node_id: str) -> dict:
    """Removes a node plus every edge into or out of it, moving the start to the first remaining node if needed."""
    new_draft = dict(draft)
    nodes = dict(draft["nodes"])
    nodes.pop(node_id, None)
    new_draft["nodes"] = nodes

    edges = {
        source: [dict(edge) for edge in edge_list if edge["to"] != node_id]
        for source, edge_list in draft["edges"].items() if source != node_id
    }
    new_draft["edges"] = {source: edge_list for source, edge_list in edges.items() if edge_list}

    if draft["start"] == node_id:
        new_draft["start"] = next(iter(nodes), None)
    return new_draft


def rename_node(draft: dict, old_id: str, new_id: str) -> dict:
    """Renames a node, along with every edge source/target and the start that reference it."""
    if old_id not in draft["nodes"]:
        raise ValueError(f"Node '{old_id}' does not exist")
    if new_id in draft["nodes"]:
        raise ValueError(f"Node '{new_id}' already exists")

    new_draft = dict(draft)
    nodes = dict(draft["nodes"])
    nodes[new_id] = nodes.pop(old_id)
    new_draft["nodes"] = nodes

    edges = {}
    for source, edge_list in draft["edges"].items():
        new_source = new_id if source == old_id else source
        edges[new_source] = [
            dict(edge, to=(new_id if edge["to"] == old_id else edge["to"])) for edge in edge_list
        ]
    new_draft["edges"] = edges

    if draft["start"] == old_id:
        new_draft["start"] = new_id
    return new_draft


def set_mission_name(draft: dict, name: str) -> dict:
    """Sets the mission's optional human-readable name; an empty (or all-whitespace) name removes it."""
    new_draft = dict(draft)
    if name.strip():
        new_draft["name"] = name.strip()
    else:
        new_draft.pop("name", None)
    return new_draft


def set_start_node(draft: dict, node_id: str) -> dict:
    """Makes `node_id` the start node; raises ValueError if it doesn't exist."""
    if node_id not in draft["nodes"]:
        raise ValueError(f"Node '{node_id}' does not exist")
    return {**draft, "start": node_id}







#========================================#
# Capability Requests
#========================================#

def add_capability(draft: dict, node_id: str, request_name: str, capability: str,
                   inputs: dict, outputs: dict) -> dict:
    """Adds a capability request to a node; raises ValueError if the name is already taken there."""
    node = draft["nodes"][node_id]
    if request_name in node["capabilities"]:
        raise ValueError(f"Capability request '{request_name}' already exists on node '{node_id}'")

    new_draft = dict(draft)
    new_nodes = dict(draft["nodes"])
    new_capability_requests = {
        **node["capabilities"],
        request_name: {"capability": capability, "inputs": dict(inputs), "outputs": dict(outputs)},
    }
    new_nodes[node_id] = {"capabilities": new_capability_requests}
    new_draft["nodes"] = new_nodes
    return new_draft


def edit_capability(draft: dict, node_id: str, old_name: str, new_name: str, capability: str,
                    inputs: dict, outputs: dict) -> dict:
    """Replaces an existing capability request in place -- same as add_capability, but
    overwrites rather than rejecting an existing name, and additionally supports
    renaming (old_name -> new_name) in one step."""
    node = draft["nodes"][node_id]
    if new_name != old_name and new_name in node["capabilities"]:
        raise ValueError(f"Capability request '{new_name}' already exists on node '{node_id}'")

    new_draft = dict(draft)
    new_nodes = dict(draft["nodes"])
    new_capability_requests = dict(node["capabilities"])
    new_capability_requests.pop(old_name, None)
    new_capability_requests[new_name] = {"capability": capability, "inputs": dict(inputs), "outputs": dict(outputs)}
    new_nodes[node_id] = {"capabilities": new_capability_requests}
    new_draft["nodes"] = new_nodes
    return new_draft


def remove_capability(draft: dict, node_id: str, request_name: str) -> dict:
    """Removes a capability request from a node (a missing name is a no-op)."""
    new_draft = dict(draft)
    new_nodes = dict(draft["nodes"])
    new_capability_requests = dict(new_nodes[node_id]["capabilities"])
    new_capability_requests.pop(request_name, None)
    new_nodes[node_id] = {"capabilities": new_capability_requests}
    new_draft["nodes"] = new_nodes
    return new_draft







#========================================#
# Edges
#========================================#

def add_edge(draft: dict, source_id: str, target_id: str, condition: list) -> dict:
    """Appends an edge to the end of `source_id`'s edge list (checked last)."""
    new_draft = dict(draft)
    new_edges = dict(draft["edges"])
    new_edges[source_id] = [*new_edges.get(source_id, []), {"condition": condition, "to": target_id}]
    new_draft["edges"] = new_edges
    return new_draft


def edit_edge(draft: dict, source_id: str, index: int, new_source_id: str, new_target_id: str,
              condition: list) -> dict:
    """Replaces the edge at `index` in `source_id`'s list. With the same source it stays at
    its index (keeping its priority); moved to a different source, it is appended there
    (checked last), the same as remove_edge followed by add_edge."""
    if new_source_id != source_id:
        return add_edge(remove_edge(draft, source_id, index), new_source_id, new_target_id, condition)
    new_draft = dict(draft)
    new_edges = dict(draft["edges"])
    edge_list = [dict(edge) for edge in new_edges[source_id]]
    edge_list[index] = {"condition": condition, "to": new_target_id}
    new_edges[source_id] = edge_list
    new_draft["edges"] = new_edges
    return new_draft


def move_edge(draft: dict, source_id: str, index: int, new_index: int) -> dict:
    """Moves the edge at `index` in `source_id`'s list to `new_index`, changing its priority
    (edges are checked in order, first match wins); raises IndexError if either is out of range."""
    edge_list = [dict(edge) for edge in draft["edges"].get(source_id, [])]
    if not (0 <= index < len(edge_list) and 0 <= new_index < len(edge_list)):
        raise IndexError(f"node '{source_id}' has {len(edge_list)} edge(s); can't move edge {index} to {new_index}")
    edge_list.insert(new_index, edge_list.pop(index))
    new_draft = dict(draft)
    new_draft["edges"] = {**draft["edges"], source_id: edge_list}
    return new_draft


def remove_edge(draft: dict, source_id: str, index: int) -> dict:
    """Removes the edge at `index` in `source_id`'s list, dropping the list once empty."""
    new_draft = dict(draft)
    new_edges = dict(draft["edges"])
    edge_list = [dict(edge) for edge in new_edges.get(source_id, [])]
    del edge_list[index]
    if edge_list:
        new_edges[source_id] = edge_list
    else:
        new_edges.pop(source_id, None)
    new_draft["edges"] = new_edges
    return new_draft







#========================================#
# Knowledge
#========================================#

def add_knowledge_key(draft: dict, key: str, entry_type: type, value) -> dict:
    """Declares a new knowledge key; raises ValueError if it's already declared."""
    if key in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{key}' already declared")
    new_draft = dict(draft)
    new_draft["knowledge"] = {**draft["knowledge"], key: {"type": entry_type, "value": value}}
    return new_draft


def edit_knowledge_key(draft: dict, key: str, entry_type: type, value) -> dict:
    """Replaces an existing knowledge key's declared type/value in place, without
    renaming it -- use rename_knowledge_key() first if the key itself is
    changing, since a plain rename here would silently break every capability
    request binding/edge condition that already references the old key string."""
    if key not in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{key}' is not declared")
    new_draft = dict(draft)
    new_draft["knowledge"] = {**draft["knowledge"], key: {"type": entry_type, "value": value}}
    return new_draft


def _rename_key_in_condition(condition: list, old_key: str, new_key: str) -> list:
    """Renames every key-reference token equal to `old_key` in a pre-tokenized condition."""
    # NOTE: a key token is always immediately followed by a comparison operator or
    # "is" (see KEY_FOLLOWER_TOKENS); the grammar never places a literal value there,
    # so this positional check identifies exactly the key-reference tokens, with no
    # risk of renaming a same-valued string literal.
    renamed = list(condition)
    for index, token in enumerate(renamed[:-1]):
        if token == old_key and renamed[index + 1] in KEY_FOLLOWER_TOKENS:
            renamed[index] = new_key
    return renamed


def rename_knowledge_key(draft: dict, old_key: str, new_key: str) -> dict:
    """Renames a Knowledge key everywhere it's referenced: its own declaration,
    every capability request input/output binding across every node, and every edge
    condition -- unlike edit_knowledge_key() (type/value only), this is the
    rename path, updating every reference so it doesn't silently break them."""
    if old_key not in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{old_key}' is not declared")
    if new_key != old_key and new_key in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{new_key}' already declared")

    new_draft = dict(draft)


    # Declaration
    knowledge = dict(draft["knowledge"])
    knowledge[new_key] = knowledge.pop(old_key)
    new_draft["knowledge"] = knowledge


    # Capability request bindings
    new_nodes = {}
    for node_id, node in draft["nodes"].items():
        new_capability_requests = {}
        for name, capability_request in node["capabilities"].items():
            new_capability_requests[name] = {
                "capability": capability_request["capability"],
                "inputs": {field: (new_key if key == old_key else key)
                           for field, key in capability_request.get("inputs", {}).items()},
                "outputs": {field: (new_key if key == old_key else key)
                            for field, key in capability_request.get("outputs", {}).items()},
            }
        new_nodes[node_id] = {"capabilities": new_capability_requests}
    new_draft["nodes"] = new_nodes


    # Edge conditions
    new_edges = {}
    for source_id, edge_list in draft["edges"].items():
        new_edges[source_id] = [
            {"condition": _rename_key_in_condition(edge["condition"], old_key, new_key), "to": edge["to"]}
            for edge in edge_list
        ]
    new_draft["edges"] = new_edges


    return new_draft


def remove_knowledge_key(draft: dict, key: str) -> dict:
    """Removes a knowledge key's declaration (references to it are left for validation to flag)."""
    new_draft = dict(draft)
    knowledge = dict(draft["knowledge"])
    knowledge.pop(key, None)
    new_draft["knowledge"] = knowledge
    return new_draft
