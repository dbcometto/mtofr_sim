"""Defines an agent"""


class Agent:
    """Wraps a Platform with memory and mission tracking.

    Mission graph:
      {"nodes": {id: {"primitives": [...]}},
       "edges": {id: [{"conditions": [{"primitive": i, "status": "success"}, ...], "to": next_id}, ...]},
       "start": id}
    Edges are checked in order; the first edge whose conditions are all
    satisfied by current primitive statuses is taken.
    Agent never touches WorldState directly.
    """

    def __init__(self, platform, memory, mission_graph=None):
        self.platform = platform
        self.memory = memory
        self.mission_graph = mission_graph or {"nodes": {}, "edges": {}, "start": None}
        self.active_node_id = self.mission_graph.get("start")
        self._handles = {}      # primitive index -> handle
        self._statuses = {}     # primitive index -> last known status
        self._blocked = False

    def _activate_node(self, node_id):
        self.active_node_id = node_id
        self._handles = {}
        self._statuses = {}

    def update(self) -> None:
        if self._blocked or self.active_node_id is None:
            return

        node = self.mission_graph["nodes"][self.active_node_id]
        primitives = node["primitives"]
        caps = self.platform.capabilities()

        for name, p in primitives.items():
            capability = caps.get(p["type"])
            if capability is None:
                print(f"[Agent] Platform cannot fulfill IPL type '{p['type']}' — halting mission.")
                for h in self._handles.values():
                    self.platform.cancel(h)
                self._blocked = True
                return

            if name not in self._handles:
                self._handles[name] = self.platform.actuate(capability, p["params"])
                self._statuses[name] = "received"
                print(f"[Agent] Node '{self.active_node_id}' primitive '{name}' ({p['type']}) -> actuated")
                continue

            status = self.platform.poll_status(self._handles[name])["status"]
            if status != self._statuses.get(name):
                print(f"[Agent] Node '{self.active_node_id}' primitive '{name}' ({p['type']}) -> {status}")
            self._statuses[name] = status
            if status in ("fail", "timeout"):
                del self._handles[name]

        for edge in self.mission_graph["edges"].get(self.active_node_id, []):
            if all(self._statuses.get(c["primitive"]) == c["status"] for c in edge["conditions"]):
                print(f"[Agent] Transitioning '{self.active_node_id}' -> '{edge['to']}'")
                self._activate_node(edge["to"])
                break