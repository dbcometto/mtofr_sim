"""Defines hardware for the interface (mission-editor) platform."""
from mtofr.world.base import Hardware, WorldState


class ConsoleHardware(Hardware):
    """The MCU/actuator-equivalent layer for a fixed operator console: never moves,
    regardless of what controls it's sent. Exists purely so the mission-editor
    platform can share World/Environment/PlanePlotter's ordinary per-platform
    plumbing (WorldState, map-relative rendering) without a physical dynamics
    model of its own."""
    def __init__(self, initial_state: WorldState = None):
        super().__init__()
        self.state = initial_state or WorldState()

    def calculate_dynamics(self, state: WorldState, controls: dict, dt: float,
                            max_speed_multiplier: float = 1.0) -> WorldState:
        return WorldState(t=state.t + dt, x=state.x, y=state.y, theta=state.theta)