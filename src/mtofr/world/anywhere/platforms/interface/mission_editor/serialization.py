"""Save/load a mission-graph dict to/from JSON, plus the shared knowledge-type
introspection this and mission_editor.window both use. A graph's "knowledge"
section stores real `type` objects, which JSON can't hold directly --
KNOWLEDGE_TYPES_BY_NAME (and its reverse, KNOWLEDGE_TYPE_NAMES) is the name<->type
registry used to round-trip them. A compound type (any KnowledgeEntry subclass,
e.g. Location) is encoded/decoded generically via constructor_fields()'s
introspection of its __init__ signature rather than a hardcoded per-type case --
adding a new KnowledgeEntry subclass to KNOWLEDGE_TYPES_BY_NAME is the only step
needed for it to be declarable, edited, and saved/loaded by the editor."""
import inspect
import json

from mtofr.database import KnowledgeEntry, Location

KNOWLEDGE_TYPES_BY_NAME = {"bool": bool, "float": float, "int": int, "str": str, "Location": Location}
KNOWLEDGE_TYPE_NAMES = {value: name for name, value in KNOWLEDGE_TYPES_BY_NAME.items()}

# Casts a field's raw text to its annotated type -- shared by the editor's generic
# per-field form and this module's decode path. bool is handled specially since
# bool("False") is truthy for any non-empty string.
SCALAR_CASTERS = {
    bool: lambda text: text.strip().lower() in ("true", "1", "yes"),
    float: float,
    int: int,
    str: str,
}


def is_compound_knowledge_type(entry_type: type) -> bool:
    """True for any KnowledgeEntry subclass (has multiple named fields, needs a
    generic per-field form/encoding) as opposed to a plain scalar type (bool/
    float/int/str, a single value)."""
    return isinstance(entry_type, type) and issubclass(entry_type, KnowledgeEntry)


def constructor_fields(entry_type: type) -> list:
    """Introspects entry_type's __init__ signature (skipping self) into a list of
    (field_name, annotation) pairs -- annotation defaults to str when unannotated.
    Lets the editor build an add/edit form, and this module encode/decode a saved
    file, for any KnowledgeEntry subclass without hardcoding its fields."""
    parameters = inspect.signature(entry_type.__init__).parameters
    fields = []
    for name, parameter in parameters.items():
        if name == "self":
            continue
        annotation = parameter.annotation if parameter.annotation is not inspect.Parameter.empty else str
        fields.append((name, annotation))
    return fields


def _encode_value(value):
    if isinstance(value, KnowledgeEntry):
        return {field_name: getattr(value, field_name) for field_name, _ in constructor_fields(type(value))}
    return value


def _decode_value(entry_type: type, encoded):
    if is_compound_knowledge_type(entry_type):
        return entry_type(**encoded)
    return encoded


def save_mission_graph(mission_graph: dict, file_path) -> None:
    """Serializes `mission_graph` to `file_path` as JSON."""
    encoded_knowledge = {
        key: {"type": KNOWLEDGE_TYPE_NAMES[declaration["type"]], "value": _encode_value(declaration["value"])}
        for key, declaration in mission_graph.get("knowledge", {}).items()
    }
    encoded = {
        "knowledge": encoded_knowledge,
        "nodes": mission_graph.get("nodes", {}),
        "edges": mission_graph.get("edges", {}),
        "start": mission_graph.get("start"),
    }
    with open(file_path, "w") as file:
        json.dump(encoded, file, indent=2)


def load_mission_graph(file_path) -> dict:
    """Deserializes a mission graph previously written by save_mission_graph()."""
    with open(file_path) as file:
        encoded = json.load(file)

    decoded_knowledge = {}
    for key, declaration in encoded.get("knowledge", {}).items():
        entry_type = KNOWLEDGE_TYPES_BY_NAME[declaration["type"]]
        decoded_knowledge[key] = {"type": entry_type, "value": _decode_value(entry_type, declaration["value"])}

    return {
        "knowledge": decoded_knowledge,
        "nodes": encoded.get("nodes", {}),
        "edges": encoded.get("edges", {}),
        "start": encoded.get("start"),
    }