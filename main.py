"""The main simulator entry point"""
import time

from mtofr.environments.world import World
from mtofr.platform.platform import Platform
from mtofr.scenarios import Scenario, SCENARIOS
from mtofr.viz.dashboard import MissionDashboard


#========================================#
# Config
#========================================#

DT = 0.1   # s per sim step
ENABLE_HEADLESS = False
DEBUG = False   # turns on [World]/[Backseater]/[Frontseater] debug prints
# SPLIT: independent loops. WAIT: ugv2 waits on ugv1 via mesh sync. VILLAGE: exercises
# simple_village's road speed boost and blocked-terrain hard stop. VILLAGE_DEFAULT: same
# map, but every platform (including the mission-editor "interface" platform) boots onto
# its own default_mission_graph() -- author/push a real mission live via its web UI
# (the address is printed at startup, and opens in a browser).
ACTIVE_SCENARIO = Scenario.VILLAGE_DEFAULT
MAX_BACKLOG_STEPS = 5   # once the loop falls further behind than this many steps, drop the backlog
IDLE_SLEEP_SECONDS = 0.001   # yields the CPU when there's no step/redraw to do







#========================================#
# Run
#========================================#

# NOTE: setup and the main loop both live inside this guard, not just the loop:
# BicycleFrontseater spawns a worker process per platform, and multiprocessing's default
# "spawn" start method on Windows re-imports this file as __main__ in every worker process.
# Unguarded top-level setup code would re-run there too -- reconstructing the whole world
# (and spawning more worker processes) inside each worker, recursively.
if __name__ == "__main__":
    print("Starting up the MTOFR Simulator...")

    #===============# Set Up #===============#

    scenario = SCENARIOS[ACTIVE_SCENARIO]

    platforms = {spec.platform_id: Platform(spec, debug=DEBUG) for spec in scenario.platforms}

    try:
        environment = scenario.build_environment()
        world = World(environment, platforms=platforms, debug=DEBUG)
        visualizer = None if ENABLE_HEADLESS else MissionDashboard(world, scenario.build_viewer(environment))

        # Only now do World and the dashboard's Tk root exist -- some platforms (e.g. the
        # mission editor) need them for setup they couldn't do at construction.
        window_root = None if visualizer is None else visualizer.root
        for platform in platforms.values():
            platform.attach(world, window_root)
    except BaseException:
        # The platforms above already spawned their MPC worker processes; a setup failure
        # here (e.g. World refusing a platform its environment can't host) would orphan them.
        for platform in platforms.values():
            platform.shutdown()
        raise





    #===============# Main Loop #===============#

    accumulator = 0.0          # s of wall time not yet stepped
    render_accumulator = 0.0   # s since the last redraw; throttles visualizer.update() to ~1/DT, even while paused
    last_time = time.perf_counter()
    try:
        while visualizer is None or visualizer.is_open():
            current_time = time.perf_counter()
            frame_dt = current_time - last_time
            accumulator += frame_dt
            render_accumulator += frame_dt
            last_time = current_time

            paused = visualizer is not None and visualizer.is_paused()
            did_work = False
            if paused:
                accumulator = 0.0   # don't build up backlog while paused
                if visualizer is not None and render_accumulator >= DT:
                    visualizer.update()
                    render_accumulator = 0.0
                    did_work = True
            else:
                if accumulator > MAX_BACKLOG_STEPS * DT:
                    if DEBUG:
                        print(f"[main.py] Falling behind, skipping {accumulator - DT:.3f}s")
                    accumulator = DT   # drop the backlog instead of stepping through it

                while accumulator >= DT:
                    world.step(DT)
                    accumulator -= DT
                    did_work = True

                # Refresh once per outer-loop iteration rather than after every step:
                # a catch-up burst (up to MAX_BACKLOG_STEPS of backlog) still stays visually
                # smooth since it's at most a handful of steps, and this avoids redrawing the
                # whole dashboard (mission graph, knowledge/capability trees, plot)
                # once per physics step, which was the dominant per-tick viz cost.
                if did_work and visualizer is not None:
                    visualizer.update()
                    render_accumulator = 0.0

            # Without this, the loop busy-spins as fast as the CPU allows whenever
            # there's no step/redraw to do (e.g. paused, or waiting for the next DT
            # to accumulate), permanently maxing out one core doing nothing.
            if not did_work:
                time.sleep(IDLE_SLEEP_SECONDS)

    except KeyboardInterrupt:
        pass

    finally:
        print("Shutting down...")
        for platform in platforms.values():
            platform.shutdown()
