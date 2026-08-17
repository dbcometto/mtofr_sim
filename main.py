"""The main simulator entry point"""
import time

from mtofr.viz.dashboard import MissionDashboard
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.backseater.backseater import Backseater
from mtofr.knowledge.knowledge import Knowledge
from mtofr.relay.relay import Relay
from mtofr.missions import (
    MissionSet, mission_split_ugv1, mission_split_ugv2, mission_wait_ugv1, mission_wait_ugv2,
)


#==========# Config #==========#
DT = 0.1
ENABLE_HEADLESS = False
DEBUG = False   # turns on [World]/[Backseater]/[Frontseater] debug prints
ACTIVE_MISSION_SET = MissionSet.SPLIT   # SPLIT: independent loops. WAIT: ugv2 waits on ugv1 via Relay.

MISSION_SETS = {
    MissionSet.SPLIT: (mission_split_ugv1, mission_split_ugv2),
    MissionSet.WAIT: (mission_wait_ugv1, mission_wait_ugv2),
}


# Setup and the main loop both live inside this guard, not just the loop: BicycleFrontseater
# spawns a worker process per platform, and multiprocessing's default "spawn" start method
# on Windows re-imports this file as __main__ in every worker process. Unguarded top-level
# setup code would re-run there too -- reconstructing the whole world (and spawning more
# worker processes) inside each worker, recursively.
if __name__ == "__main__":
    #==========# Set up #==========#
    mission_ugv1, mission_ugv2 = MISSION_SETS[ACTIVE_MISSION_SET]

    ugv1_hardware = BicycleHardware()
    ugv1_frontseater = BicycleFrontseater(hardware=ugv1_hardware, debug=DEBUG)
    ugv1_knowledge = Knowledge()
    ugv1_backseater = Backseater(frontseater=ugv1_frontseater, knowledge=ugv1_knowledge,
                                  mission_graph=mission_ugv1, platform_id="ugv1", debug=DEBUG)

    ugv2_hardware = BicycleHardware()
    ugv2_frontseater = BicycleFrontseater(hardware=ugv2_hardware, debug=DEBUG)
    ugv2_knowledge = Knowledge()
    ugv2_backseater = Backseater(frontseater=ugv2_frontseater, knowledge=ugv2_knowledge,
                                  mission_graph=mission_ugv2, platform_id="ugv2", debug=DEBUG)

    environment = GroundPlaneEnv()
    relay = Relay()
    world = World(environment, backseaters={"ugv1": ugv1_backseater, "ugv2": ugv2_backseater}, relay=relay, debug=DEBUG)
    vizualizer = None if ENABLE_HEADLESS else MissionDashboard(world, PlanePlotter())

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
        ugv1_frontseater.shutdown()
        ugv2_frontseater.shutdown()