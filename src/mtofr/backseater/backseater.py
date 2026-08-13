"""Defines a backseater"""
from mtofr.condition.condition import parse_condition


class Backseater:
    """Platform-agnostic relay between a mission graph and a Frontseater.

    Mission graph:
      {"knowledge": {key: {"type": type, "value": value}, ...},
       "nodes": {id: {"primitives": {name: {"capability", "inputs", "outputs"}}}},
       "edges": {id: [{"condition": [token, ...], "to": next_id}, ...]},
       "start": id}
    `condition` is a pre-tokenized boolean expression over Knowledge keys (see
    mtofr.condition.condition), parsed once at construction. Edges are checked in
    order; the first edge whose condition evaluates true against current Knowledge
    is taken. Primitive `status` (waiting/success/fail/timeout) is comms-health
    information between Backseater and Frontseater only — it never drives edges;
    a capability decides for itself what, if anything, to write to Knowledge.
    Backseater never touches WorldState directly.
    """

    def __init__(self, frontseater, knowledge, mission_graph=None, debug=False):
        self.frontseater = frontseater
        self.knowledge = knowledge
        self.mission_graph = mission_graph or {"knowledge": {}, "nodes": {}, "edges": {}, "start": None}
        self.debug = debug

        for key, declaration in self.mission_graph.get("knowledge", {}).items():
            self.knowledge.declare(key, declaration["type"], declaration["value"])

        self._parsed_conditions = {
            node_id: [(parse_condition(edge["condition"]), edge["to"]) for edge in edges]
            for node_id, edges in self.mission_graph.get("edges", {}).items()
        }

        self.active_node_id = self.mission_graph.get("start")
        self._handles = {}      # primitive name -> handle
        self._statuses = {}     # primitive name -> last known status
        self._blocked = False

    def capabilities(self):
        """Relays the Frontseater's advertised CapabilityRegistry — the query path a planner
        uses to discover what this backseater's platform can do, instead of assuming it."""
        return self.frontseater.capabilities()

    def status(self) -> dict:
        """Read-only snapshot of mission progress — the query path a visualization tool
        uses instead of reaching into private state. Primitive statuses default to
        "pending" for primitives in the active node that haven't been actuated yet."""
        node = self.mission_graph["nodes"].get(self.active_node_id, {}) if self.active_node_id else {}
        primitives = node.get("primitives", {})
        return {
            "active_node_id": self.active_node_id,
            "blocked": self._blocked,
            "primitives": {
                name: {
                    "capability": primitive["capability"],
                    "status": self._statuses.get(name, "pending"),
                    "handle": self._handles.get(name),
                }
                for name, primitive in primitives.items()
            },
        }

    def _activate_node(self, node_id):
        self.active_node_id = node_id
        self._handles = {}
        self._statuses = {}

    def _resolve_inputs(self, capability, raw_inputs: dict) -> dict:
        """Resolves every input's Knowledge key to its current value before actuate() —
        every capability input is a Knowledge reference, there is no raw-value path."""
        return {spec.name: self.knowledge.get(raw_inputs[spec.name]) for spec in capability.inputs}

    def _commit_outputs(self, capability, primitive, outputs: dict) -> None:
        """Validates and writes any bound capability outputs to Knowledge. Raises ValueError
        on a bad/mistyped output — the same failure mode as bad inputs, caught by update()."""
        capability.validate_outputs(outputs)
        for output_name, knowledge_key in primitive.get("outputs", {}).items():
            if output_name in outputs:
                self.knowledge.set(knowledge_key, outputs[output_name])

    def update(self) -> None:
        if self._blocked or self.active_node_id is None:
            return

        node = self.mission_graph["nodes"][self.active_node_id]
        primitives = node["primitives"]
        capability_registry = self.frontseater.capabilities()

        for name, primitive in primitives.items():
            capability = capability_registry.get(primitive["capability"])
            if capability is None:
                print(f"[Backseater] Frontseater cannot fulfill IPL type '{primitive['capability']}' — halting mission.")
                for handle in self._handles.values():
                    self.frontseater.cancel(handle)
                self._blocked = True
                return

            if name not in self._handles:
                try:
                    resolved_inputs = self._resolve_inputs(capability, primitive["inputs"])
                    capability.validate_inputs(resolved_inputs)
                except (KeyError, ValueError) as error:
                    print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' "
                          f"({primitive['capability']}) -> invalid inputs: {error} — halting mission.")
                    for handle in self._handles.values():
                        self.frontseater.cancel(handle)
                    self._blocked = True
                    return

                self._handles[name] = self.frontseater.start_capability(capability.ipl_type, resolved_inputs)
                if self.debug:
                    print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' ({primitive['capability']}) -> started")

            # Poll immediately, including on the tick a primitive was just started: a
            # resettable output (e.g. move_to's "arrived") must be recommitted to
            # Knowledge the same tick it's reset, or a stale prior value could satisfy
            # an edge condition for one extra tick before the fresh value lands.
            poll_result = self.frontseater.poll_status(self._handles[name])
            status = poll_result["status"]
            if self.debug and status != self._statuses.get(name):
                print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' ({primitive['capability']}) -> {status}")
            self._statuses[name] = status
            if status in ("fail", "timeout"):
                del self._handles[name]

            try:
                self._commit_outputs(capability, primitive, poll_result.get("outputs", {}))
            except ValueError as error:
                print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' "
                      f"({primitive['capability']}) -> invalid output: {error} — halting mission.")
                for handle in self._handles.values():
                    self.frontseater.cancel(handle)
                self._blocked = True
                return

        for condition, target_node_id in self._parsed_conditions.get(self.active_node_id, []):
            if condition.evaluate(self.knowledge):
                if self.debug:
                    print(f"[Backseater] Transitioning '{self.active_node_id}' -> '{target_node_id}'")
                self._activate_node(target_node_id)
                break
