"""Checks a mission graph: structurally on its own (verify_mission_structure), and
against one platform's capabilities (find_binding_problems).  The editor, the LLM
assistant, Backseater.write_mission(), and Backseater's bind-time check all share these,
so a graph is judged the same way everywhere."""
from mtofr.core.capability import CapabilityRegistry
from mtofr.mission.condition import parse_condition
from mtofr.mission.graph import MissionGraph, CapabilityRequest


#========================================#
# Structure
#========================================#

class MissionStructuralError(ValueError):
    """Raised when a mission graph references a Knowledge key, in an edge condition or a
    capability request's inputs/outputs, that isn't declared in that same graph's own "knowledge"
    section, or (from Backseater.write_mission()) when it can't be bound on its platform."""


def verify_mission_structure(mission_graph: MissionGraph) -> None:
    """Raises MissionStructuralError if any edge condition or capability request input/output binding
    in `mission_graph` references a Knowledge key not declared in the graph's own "knowledge" section.
    Capability request bindings are checked here (not only at Backseater's bind time) so a bad graph is
    rejected at push instead of being accepted and then halting the running mission."""
    declared_keys = set(mission_graph.get("knowledge", {}).keys())

    # Collect every key an edge condition or a capability request binding references
    referenced_keys = set()
    for edges in mission_graph.get("edges", {}).values():
        for edge in edges:
            referenced_keys |= parse_condition(edge["condition"]).keys()
    for node in mission_graph.get("nodes", {}).values():
        for capability_request in node.get("capabilities", {}).values():
            referenced_keys |= set(capability_request.get("inputs", {}).values())
            referenced_keys |= set(capability_request.get("outputs", {}).values())


    missing_keys = referenced_keys - declared_keys
    if missing_keys:
        raise MissionStructuralError(
            f"Mission graph references undeclared knowledge key(s): {sorted(missing_keys)}"
        )







#========================================#
# Binding
#========================================#

def declared_types(mission_graph: MissionGraph) -> dict[str, type]:
    """Knowledge key -> declared type, from `mission_graph`'s own "knowledge" section."""
    return {key: declaration["type"] for key, declaration in mission_graph.get("knowledge", {}).items()}


def find_capability_problems(capability_request: CapabilityRequest, known_types: dict[str, type],
                             capability_registry: CapabilityRegistry) -> list[str]:
    """Every reason `capability_request` could not be bound by a platform advertising `capability_registry`:
    unknown capability, missing/unknown fields, undeclared keys, or a key whose declared type differs
    from the field's.  `known_types` maps Knowledge key -> declared type: a graph's own declarations
    (declared_types()) at edit/validate/push time, or a live KnowledgeDatabase.types() at Backseater's
    bind time, so both checks are the same code."""
    capability = capability_registry.get(capability_request["capability"])
    if capability is None:
        return [f"capability '{capability_request['capability']}' does not exist on this platform. "
                f"Available: {sorted(capability_registry.all())}"]

    problems = []
    for direction, specs, bindings in (("input", capability.inputs, capability_request.get("inputs", {})),
                                       ("output", capability.outputs, capability_request.get("outputs", {}))):
        specs_by_name = {spec.name: spec for spec in specs}
        if direction == "input":   # outputs are optional; every input is required
            problems += [f"{capability.ipl_type} is missing required input '{name}' ({spec.type.__name__}); "
                         f"bind it to a declared {spec.type.__name__} key"
                         for name, spec in specs_by_name.items() if name not in bindings]
        for field_name, key in bindings.items():
            spec = specs_by_name.get(field_name)
            if spec is None:
                problems.append(f"'{field_name}' is not an {direction} of {capability.ipl_type}. "
                                f"Its {direction}s: {sorted(specs_by_name) or 'none'}")
            elif key not in known_types:
                problems.append(f"key '{key}' bound to {direction} '{field_name}' is not declared; declare it first")
            elif known_types[key] != spec.type:
                problems.append(f"{direction} '{field_name}' expects {spec.type.__name__}, but key '{key}' is declared "
                                f"{known_types[key].__name__}")
    return problems


def find_binding_problems(mission_graph: MissionGraph, capability_registry: CapabilityRegistry | None) -> list[str]:
    """find_capability_problems() over every capability request in `mission_graph`, against the
    graph's own declarations, each prefixed with where it is.  Empty when the registry is unknown
    (None) -- nothing to check against."""
    if capability_registry is None:
        return []
    known_types = declared_types(mission_graph)
    problems = []
    for node_id, node in mission_graph.get("nodes", {}).items():
        for name, capability_request in node.get("capabilities", {}).items():
            problems += [f"node '{node_id}' capability request '{name}': {problem}" for problem in
                         find_capability_problems(capability_request, known_types, capability_registry)]
    return problems
