"""Defines a world"""


class World:
    """Owns an Environment and a set of Agents, and runs the sim loop"""
    def __init__(self, env, agents: dict):
        self.env = env
        self.agents = agents   # eid -> Agent

    def step(self, dt: float) -> None:
        controls = {eid: a.plan(a.platform.state) for eid, a in self.agents.items()}

        new_states = self.env.step_dynamics_all(
            {eid: a.platform for eid, a in self.agents.items()}, controls, dt
        )

        for eid, agent in self.agents.items():
            agent.platform.state = new_states[eid]

    def get_states(self) -> dict:
        return {eid: a.platform.state for eid, a in self.agents.items()}