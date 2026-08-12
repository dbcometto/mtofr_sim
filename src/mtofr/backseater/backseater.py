"""Defines a backseater"""


class Backseater:
    """Platform-agnostic relay between a mission graph and a Frontseater.

    Mission graph:
      {"nodes": {id: {"primitives": [...]}},
       "edges": {id: [{"conditions": [{"primitive": i, "status": "success"}, ...], "to": next_id}, ...]},
       "start": id}
    Edges are checked in order; the first edge whose conditions are all
    satisfied by current primitive statuses is taken.
    Backseater never touches WorldState directly.
    """

    def __init__(self, frontseater, memory, mission_graph=None):
        self.frontseater = frontseater
        self.memory = memory
        self.mission_graph = mission_graph or {"nodes": {}, "edges": {}, "start": None}
        self.active_node_id = self.mission_graph.get("start")
        self._handles = {}      # primitive name -> handle
        self._statuses = {}     # primitive name -> last known status
        self._blocked = False

    def capabilities(self):
        """Relays the Frontseater's advertised CapabilityRegistry — the query path a planner
        uses to discover what this backseater's platform can do, instead of assuming it."""
        return self.frontseater.capabilities()

    def _activate_node(self, node_id):
        self.active_node_id = node_id
        self._handles = {}
        self._statuses = {}

    def _resolve_params(self, capability, raw_params: dict) -> dict:
        """Resolves memory-id params to their Memory entries before actuate()."""
        resolved = {}
        for spec in capability.params:
            value = raw_params[spec.name]
            resolved[spec.name] = self.memory.get(value) if spec.is_memory_ref else value
        return resolved

    def update(self) -> None:
        if self._blocked or self.active_node_id is None:
            return

        node = self.mission_graph["nodes"][self.active_node_id]
        primitives = node["primitives"]
        capability_registry = self.frontseater.capabilities()

        for name, primitive in primitives.items():
            capability = capability_registry.get(primitive["type"])
            if capability is None:
                print(f"[Backseater] Frontseater cannot fulfill IPL type '{primitive['type']}' — halting mission.")
                for handle in self._handles.values():
                    self.frontseater.cancel(handle)
                self._blocked = True
                return

            if name not in self._handles:
                try:
                    resolved_params = self._resolve_params(capability, primitive["params"])
                    capability.validate(resolved_params)
                except (KeyError, ValueError) as error:
                    print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' "
                          f"({primitive['type']}) -> invalid params: {error} — halting mission.")
                    for handle in self._handles.values():
                        self.frontseater.cancel(handle)
                    self._blocked = True
                    return

                self._handles[name] = self.frontseater.actuate(capability.ipl_type, resolved_params)
                self._statuses[name] = "received"
                print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' ({primitive['type']}) -> actuated")
                continue

            status = self.frontseater.poll_status(self._handles[name])["status"]
            if status != self._statuses.get(name):
                print(f"[Backseater] Node '{self.active_node_id}' primitive '{name}' ({primitive['type']}) -> {status}")
            self._statuses[name] = status
            if status in ("fail", "timeout"):
                del self._handles[name]

        for edge in self.mission_graph["edges"].get(self.active_node_id, []):
            if all(self._statuses.get(condition["primitive"]) == condition["status"] for condition in edge["conditions"]):
                print(f"[Backseater] Transitioning '{self.active_node_id}' -> '{edge['to']}'")
                self._activate_node(edge["to"])
                break