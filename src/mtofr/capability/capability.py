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
