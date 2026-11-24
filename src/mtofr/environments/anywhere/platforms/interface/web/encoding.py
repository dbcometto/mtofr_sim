"""JSON-native forms of the things panels send to the browser: knowledge types (with the
fields a value form needs), capability registries, and edge conditions as builder rows."""
from mtofr.mission.condition import And, Comparison, IsNone, Not, Or, parse_condition
from mtofr.mission.serialization import KNOWLEDGE_TYPE_NAMES, KNOWLEDGE_TYPES_BY_NAME, constructor_fields, is_compound_knowledge_type

SCALAR_FIELD_NAME = "value"   # the one form field a scalar (non-KnowledgeEntry) type gets
IS_NONE_OPERATOR = "is None"           # the condition builder's operator names for an IsNone check
IS_NOT_NONE_OPERATOR = "is not None"
MATCH_ALL = "all"   # rows joined by "and"
MATCH_ANY = "any"   # rows joined by "or"


def type_name(entry_type) -> str:
    """The registry name for `entry_type` (e.g. "Location"), falling back to its own name."""
    return KNOWLEDGE_TYPE_NAMES.get(entry_type, getattr(entry_type, "__name__", str(entry_type)))


def knowledge_type_fields() -> dict:
    """Every registered knowledge type name -> {"compound": bool, "fields": [[field_name, field_type_name], ...]}
    (one "value" field for a scalar type), so the browser can build a value form for any type and
    send back what as_knowledge_value() accepts: a field-text dict, or a scalar's text."""
    return {
        name: {
            "compound": is_compound_knowledge_type(entry_type),
            "fields": ([[field_name, type_name(annotation)] for field_name, annotation in constructor_fields(entry_type)]
                       if is_compound_knowledge_type(entry_type) else [[SCALAR_FIELD_NAME, name]]),
        }
        for name, entry_type in KNOWLEDGE_TYPES_BY_NAME.items()
    }


def _condition_row(node) -> dict | None:
    """One builder row ({key, operator, value, negated}) for a leaf check, optionally under one
    "not"; None for anything else."""
    negated = isinstance(node, Not)
    leaf = node.operand if negated else node
    if isinstance(leaf, Comparison):
        return {"key": leaf.key, "operator": leaf.operator, "value": leaf.value, "negated": negated}
    if isinstance(leaf, IsNone):
        return {"key": leaf.key, "operator": IS_NOT_NONE_OPERATOR if leaf.negated else IS_NONE_OPERATOR,
                "value": None, "negated": negated}
    return None


def condition_rows(condition: list) -> dict | None:
    """An edge condition as the graph editor's builder shows it: {"match": "all"|"any", "rows":
    [{key, operator, value, negated}, ...]}, for a single check or one and/or of checks (each
    optionally negated). None when the condition doesn't parse or nests deeper, so the editor
    falls back to raw tokens."""
    try:
        tree = parse_condition(condition)
    except ValueError:
        return None
    operands = tree.operands if isinstance(tree, (And, Or)) else (tree,)
    rows = [_condition_row(operand) for operand in operands]
    if any(row is None for row in rows):
        return None
    return {"match": MATCH_ANY if isinstance(tree, Or) else MATCH_ALL, "rows": rows}


def encode_capabilities(capability_registry) -> list | None:
    """A CapabilityRegistry as [{"ipl_type", "description", "inputs", "outputs"}, ...], each field
    as {"name", "type", "description"}; None when the registry is unknown."""
    if capability_registry is None:
        return None

    def encode_fields(param_specs) -> list:
        """ParamSpecs as JSON-native dicts."""
        return [{"name": spec.name, "type": type_name(spec.type), "description": spec.description}
                for spec in param_specs]

    return [
        {"ipl_type": capability.ipl_type, "description": capability.description,
         "inputs": encode_fields(capability.inputs), "outputs": encode_fields(capability.outputs)}
        for capability in capability_registry.all().values()
    ]
