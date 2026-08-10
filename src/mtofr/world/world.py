"""Defines a world"""


class World:
    """Owns an Environment and a set of Agents, and runs the sim loop"""
    def __init__(self, env, agents: dict, debug=False):
        self.env = env
        self.agents = agents   # eid -> Agent

        self.debug = debug

    def step(self, dt: float) -> None:
        for eid, agent in self.agents.items():
            if self.debug:
                print(f"[World] Updating agent '{eid}'")
            agent.update()

        self.env.step_dynamics_all(
            {eid: a.platform for eid, a in self.agents.items()}, dt
        )

    def get_states(self) -> dict:
        return {eid: a.platform.state for eid, a in self.agents.items()}