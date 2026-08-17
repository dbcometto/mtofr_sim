"""Defines a world"""


class World:
    """Owns an Environment and a set of Backseaters, and runs the sim loop"""
    def __init__(self, environment, backseaters: dict, relay=None, debug=False):
        self.environment = environment
        self.backseaters = backseaters   # entity_id -> Backseater
        self.relay = relay               # optional Relay: canonical cross-platform Knowledge store

        self.debug = debug

    def step(self, dt: float) -> None:
        for entity_id, backseater in self.backseaters.items():
            if self.debug:
                print(f"[World] Updating backseater '{entity_id}'")
            backseater.update()

        # Split across all platforms rather than looping backseater-by-backseater:
        # begin_update() lets a Frontseater dispatch its (possibly expensive) control
        # computation to a worker process without blocking, so every platform's work
        # is in flight before finish_update() collects any one of them -- letting
        # independent platforms' solves overlap instead of serializing.
        for backseater in self.backseaters.values():
            backseater.frontseater.begin_update()
        for backseater in self.backseaters.values():
            backseater.frontseater.finish_update()

        self.environment.step_dynamics_all(
            {entity_id: backseater.frontseater.hardware for entity_id, backseater in self.backseaters.items()}, dt
        )

        # Relay syncs last, after every backseater has committed this tick's fresh
        # Knowledge — a relayed fact lands in time for *next* tick's edge evaluation,
        # not necessarily this one; fine, since in a real deployment platforms update
        # asynchronously anyway and one tick of lag doesn't matter.
        if self.relay is not None:
            self.relay.sync(self.backseaters)

    def get_states(self) -> dict:
        return {entity_id: backseater.frontseater.hardware.state for entity_id, backseater in self.backseaters.items()}