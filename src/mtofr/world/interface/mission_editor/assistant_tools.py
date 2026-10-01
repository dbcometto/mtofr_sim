"""Defines the LLM assistant's tools: one thin wrapper per graph_draft.py mutator, applied through a caller-supplied draft accessor."""
import json

from mtofr.capability.capability import find_binding_problems, find_primitive_problems
from mtofr.condition.condition import parse_condition
from mtofr.world.interface.mission_editor import graph_draft
from mtofr.world.interface.mission_editor.serialization import (
    KNOWLEDGE_TYPES_BY_NAME, SCALAR_CASTERS, constructor_fields, is_compound_knowledge_type,
)


#==========# Argument coercion #==========#

def _as_json(value, expected_type: type, description: str):
    """Small models often send a nested argument as a JSON string; accept either form."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError(f"{description} must be valid JSON, got: {value!r}")
    if not isinstance(value, expected_type):
        raise ValueError(f"{description} must be a {expected_type.__name__}, got: {value!r}")
    return value


def _as_bindings(value, description: str) -> dict:
    """A primitive's inputs/outputs: {capability field name: knowledge key}."""
    bindings = _as_json(value if value is not None else {}, dict, description)
    for field, key in bindings.items():
        if not isinstance(key, str):
            raise ValueError(f"{description}['{field}'] must be a knowledge key name (string), got: {key!r}")
    return bindings


def _as_condition(value) -> list:
    """An edge condition token list, validated with the same parser the manual editor uses."""
    condition = _as_json(value, list, "condition")
    parse_condition(condition)   # raises ConditionSyntaxError, a ValueError subclass
    return condition


def _as_knowledge_value(entry_type: type, value):
    """Builds a knowledge value of `entry_type` from what the model sent (a scalar, or a field dict/list for compound types)."""
    if is_compound_knowledge_type(entry_type):
        field_names = [name for name, _ in constructor_fields(entry_type)]
        if isinstance(value, str):
            value = _as_json(value, (dict, list), "value")
        if isinstance(value, list):
            value = dict(zip(field_names, value))
        if not isinstance(value, dict) or set(value) != set(field_names):
            raise ValueError(f"value for {entry_type.__name__} must provide exactly these fields: {field_names}")
        converted = {name: SCALAR_CASTERS[annotation](str(value[name])) if annotation in SCALAR_CASTERS else value[name]
                     for name, annotation in constructor_fields(entry_type)}
        return entry_type(**converted)
    try:
        return SCALAR_CASTERS[entry_type](str(value))
    except ValueError:
        raise ValueError(f"value {value!r} is not a valid {entry_type.__name__}")


def _as_knowledge_type(type_name: str) -> type:
    """Resolves a type name (e.g. "float", "Location") through the editor's serialization registry."""
    if type_name not in KNOWLEDGE_TYPES_BY_NAME:
        raise ValueError(f"unknown type '{type_name}'. Available types: {', '.join(KNOWLEDGE_TYPES_BY_NAME)}")
    return KNOWLEDGE_TYPES_BY_NAME[type_name]


#==========# Toolbox #==========#

class DraftToolbox:
    """The assistant's tools, bound to one draft via `get_draft()`/`apply_draft(new_draft)`. Every tool is a
    1:1 wrapper of a graph_draft helper (deliberately no composite tools -- the granularity is the point);
    `run()` returns "ok: ..." or an "Error: ..." string, never raises, so the model can read it and retry."""

    def __init__(self, get_draft, apply_draft, get_capabilities=lambda: None):
        self.get_draft = get_draft
        self.apply_draft = apply_draft
        self.get_capabilities = get_capabilities   # the target platform's CapabilityRegistry, or None when unknown
        self._functions = {
            "add_node": self.add_node, "remove_node": self.remove_node, "rename_node": self.rename_node,
            "set_start_node": self.set_start_node,
            "add_primitive": self.add_primitive, "edit_primitive": self.edit_primitive,
            "remove_primitive": self.remove_primitive,
            "add_edge": self.add_edge, "edit_edge": self.edit_edge, "remove_edge": self.remove_edge,
            "add_knowledge_key": self.add_knowledge_key, "edit_knowledge_key": self.edit_knowledge_key,
            "rename_knowledge_key": self.rename_knowledge_key, "remove_knowledge_key": self.remove_knowledge_key,
        }
        self.names = list(self._functions)
        self.schemas = _build_schemas()

    def run(self, name: str, arguments: dict) -> str:
        """Runs the named tool; errors come back as text, not exceptions."""
        function = self._functions.get(name)
        if function is None:
            return f"Error: unknown tool '{name}'. Available tools: {', '.join(self._functions)}"
        try:
            return function(**arguments)
        except TypeError as error:   # wrong or missing arguments
            return f"Error: bad arguments for {name}: {error}"
        except (ValueError, KeyError, IndexError) as error:
            message = error.args[0] if isinstance(error, KeyError) and error.args else error
            return f"Error: {message}"

    #=====# Checks the helpers don't make themselves (they'd raise a bare KeyError/IndexError) #=====#

    def _require_node(self, node_id: str) -> None:
        if node_id not in self.get_draft()["nodes"]:
            raise ValueError(f"node '{node_id}' does not exist. Existing nodes: {list(self.get_draft()['nodes'])}")

    def _require_primitive(self, node_id: str, primitive_name: str) -> None:
        self._require_node(node_id)
        primitives = self.get_draft()["nodes"][node_id]["primitives"]
        if primitive_name not in primitives:
            raise ValueError(f"node '{node_id}' has no primitive '{primitive_name}'. Its primitives: {list(primitives)}")

    def _require_edge(self, source_id: str, index) -> int:
        edge_list = self.get_draft()["edges"].get(source_id, [])
        if isinstance(index, str):
            index = int(index) if index.strip().lstrip("-").isdigit() else index
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(edge_list):
            raise ValueError(f"node '{source_id}' has no edge with index {index!r}; it has {len(edge_list)} edge(s)")
        return index

    def _require_key(self, key: str) -> None:
        if key not in self.get_draft()["knowledge"]:
            raise ValueError(f"knowledge key '{key}' is not declared. Declared keys: {list(self.get_draft()['knowledge'])}")

    def _require_bindable(self, capability: str, inputs: dict, outputs: dict) -> None:
        """Rejects a primitive the target platform could not bind (unknown capability or field, undeclared key, wrong key type)."""
        registry = self.get_capabilities()
        if registry is None:
            return
        primitive = {"capability": capability, "inputs": inputs, "outputs": outputs}
        problems = find_primitive_problems(primitive, self.get_draft()["knowledge"], registry)
        if problems:
            raise ValueError("; ".join(problems))

    #=====# Nodes #=====#

    def add_node(self, node_id: str) -> str:
        self.apply_draft(graph_draft.add_node(self.get_draft(), node_id))
        return f"ok: added node '{node_id}'"

    def remove_node(self, node_id: str) -> str:
        self._require_node(node_id)
        self.apply_draft(graph_draft.remove_node(self.get_draft(), node_id))
        return f"ok: removed node '{node_id}' and every edge touching it"

    def rename_node(self, old_id: str, new_id: str) -> str:
        self.apply_draft(graph_draft.rename_node(self.get_draft(), old_id, new_id))
        return f"ok: renamed node '{old_id}' to '{new_id}'"

    def set_start_node(self, node_id: str) -> str:
        self.apply_draft(graph_draft.set_start_node(self.get_draft(), node_id))
        return f"ok: start node is now '{node_id}'"

    #=====# Primitives #=====#

    def add_primitive(self, node_id: str, primitive_name: str, capability: str, inputs=None, outputs=None) -> str:
        self._require_node(node_id)
        inputs, outputs = _as_bindings(inputs, "inputs"), _as_bindings(outputs, "outputs")
        self._require_bindable(capability, inputs, outputs)
        self.apply_draft(graph_draft.add_primitive(self.get_draft(), node_id, primitive_name, capability, inputs, outputs))
        return f"ok: added primitive '{primitive_name}' ({capability}) to node '{node_id}'"

    def edit_primitive(self, node_id: str, old_name: str, new_name: str, capability: str, inputs=None, outputs=None) -> str:
        self._require_primitive(node_id, old_name)
        inputs, outputs = _as_bindings(inputs, "inputs"), _as_bindings(outputs, "outputs")
        self._require_bindable(capability, inputs, outputs)
        self.apply_draft(graph_draft.edit_primitive(self.get_draft(), node_id, old_name, new_name, capability, inputs, outputs))
        return f"ok: node '{node_id}' primitive '{old_name}' is now '{new_name}' ({capability})"

    def remove_primitive(self, node_id: str, primitive_name: str) -> str:
        self._require_primitive(node_id, primitive_name)
        self.apply_draft(graph_draft.remove_primitive(self.get_draft(), node_id, primitive_name))
        return f"ok: removed primitive '{primitive_name}' from node '{node_id}'"

    #=====# Edges #=====#

    def add_edge(self, source_id: str, target_id: str, condition) -> str:
        self._require_node(source_id)
        self._require_node(target_id)
        self.apply_draft(graph_draft.add_edge(self.get_draft(), source_id, target_id, _as_condition(condition)))
        return f"ok: added edge '{source_id}' -> '{target_id}'"

    def edit_edge(self, source_id: str, index, new_source_id: str, new_target_id: str, condition) -> str:
        index = self._require_edge(source_id, index)
        self._require_node(new_source_id)
        self._require_node(new_target_id)
        self.apply_draft(graph_draft.edit_edge(
            self.get_draft(), source_id, index, new_source_id, new_target_id, _as_condition(condition)))
        return f"ok: edge {index} of '{source_id}' is now '{new_source_id}' -> '{new_target_id}'"

    def remove_edge(self, source_id: str, index) -> str:
        index = self._require_edge(source_id, index)
        self.apply_draft(graph_draft.remove_edge(self.get_draft(), source_id, index))
        return f"ok: removed edge {index} of '{source_id}'"

    #=====# Knowledge #=====#

    def add_knowledge_key(self, key: str, type: str, value) -> str:
        entry_type = _as_knowledge_type(type)
        self.apply_draft(graph_draft.add_knowledge_key(
            self.get_draft(), key, entry_type, _as_knowledge_value(entry_type, value)))
        return f"ok: declared knowledge key '{key}' ({type})"

    def edit_knowledge_key(self, key: str, type: str, value) -> str:
        self._require_key(key)
        entry_type = _as_knowledge_type(type)
        self.apply_draft(graph_draft.edit_knowledge_key(
            self.get_draft(), key, entry_type, _as_knowledge_value(entry_type, value)))
        broken = find_binding_problems(self.get_draft(), self.get_capabilities())   # a type change can invalidate existing bindings
        warning = f" WARNING, this broke existing bindings: {'; '.join(broken)}" if broken else ""
        return f"ok: knowledge key '{key}' is now a {type}.{warning}"

    def rename_knowledge_key(self, old_key: str, new_key: str) -> str:
        self.apply_draft(graph_draft.rename_knowledge_key(self.get_draft(), old_key, new_key))
        return f"ok: renamed knowledge key '{old_key}' to '{new_key}' everywhere it is used"

    def remove_knowledge_key(self, key: str) -> str:
        self._require_key(key)
        self.apply_draft(graph_draft.remove_knowledge_key(self.get_draft(), key))
        return f"ok: removed knowledge key '{key}' (bindings and conditions that use it are NOT updated)"


#==========# Schemas #==========#
# The model never sees the Python above, only this text.

def _string(description: str) -> dict:
    return {"type": "string", "description": description}


def _schema(name: str, description: str, properties: dict, required: list) -> dict:
    """Builds one tool's schema in Ollama's function-calling format."""
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }}


def _build_schemas() -> list:
    """The schema list handed to the model, one entry per tool."""
    node = _string("node id")
    primitive = _string("primitive name, unique within its node")
    capability = _string("capability name, exactly as listed under Capabilities")
    inputs = {"type": "object", "description": "maps each capability input field name to the NAME of a declared knowledge key, "
              'never a literal value, e.g. {"target": "goal", "tolerance": "tolerance"}'}
    outputs = {"type": "object", "description": "maps each capability output field name to the NAME of a declared knowledge key, "
               'e.g. {"arrived": "arrived"}'}
    condition = {"type": "array", "description": 'condition tokens, e.g. ["arrived", "==", true] or '
                 '["battery", ">", 0.5, "and", "found", "==", true]. Keys are strings; true/false/numbers are literals.'}
    index = {"type": "integer", "description": "the edge number shown in the draft (0-based, per source node)"}
    type_name = _string(f"one of: {', '.join(KNOWLEDGE_TYPES_BY_NAME)}")
    value = {"description": 'initial value: a number/boolean/string, or for Location an object like {"x": 1.0, "y": 2.0}'}
    return [
        _schema("add_node", "Add a new empty node to the mission graph.", {"node_id": node}, ["node_id"]),
        _schema("remove_node", "Remove a node and every edge touching it.", {"node_id": node}, ["node_id"]),
        _schema("rename_node", "Rename a node, updating edges and the start node.",
                {"old_id": node, "new_id": node}, ["old_id", "new_id"]),
        _schema("set_start_node", "Choose which node the mission starts in.", {"node_id": node}, ["node_id"]),
        _schema("add_primitive", "Add a capability to a node; it runs while that node is active.",
                {"node_id": node, "primitive_name": primitive, "capability": capability,
                 "inputs": inputs, "outputs": outputs},
                ["node_id", "primitive_name", "capability"]),
        _schema("edit_primitive", "Replace a primitive on a node (can rename it).",
                {"node_id": node, "old_name": primitive, "new_name": primitive, "capability": capability,
                 "inputs": inputs, "outputs": outputs},
                ["node_id", "old_name", "new_name", "capability"]),
        _schema("remove_primitive", "Remove a primitive from a node.",
                {"node_id": node, "primitive_name": primitive}, ["node_id", "primitive_name"]),
        _schema("add_edge", "Add a transition from one node to another, taken when the condition becomes true.",
                {"source_id": node, "target_id": node, "condition": condition},
                ["source_id", "target_id", "condition"]),
        _schema("edit_edge", "Replace an existing edge (identified by source node and edge number).",
                {"source_id": node, "index": index, "new_source_id": node, "new_target_id": node,
                 "condition": condition},
                ["source_id", "index", "new_source_id", "new_target_id", "condition"]),
        _schema("remove_edge", "Remove an edge, identified by its source node and edge number.",
                {"source_id": node, "index": index}, ["source_id", "index"]),
        _schema("add_knowledge_key", "Declare a new knowledge key with a type and initial value. Use type Location for any place.",
                {"key": _string("key name"), "type": type_name, "value": value}, ["key", "type", "value"]),
        _schema("edit_knowledge_key", "Change an existing knowledge key's type and value (not its name).",
                {"key": _string("key name"), "type": type_name, "value": value}, ["key", "type", "value"]),
        _schema("rename_knowledge_key", "Rename a knowledge key everywhere it is used.",
                {"old_key": _string("current key name"), "new_key": _string("new key name")}, ["old_key", "new_key"]),
        _schema("remove_knowledge_key", "Remove a knowledge key declaration.",
                {"key": _string("key name")}, ["key"]),
    ]
