"""Defines capabilities: typed, self-describing actions a Frontseater advertises and runs.
A Capability subclass is both the declaration (class attributes) and the behavior (one
instance per running capability request)."""
from dataclasses import dataclass


#========================================#
# Schema
#========================================#

@dataclass(frozen=True)
class ParamSpec:
    """Describes one named field of a capability: either an input its inputs dict must
    contain, or an output it may publish; the same shape serves both. Every field is a
    Knowledge reference: the mission graph always supplies a Knowledge key (str) whose
    declared type must be exactly `type`; there is no separate "raw value" path. A
    capability may leave any declared output unwritten, whichever are meaningful for its
    current status."""
    name: str
    type: type
    description: str

    def describe(self) -> str:
        """Plaintext description of this field for a planner LLM or human."""
        header = f"{self.name} (Knowledge id -> {self.type.__name__}): {self.description}"
        if hasattr(self.type, "describe"):   # KnowledgeEntry subclasses self-describe; plain types (float, bool, ...) don't
            return f"{header}\n        {self.type.describe()}"
        return header







#========================================#
# Capability
#========================================#

class Capability:
    """One platform-agnostic action a Frontseater can perform.  A subclass declares itself
    with class attributes and implements whichever of start()/tick()/stop()/status() it
    needs; the Frontseater base creates one instance per running capability request and
    calls them (see Frontseater.set_active_capabilities()).

    `ipl_type` is the mission-graph-facing name: what a capability request's "capability"
    field must match.  `inputs`/`outputs` declare the fields a request binds to Knowledge
    keys; read()/write() resolve those bindings, so a capability never touches the request
    dict or the Backseater directly."""
    # NOTE: no defaults for ipl_type/description, so CapabilityRegistry can refuse a
    # subclass that forgot to declare them.
    ipl_type: str
    description: str
    inputs: tuple[ParamSpec, ...] = ()
    outputs: tuple[ParamSpec, ...] = ()

    #===============# Declaration #===============#

    @classmethod
    def describe(cls) -> str:
        """Plaintext description of this capability, its inputs, and its outputs, for a planner LLM or human."""
        lines = [f"{cls.ipl_type}: {cls.description}"]
        for spec in cls.inputs:
            lines.append(f"    input {spec.describe()}")
        for spec in cls.outputs:
            lines.append(f"    output {spec.describe()}")
        return "\n".join(lines)





    #===============# Running Instance #===============#

    def __init__(self, frontseater, name: str, request: dict):
        """One running copy of this capability, for the request `name` ({"capability",
        "inputs", "outputs"}) on `frontseater` (duck-typed, so core imports nothing above it)."""
        self.frontseater = frontseater
        self.name = name
        self.request = request

    @property
    def hardware(self):
        """The Frontseater's Hardware, for read_state()."""
        return self.frontseater.hardware

    def start(self) -> None:
        """Called once when the request starts.  Default: nothing."""

    def tick(self) -> None:
        """Called every sim tick while the request runs, before controls are computed.  Default: nothing."""

    def stop(self) -> None:
        """Called once when the request stops; undo anything start()/tick() set on the Frontseater.  Default: nothing."""

    def status(self) -> str:
        """Short human-readable status for display only; never drives mission logic."""
        return "running"

    def read(self, field: str):
        """The current value of the Knowledge key bound to input `field`, queried live.
        Raises KeyError for a field this capability doesn't declare as an input."""
        if field not in {spec.name for spec in self.inputs}:
            raise KeyError(f"'{field}' is not an input of {self.ipl_type}")
        key = self.request.get("inputs", {})[field]   # bound by the Backseater's bind check
        return self.frontseater.backseater.query("knowledge", key)

    def write(self, field: str, value) -> None:
        """Publishes `value` to the Knowledge key bound to output `field`; a no-op when the
        request leaves that output unbound.  Raises KeyError for a field this capability
        doesn't declare as an output."""
        if field not in {spec.name for spec in self.outputs}:
            raise KeyError(f"'{field}' is not an output of {self.ipl_type}")
        key = self.request.get("outputs", {}).get(field)
        if key is not None:
            self.frontseater.backseater.publish("knowledge", key, value)







#========================================#
# Registry
#========================================#

class CapabilityRegistry:
    """Read-only lookup of a Frontseater's advertised Capability classes, keyed by
    mission-graph IPL type name. This is the query path a Backseater (and eventually a
    planner) uses instead of assuming what a platform can do."""
    def __init__(self, capabilities: list[type[Capability]]):
        """Indexes `capabilities` by ipl_type; raises TypeError for one that never declares it."""
        for capability in capabilities:
            if not hasattr(capability, "ipl_type") or not hasattr(capability, "description"):
                raise TypeError(f"{capability.__name__} must declare both ipl_type and description")
        self._by_ipl_type = {capability.ipl_type: capability for capability in capabilities}

    def get(self, ipl_type: str) -> type[Capability] | None:
        """Returns the Capability class for an IPL type, or None if unsupported."""
        return self._by_ipl_type.get(ipl_type)

    def all(self) -> dict:
        """ipl_type -> Capability class for every advertised capability."""
        return dict(self._by_ipl_type)

    def describe(self) -> str:
        """Plaintext listing of every advertised capability, for a planner LLM or human."""
        return "\n".join(capability.describe() for capability in self._by_ipl_type.values())
