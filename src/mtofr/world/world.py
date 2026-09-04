"""Defines a world"""


class World:
    """Owns an Environment and a set of Backseaters, and runs the sim loop"""
    def __init__(self, environment, backseaters: dict, debug=False):
        self.environment = environment
        self.backseaters = backseaters   # entity_id -> Backseater

        self.debug = debug

    def step(self, dt: float) -> None:
        # Each phase is isolated per platform: a bespoke Frontseater raising (e.g. a
        # broken set_active_primitives() implementation, or a real hardware fault a
        # future deployment would see) skips only that platform for the rest of this
        # tick, rather than crashing the whole simulation step. In a real deployment
        # each platform's stack runs in its own process/node, so this mirrors that
        # isolation rather than inventing new behavior.
        failed_entity_ids = set()

        for entity_id, backseater in self.backseaters.items():
            if self.debug:
                print(f"[World] Updating backseater '{entity_id}'")
            try:
                backseater.update()
            except Exception as error:
                print(f"[World] Backseater '{entity_id}' update() failed: {error} — skipping this tick.")
                failed_entity_ids.add(entity_id)

        # Split across all platforms rather than looping backseater-by-backseater:
        # begin_update() lets a Frontseater dispatch its (possibly expensive) control
        # computation to a worker process without blocking, so every platform's work
        # is in flight before finish_update() collects any one of them -- letting
        # independent platforms' solves overlap instead of serializing.
        for entity_id, backseater in self.backseaters.items():
            if entity_id in failed_entity_ids:
                continue
            try:
                backseater.frontseater.begin_update()
            except Exception as error:
                print(f"[World] Frontseater '{entity_id}' begin_update() failed: {error} — skipping this tick.")
                failed_entity_ids.add(entity_id)
        for entity_id, backseater in self.backseaters.items():
            if entity_id in failed_entity_ids:
                continue
            try:
                backseater.frontseater.finish_update()
            except Exception as error:
                print(f"[World] Frontseater '{entity_id}' finish_update() failed: {error} — skipping this tick.")

        self.environment.step_dynamics_all(
            {entity_id: backseater.frontseater.hardware for entity_id, backseater in self.backseaters.items()}, dt
        )

        # Mesh sync happens last, after every backseater has committed this tick's
        # fresh Knowledge — a synced fact lands in time for *next* tick's edge
        # evaluation, not necessarily this one; fine, since in a real deployment
        # platforms update asynchronously anyway and one tick of lag doesn't matter.
        # Full connectivity is assumed for now (every backseater treats every other
        # backseater as a peer in comms range); partial/topological connectivity is
        # explicitly deferred.
        for entity_id, backseater in self.backseaters.items():
            peers = [peer for peer_id, peer in self.backseaters.items() if peer_id != entity_id]
            backseater.sync_with_stale_peers(peers)

    def get_states(self) -> dict:
        return {entity_id: backseater.frontseater.hardware.state for entity_id, backseater in self.backseaters.items()}