"""Save/load a mission-graph dict to/from JSON (a file, or a JSON-native dict for the web
interface), plus the shared knowledge-type introspection this and the mission editors
use. A graph's "knowledge"
section stores real `type` objects, which JSON can't hold directly --
KNOWLEDGE_TYPES_BY_NAME (and its reverse, KNOWLEDGE_TYPE_NAMES) is the name<->type
registry used to round-trip them, re-exported here from mtofr.database, where every
KnowledgeEntry subclass registers itself. A compound type (e.g. Location) is
encoded/decoded generically via constructor_fields()'s introspection of its __init__
signature rather than a hardcoded per-type case, so defining the subclass is the only
step needed for it to be declarable, edited, and saved/loaded by the editor."""
import inspect
import json

from mtofr.database import KNOWLEDGE_TYPE_NAMES, KNOWLEDGE_TYPES_BY_NAME, KnowledgeEntry


#========================================#
# Config
#========================================#

TRUE_TEXTS = ("true", "1", "yes")   # lowercase text a bool field reads as True
JSON_INDENT = 2

# Casts a field's raw text to its annotated type -- shared by the editor's generic
# per-field form and this module's decode path. bool is handled specially since
# bool("False") is truthy for any non-empty string.
SCALAR_CASTERS = {
    bool: lambda text: text.strip().lower() in TRUE_TEXTS,
    float: float,
    int: int,
    str: str,
}
SCALAR_DEFAULTS = {bool: False, float: 0.0, int: 0, str: ""}   # see default_knowledge_value()







#========================================#
# Type Introspection
#========================================#

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
    return [
        (name, parameter.annotation if parameter.annotation is not inspect.Parameter.empty else str)
        for name, parameter in parameters.items() if name != "self"
    ]


def default_knowledge_value(entry_type: type):
    """A neutral value of `entry_type` (0, 0.0, False, "", or a KnowledgeEntry built from those per
    field), for a declaration that needs *some* value before the operator sets a real one. Never
    a meaningful value: a web-editor placeholder key holding it is flagged unset until edited."""
    if is_compound_knowledge_type(entry_type):
        return entry_type(**{field_name: SCALAR_DEFAULTS.get(annotation, "") for field_name, annotation in constructor_fields(entry_type)})
    return SCALAR_DEFAULTS[entry_type]


def encode_value(value):
    """A KnowledgeEntry as a {field_name: value} dict; any other value unchanged."""
    if isinstance(value, KnowledgeEntry):
        return {field_name: getattr(value, field_name) for field_name, _ in constructor_fields(type(value))}
    return value


def decode_value(entry_type: type, encoded):
    """Reverses encode_value() for a value declared as `entry_type`."""
    if is_compound_knowledge_type(entry_type):
        return entry_type(**encoded)
    return encoded







#========================================#
# Save/Load
#========================================#

def encode_mission_graph(mission_graph: dict) -> dict:
    """`mission_graph` as a JSON-native dict: knowledge types by name, KnowledgeEntry values as field
    dicts, and the optional name."""
    encoded_knowledge = {
        key: {"type": KNOWLEDGE_TYPE_NAMES[declaration["type"]], "value": encode_value(declaration["value"])}
        for key, declaration in mission_graph.get("knowledge", {}).items()
    }
    encoded = {
        "knowledge": encoded_knowledge,
        "nodes": mission_graph.get("nodes", {}),
        "edges": mission_graph.get("edges", {}),
        "start": mission_graph.get("start"),
    }
    if "name" in mission_graph:
        encoded["name"] = mission_graph["name"]
    return encoded


def decode_mission_graph(encoded: dict) -> dict:
    """Reverses encode_mission_graph(); raises ValueError on an unknown knowledge type name. Other
    top-level sections (e.g. a web-editor file's "editor" section) are ignored."""
    decoded_knowledge = {}
    for key, declaration in encoded.get("knowledge", {}).items():
        entry_type = KNOWLEDGE_TYPES_BY_NAME.get(declaration["type"])
        if entry_type is None:
            raise ValueError(f"knowledge key '{key}' has unknown type '{declaration['type']}'. "
                             f"Known types: {list(KNOWLEDGE_TYPES_BY_NAME)}")
        decoded_knowledge[key] = {"type": entry_type, "value": decode_value(entry_type, declaration["value"])}
    decoded = {
        "knowledge": decoded_knowledge,
        "nodes": encoded.get("nodes", {}),
        "edges": encoded.get("edges", {}),
        "start": encoded.get("start"),
    }
    if "name" in encoded:
        decoded["name"] = str(encoded["name"])
    return decoded


def save_mission_graph(mission_graph: dict, file_path) -> None:
    """Serializes `mission_graph` to `file_path` as JSON."""
    with open(file_path, "w") as file:
        json.dump(encode_mission_graph(mission_graph), file, indent=JSON_INDENT)


def load_mission_graph(file_path) -> dict:
    """Deserializes a mission graph previously written by save_mission_graph()."""
    with open(file_path) as file:
        return decode_mission_graph(json.load(file))
