"""The main simulator entry point"""
import time
from pathlib import Path

import mtofr.maps as maps_package
from mtofr.viz.dashboard import MissionDashboard
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.world.platform import Platform
from mtofr.maps import GroundMap
from mtofr.missions import MissionSet, MISSION_SETS


#==========# Config #==========#
DT = 0.1
ENABLE_HEADLESS = False
DEBUG = False   # turns on [World]/[Backseater]/[Frontseater] debug prints
# SPLIT: independent loops. WAIT: ugv2 waits on ugv1 via mesh sync. VILLAGE: exercises
# simple_village's road speed boost and blocked-terrain hard stop. VILLAGE_DEFAULT: same
# map, but every platform (including the mission-editor "interface" platform) boots onto
# its own default_mission_graph() -- author/push a real mission live via its window.
ACTIVE_MISSION_SET = MissionSet.VILLAGE_DEFAULT


# Setup and the main loop both live inside this guard, not just the loop: BicycleFrontseater
# spawns a worker process per platform, and multiprocessing's default "spawn" start method
# on Windows re-imports this file as __main__ in every worker process. Unguarded top-level
# setup code would re-run there too -- reconstructing the whole world (and spawning more
# worker processes) inside each worker, recursively.
if __name__ == "__main__":
    #==========# Set up #==========#
    mission_set = MISSION_SETS[ACTIVE_MISSION_SET]

    platforms = {spec.platform_id: Platform(spec, debug=DEBUG) for spec in mission_set.platforms}

    try:
        ground_map = None if mission_set.map_name is None \
            else GroundMap.load(Path(maps_package.__file__).parent / mission_set.map_name)
        environment = GroundPlaneEnv(ground_map=ground_map)
        world = World(environment, platforms=platforms, debug=DEBUG)
        vizualizer = None if ENABLE_HEADLESS else MissionDashboard(world, PlanePlotter(ground_map=ground_map))

        # Only now do World and the dashboard's Tk root exist -- some platforms (e.g. the
        # mission editor) need them for setup they couldn't do at construction.
        window_root = None if vizualizer is None else vizualizer.root
        for platform in platforms.values():
            platform.attach(world, window_root)
    except BaseException:
        # The platforms above already spawned their MPC worker processes; a setup failure
        # here (e.g. World refusing a platform its environment can't host) would orphan them.
        for platform in platforms.values():
            platform.shutdown()
        raise

    #==========# Main #==========#
    accumulator = 0.0
    render_accumulator = 0.0   # throttles vizualizer.update() to ~1/DT, even while paused
    last_time = time.perf_counter()
    try:
        while True:
            if vizualizer is not None and not vizualizer.is_open():
                break

            current_time = time.perf_counter()
            frame_dt = current_time - last_time
            accumulator += frame_dt
            render_accumulator += frame_dt
            last_time = current_time

            paused = vizualizer is not None and vizualizer.is_paused()
            did_work = False
            if paused:
                accumulator = 0.0   # don't build up backlog while paused
                if vizualizer is not None and render_accumulator >= DT:
                    vizualizer.update()
                    render_accumulator = 0.0
                    did_work = True
            else:
                if accumulator > 5 * DT:
                    if DEBUG:
                        print(f"[main.py] Falling behind, skipping {accumulator - DT:.3f}s")
                    accumulator = DT   # drop the backlog instead of stepping through it

                while accumulator >= DT:
                    world.step(DT)
                    accumulator -= DT
                    did_work = True

                # Refresh once per outer-loop iteration rather than after every step:
                # a catch-up burst (up to 5*DT of backlog) still stays visually smooth
                # since it's at most a handful of steps, and this avoids redrawing the
                # whole dashboard (mission graph, knowledge/capability trees, plot)
                # once per physics step, which was the dominant per-tick viz cost.
                if did_work and vizualizer is not None:
                    vizualizer.update()
                    render_accumulator = 0.0

            # Without this, the loop busy-spins as fast as the CPU allows whenever
            # there's no step/redraw to do (e.g. paused, or waiting for the next DT
            # to accumulate), permanently maxing out one core doing nothing.
            if not did_work:
                time.sleep(0.001)

    except KeyboardInterrupt:
        pass

    except Exception as e:
        raise

    finally:
        print("Shutting down...")
        for platform in platforms.values():
            platform.shutdown()