"""Defines a world"""


class World:
    """Owns an Environment and a set of Platforms, and runs the sim loop: the sim harness
    standing in for the physical world, comms (mesh sync) and scheduling, none of which a
    real deployment's platforms would need a World for. Platforms never reference World
    back. Refuses at construction any platform whose Hardware can't live in this
    environment (see Hardware.environment_type)."""
    def __init__(self, environment, platforms: dict, debug: bool = False):
        """Takes `platforms` (platform_id -> Platform); raises TypeError for any the environment can't host."""
        for platform_id, platform in platforms.items():
            _check_hosts(environment, platform_id, platform.hardware)
        self.environment = environment
        self.platforms = platforms   # platform_id -> Platform

        self.debug = debug

    def step(self, dt: float) -> None:
        """Advances every platform and the mesh by one tick of `dt` (s)."""
        # NOTE: each phase is isolated per platform: a bespoke Frontseater raising (e.g. a
        # broken set_active_primitives() implementation, or a real hardware fault a
        # future deployment would see) skips only that platform for the rest of this
        # tick, rather than crashing the whole simulation step. In a real deployment
        # each platform's stack runs in its own process/node, so this mirrors that
        # isolation rather than inventing new behavior.
        failed_platform_ids = set()


        # Backseaters
        for platform_id, platform in self.platforms.items():
            if self.debug:
                print(f"[World] Updating backseater '{platform_id}'")
            try:
                platform.backseater.update()
            except Exception as error:
                print(f"[World] Backseater '{platform_id}' update() failed: {error} — skipping this tick.")
                failed_platform_ids.add(platform_id)


        # Frontseaters
        # NOTE: split across all platforms rather than looping platform-by-platform:
        # begin_update() lets a Frontseater dispatch its (possibly expensive) control
        # computation to a worker process without blocking, so every platform's work
        # is in flight before finish_update() collects any one of them, letting
        # independent platforms' solves overlap instead of serializing.
        for platform_id, platform in self.platforms.items():
            if platform_id not in failed_platform_ids:
                try:
                    platform.frontseater.begin_update()
                except Exception as error:
                    print(f"[World] Frontseater '{platform_id}' begin_update() failed: {error} — skipping this tick.")
                    failed_platform_ids.add(platform_id)
        for platform_id, platform in self.platforms.items():
            if platform_id not in failed_platform_ids:
                try:
                    platform.frontseater.finish_update()
                except Exception as error:
                    print(f"[World] Frontseater '{platform_id}' finish_update() failed: {error} — skipping this tick.")


        # Hardware
        # Every platform's hardware steps itself against the (passive) environment,
        # including one whose brain faulted above, since a real vehicle keeps coasting
        # on its last controls regardless. Isolated per platform, like the phases above.
        for platform_id, platform in self.platforms.items():
            try:
                platform.hardware.step_dynamics(dt, self.environment)
            except Exception as error:
                print(f"[World] Hardware '{platform_id}' step_dynamics() failed: {error} — skipping this tick.")


        # Mesh sync
        # Happens last, after every backseater has committed this tick's fresh Knowledge,
        # so a synced fact lands in time for *next* tick's edge evaluation; fine, since in
        # a real deployment platforms update asynchronously anyway.
        # TODO: full connectivity is assumed (every backseater treats every other as a
        # peer in comms range); partial/topological connectivity is deferred.
        for platform_id, platform in self.platforms.items():
            peers = [peer.backseater for peer_id, peer in self.platforms.items() if peer_id != platform_id]
            platform.backseater.sync_with_stale_peers(peers)

    def get_states(self) -> dict:
        """Returns platform_id -> that platform's ground-truth WorldState."""
        return {platform_id: platform.hardware.state for platform_id, platform in self.platforms.items()}


def _check_hosts(environment, platform_id: str, hardware) -> None:
    """Raises TypeError unless hardware declares an environment_type that environment satisfies (None = any)."""
    hardware_name = type(hardware).__name__
    if not hasattr(hardware, "environment_type"):
        raise TypeError(f"Platform '{platform_id}': {hardware_name} never declares environment_type "
                        f"(the Environment class it lives in, or None for any)")
    required_type = hardware.environment_type
    if required_type is not None and not isinstance(environment, required_type):
        raise TypeError(f"Platform '{platform_id}': {hardware_name} can only live in a {required_type.__name__}, "
                        f"but this World's environment is a {type(environment).__name__}")
