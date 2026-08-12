"""Defines a world"""


class World:
    """Owns an Environment and a set of Backseaters, and runs the sim loop"""
    def __init__(self, environment, backseaters: dict, debug=False):
        self.environment = environment
        self.backseaters = backseaters   # entity_id -> Backseater

        self.debug = debug

    def step(self, dt: float) -> None:
        for entity_id, backseater in self.backseaters.items():
            if self.debug:
                print(f"[World] Updating backseater '{entity_id}'")
            backseater.update()
            backseater.frontseater.update()

        self.environment.step_dynamics_all(
            {entity_id: backseater.frontseater.hardware for entity_id, backseater in self.backseaters.items()}, dt
        )

    def get_states(self) -> dict:
        return {entity_id: backseater.frontseater.hardware.state for entity_id, backseater in self.backseaters.items()}