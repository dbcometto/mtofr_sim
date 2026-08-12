"""Defines the capability registry: typed, self-describing actions a Frontseater advertises."""
from dataclasses import dataclass


#==========# Schema #==========#

@dataclass(frozen=True)
class ParamSpec:
    """Describes one named input a capability's params dict must contain."""
    name: str
    type: type
    description: str
    is_memory_ref: bool = False   # if True, the mission graph supplies a Memory id (str);
                                   # Backseater resolves it to an instance of `type` before actuate()

    def describe(self) -> str:
        """Plaintext description of this param for a planner LLM or human."""
        if self.is_memory_ref:
            memory_description = self.type.describe()
            return f"{self.name} (Memory id -> {self.type.__name__}): {self.description}\n        {memory_description}"
        return f"{self.name} ({self.type.__name__}): {self.description}"


@dataclass(frozen=True)
class Capability:
    """One platform-agnostic action a Frontseater can perform. `ipl_type` is the
    mission-graph-facing name — what a primitive's "type" field must match, and what
    Backseater passes straight through to Frontseater.actuate()."""
    ipl_type: str
    description: str
    params: tuple[ParamSpec, ...] = ()

    def validate(self, resolved_params: dict) -> None:
        """Raises ValueError if resolved_params doesn't satisfy every ParamSpec.
        Expects params already resolved (memory ids swapped for their entries)."""
        for spec in self.params:
            if spec.name not in resolved_params:
                raise ValueError(f"Capability '{self.ipl_type}' missing required param '{spec.name}'")
            value = resolved_params[spec.name]
            if not isinstance(value, spec.type):
                raise ValueError(
                    f"Capability '{self.ipl_type}' param '{spec.name}' expected {spec.type.__name__}, "
                    f"got {type(value).__name__}"
                )

    def describe(self) -> str:
        """Plaintext description of this capability and its params, for a planner LLM or human."""
        lines = [f"{self.ipl_type}: {self.description}"]
        for spec in self.params:
            lines.append(f"    {spec.describe()}")
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