"""Defines mutation helpers for a draft mission-graph dict, used by the mission
editor window. Each helper returns a new top-level dict object rather than
mutating in place, so MissionGraphViewer's identity-keyed layout cache
(mtofr.viz.mission_graph_view.compute_graph_layout) recomputes a fresh layout
after every edit instead of returning a stale one keyed off the old identity.
No Tk dependency -- independently testable from the GUI that calls it."""
import copy


#==========# Loading #==========#

def blank_graph(start_node_id: str = "start") -> dict:
    """A brand-new draft graph: one empty node, no edges."""
    return {"knowledge": {}, "nodes": {start_node_id: {"primitives": {}}}, "edges": {}, "start": start_node_id}


def load_draft(mission_graph: dict) -> dict:
    """Deep-copies a live/loaded mission graph into an independent draft, so
    editing it never mutates the platform (or file) it was loaded from."""
    return copy.deepcopy(mission_graph)


#==========# Nodes #==========#

def add_node(draft: dict, node_id: str) -> dict:
    if node_id in draft["nodes"]:
        raise ValueError(f"Node '{node_id}' already exists")
    new_draft = dict(draft)
    new_draft["nodes"] = {**draft["nodes"], node_id: {"primitives": {}}}
    return new_draft


def remove_node(draft: dict, node_id: str) -> dict:
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


def set_start_node(draft: dict, node_id: str) -> dict:
    if node_id not in draft["nodes"]:
        raise ValueError(f"Node '{node_id}' does not exist")
    return {**draft, "start": node_id}


#==========# Primitives #==========#

def add_primitive(draft: dict, node_id: str, primitive_name: str, capability: str,
                   inputs: dict, outputs: dict) -> dict:
    node = draft["nodes"][node_id]
    if primitive_name in node["primitives"]:
        raise ValueError(f"Primitive '{primitive_name}' already exists on node '{node_id}'")

    new_draft = dict(draft)
    new_nodes = dict(draft["nodes"])
    new_primitives = {
        **node["primitives"],
        primitive_name: {"capability": capability, "inputs": dict(inputs), "outputs": dict(outputs)},
    }
    new_nodes[node_id] = {"primitives": new_primitives}
    new_draft["nodes"] = new_nodes
    return new_draft


def edit_primitive(draft: dict, node_id: str, old_name: str, new_name: str, capability: str,
                    inputs: dict, outputs: dict) -> dict:
    """Replaces an existing primitive in place -- same as add_primitive, but
    overwrites rather than rejecting an existing name, and additionally supports
    renaming (old_name -> new_name) in one step."""
    node = draft["nodes"][node_id]
    if new_name != old_name and new_name in node["primitives"]:
        raise ValueError(f"Primitive '{new_name}' already exists on node '{node_id}'")

    new_draft = dict(draft)
    new_nodes = dict(draft["nodes"])
    new_primitives = dict(node["primitives"])
    new_primitives.pop(old_name, None)
    new_primitives[new_name] = {"capability": capability, "inputs": dict(inputs), "outputs": dict(outputs)}
    new_nodes[node_id] = {"primitives": new_primitives}
    new_draft["nodes"] = new_nodes
    return new_draft


def remove_primitive(draft: dict, node_id: str, primitive_name: str) -> dict:
    new_draft = dict(draft)
    new_nodes = dict(draft["nodes"])
    new_primitives = dict(new_nodes[node_id]["primitives"])
    new_primitives.pop(primitive_name, None)
    new_nodes[node_id] = {"primitives": new_primitives}
    new_draft["nodes"] = new_nodes
    return new_draft


#==========# Edges #==========#

def add_edge(draft: dict, source_id: str, target_id: str, condition: list) -> dict:
    new_draft = dict(draft)
    new_edges = dict(draft["edges"])
    new_edges[source_id] = [*new_edges.get(source_id, []), {"condition": condition, "to": target_id}]
    new_draft["edges"] = new_edges
    return new_draft


def edit_edge(draft: dict, source_id: str, index: int, new_source_id: str, new_target_id: str,
              condition: list) -> dict:
    """Replaces an existing edge in place -- removes the edge at `index` in
    `source_id`'s list, then adds the edited version (possibly under a different
    source/target) back, same as remove_edge followed by add_edge in one step."""
    new_draft = dict(draft)
    new_edges = dict(draft["edges"])
    edge_list = [dict(edge) for edge in new_edges.get(source_id, [])]
    del edge_list[index]
    if edge_list:
        new_edges[source_id] = edge_list
    else:
        new_edges.pop(source_id, None)

    new_edges[new_source_id] = [*new_edges.get(new_source_id, []), {"condition": condition, "to": new_target_id}]
    new_draft["edges"] = new_edges
    return new_draft


def remove_edge(draft: dict, source_id: str, index: int) -> dict:
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


#==========# Knowledge #==========#

def add_knowledge_key(draft: dict, key: str, entry_type: type, value) -> dict:
    if key in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{key}' already declared")
    new_draft = dict(draft)
    new_draft["knowledge"] = {**draft["knowledge"], key: {"type": entry_type, "value": value}}
    return new_draft


def edit_knowledge_key(draft: dict, key: str, entry_type: type, value) -> dict:
    """Replaces an existing knowledge key's declared type/value in place, without
    renaming it -- use rename_knowledge_key() first if the key itself is
    changing, since a plain rename here would silently break every primitive
    binding/edge condition that already references the old key string."""
    if key not in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{key}' is not declared")
    new_draft = dict(draft)
    new_draft["knowledge"] = {**draft["knowledge"], key: {"type": entry_type, "value": value}}
    return new_draft


# A key token in a pre-tokenized condition (see mtofr.condition.condition) is
# always immediately followed by a comparison operator or "is" -- the grammar
# never places a literal value there (after key+operator+value, the next token
# must be "and"/"or"/")"/end) -- so this positional check identifies exactly the
# key-reference tokens, with no risk of renaming a same-valued string literal.
_CONDITION_OPERATOR_TOKENS = {"==", "!=", "<", "<=", ">", ">=", "is"}


def _rename_key_in_condition(condition: list, old_key: str, new_key: str) -> list:
    renamed = list(condition)
    for index, token in enumerate(renamed[:-1]):
        if token == old_key and renamed[index + 1] in _CONDITION_OPERATOR_TOKENS:
            renamed[index] = new_key
    return renamed


def rename_knowledge_key(draft: dict, old_key: str, new_key: str) -> dict:
    """Renames a Knowledge key everywhere it's referenced: its own declaration,
    every primitive input/output binding across every node, and every edge
    condition -- unlike edit_knowledge_key() (type/value only), this is the
    rename path, updating every reference so it doesn't silently break them."""
    if old_key not in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{old_key}' is not declared")
    if new_key != old_key and new_key in draft["knowledge"]:
        raise ValueError(f"Knowledge key '{new_key}' already declared")

    new_draft = dict(draft)

    knowledge = dict(draft["knowledge"])
    knowledge[new_key] = knowledge.pop(old_key)
    new_draft["knowledge"] = knowledge

    new_nodes = {}
    for node_id, node in draft["nodes"].items():
        new_primitives = {}
        for name, primitive in node["primitives"].items():
            new_primitives[name] = {
                "capability": primitive["capability"],
                "inputs": {field: (new_key if key == old_key else key)
                           for field, key in primitive.get("inputs", {}).items()},
                "outputs": {field: (new_key if key == old_key else key)
                            for field, key in primitive.get("outputs", {}).items()},
            }
        new_nodes[node_id] = {"primitives": new_primitives}
    new_draft["nodes"] = new_nodes

    new_edges = {}
    for source_id, edge_list in draft["edges"].items():
        new_edges[source_id] = [
            {"condition": _rename_key_in_condition(edge["condition"], old_key, new_key), "to": edge["to"]}
            for edge in edge_list
        ]
    new_draft["edges"] = new_edges

    return new_draft


def remove_knowledge_key(draft: dict, key: str) -> dict:
    new_draft = dict(draft)
    knowledge = dict(draft["knowledge"])
    knowledge.pop(key, None)
    new_draft["knowledge"] = knowledge
    return new_draft