"""Defines the capability registry: typed, self-describing actions a Frontseater advertises."""
from dataclasses import dataclass


#==========# Schema #==========#

@dataclass(frozen=True)
class ParamSpec:
    """Describes one named field of a capability — either an input its inputs dict must
    contain, or an output it may write via poll_status(); the same shape serves both.
    Every field is a Knowledge reference: the mission graph always supplies a Knowledge
    key (str), and Backseater always resolves/commits it as an instance of `type` — there
    is no separate "raw value" path. A capability may omit any declared output on a given
    poll, whichever are meaningful for its current status."""
    name: str
    type: type
    description: str

    def describe(self) -> str:
        """Plaintext description of this field for a planner LLM or human."""
        header = f"{self.name} (Knowledge id -> {self.type.__name__}): {self.description}"
        if hasattr(self.type, "describe"):   # KnowledgeEntry subclasses self-describe; plain types (float, bool, ...) don't
            return f"{header}\n        {self.type.describe()}"
        return header


@dataclass(frozen=True)
class Capability:
    """One platform-agnostic action a Frontseater can perform. `ipl_type` is the
    mission-graph-facing name — what a primitive's "capability" field must match, and what
    Backseater passes straight through to Frontseater.actuate()."""
    ipl_type: str
    description: str
    inputs: tuple[ParamSpec, ...] = ()
    outputs: tuple[ParamSpec, ...] = ()

    def describe(self) -> str:
        """Plaintext description of this capability, its inputs, and its outputs, for a planner LLM or human."""
        lines = [f"{self.ipl_type}: {self.description}"]
        for spec in self.inputs:
            lines.append(f"    input {spec.describe()}")
        for spec in self.outputs:
            lines.append(f"    output {spec.describe()}")
        return "\n".join(lines)


#==========# Registry #==========#

class CapabilityRegistry:
    """Read-only lookup of a Frontseater's advertised capabilities, keyed by mission-graph
    IPL type name. This is the query path a Backseater (and eventually a planner) uses instead
    of assuming what a platform can do."""
    def __init__(self, capabilities: list[Capability]):
        self._by_ipl_type = {capability.ipl_type: capability for capability in capabilities}

    def get(self, ipl_type: str) -> Capability | None:
        """Returns the Capability for an IPL type, or None if unsupported."""
        return self._by_ipl_type.get(ipl_type)

    def all(self) -> dict:
        """ipl_type -> Capability for every advertised capability."""
        return dict(self._by_ipl_type)

    def describe(self) -> str:
        """Plaintext listing of every advertised capability, for a planner LLM or human."""
        return "\n".join(capability.describe() for capability in self._by_ipl_type.values())


#==========# Binding check #==========#

def find_primitive_problems(primitive: dict, declared_knowledge: dict, capability_registry) -> list:
    """Every reason `primitive` (a mission-graph {"capability", "inputs", "outputs"} dict) could not be bound by
    a platform advertising `capability_registry`: unknown capability, missing/unknown fields, undeclared keys,
    or a key whose declared type differs from the field's. `declared_knowledge` is a mission graph's
    "knowledge" section. Mirrors Backseater's bind-time check, but runs on the graph alone so a bad binding
    is reported at edit/validate/push time instead of halting a running mission."""
    capability = capability_registry.get(primitive["capability"])
    if capability is None:
        return [f"capability '{primitive['capability']}' does not exist on this platform. "
                f"Available: {sorted(capability_registry.all())}"]

    problems = []
    for direction, specs, bindings in (("input", capability.inputs, primitive.get("inputs", {})),
                                       ("output", capability.outputs, primitive.get("outputs", {}))):
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
            elif key not in declared_knowledge:
                problems.append(f"key '{key}' bound to {direction} '{field_name}' is not declared; declare it first")
            elif declared_knowledge[key]["type"] != spec.type:
                problems.append(f"{direction} '{field_name}' expects {spec.type.__name__}, but key '{key}' is declared "
                                f"{declared_knowledge[key]['type'].__name__}")
    return problems


def find_binding_problems(mission_graph: dict, capability_registry) -> list:
    """find_primitive_problems() over every primitive in `mission_graph`, each prefixed with where it is.
    Empty when the registry is unknown (None) -- nothing to check against."""
    if capability_registry is None:
        return []
    problems = []
    for node_id, node in mission_graph.get("nodes", {}).items():
        for name, primitive in node.get("primitives", {}).items():
            problems += [f"node '{node_id}' primitive '{name}': {problem}" for problem in
                         find_primitive_problems(primitive, mission_graph.get("knowledge", {}), capability_registry)]
    return problems
