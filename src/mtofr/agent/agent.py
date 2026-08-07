"""Defines an agent"""


class Agent:
    """Wraps a Platform with memory and mission tracking"""
    def __init__(self, platform, memory, mission_state=None, controls=None):
        self.platform = platform
        self.memory = memory
        self.mission_state = mission_state
        self._controls = controls or {}   # fixed for now, no real planner yet

    def plan(self, state, mission_state) -> dict:
        return self._controls

    def update_mission(self, state, mission_state):
        return mission_state   # no primitives wired up yet