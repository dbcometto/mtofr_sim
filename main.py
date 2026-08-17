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
from mtofr.missions import mission_ugv1, mission_ugv2




#==========# Config #==========#
DT = 0.1
ENABLE_HEADLESS = False
DEBUG = False   # turns on [World]/[Backseater]/[Frontseater] debug prints


#==========# Set up #==========#
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
world = World(environment, backseaters={"ugv1": ugv1_backseater, "ugv2": ugv2_backseater}, debug=DEBUG)
vizualizer = None if ENABLE_HEADLESS else MissionDashboard(world, PlanePlotter())



#==========# Main #==========#
accumulator = 0.0
render_accumulator = 0.0   # throttles vizualizer.update() to ~1/DT, even while paused
last_time = time.perf_counter()
if __name__ == "__main__":
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
            if paused:
                accumulator = 0.0   # don't build up backlog while paused
                if vizualizer is not None and render_accumulator >= DT:
                    vizualizer.update()
                    render_accumulator = 0.0
            else:
                if accumulator > 5 * DT:
                    if DEBUG:
                        print(f"[main.py] Falling behind, skipping {accumulator - DT:.3f}s")
                    accumulator = DT   # drop the backlog instead of stepping through it

                while accumulator >= DT:
                    world.step(DT)
                    accumulator -= DT
                    # Refresh after every step, not just once per outer loop iteration:
                    # during a catch-up burst (several steps back-to-back) this keeps
                    # the dashboard moving in step with the sim instead of freezing
                    # for the whole burst and then jumping to the final state.
                    if vizualizer is not None:
                        vizualizer.update()
                        render_accumulator = 0.0

    except KeyboardInterrupt:
        pass

    except Exception as e:
        raise

    finally:
        print("Shutting down...")
