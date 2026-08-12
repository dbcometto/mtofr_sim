"""The main simulator entry point"""
import time

from mtofr.viz.dashboard import MissionDashboard
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.world.ground_plane.viz.plane_plotter import PlanePlotter
from mtofr.backseater.backseater import Backseater
from mtofr.knowledge.knowledge import Knowledge, Location




#==========# Config #==========#
DT = 0.1
ENABLE_HEADLESS = False
DEBUG = False   # turns on [World]/[Backseater]/[Frontseater] debug prints

test_mission = {
    "nodes": {
        "outbound": {"primitives": {
            "avoid_origin": {"type": "avoid", "params": {"point": "origin", "radius": 2.0}},
            "nav": {"type": "move_to", "params": {"target": "northeast"}},
        }},
        "return": {"primitives": {
            "avoid_origin": {"type": "avoid", "params": {"point": "origin", "radius": 2.0}},
            "nav": {"type": "move_to", "params": {"target": "southwest"}},
        }},
    },
    "edges": {
        "outbound": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "return"}],
        "return": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "outbound"}],
    },
    "start": "outbound",
}


test_mission_2 = {
    "nodes": {
        "head_east": {"primitives": {
            "nav": {"type": "move_to", "params": {"target": "east"}},
        }},
        "loop_west": {"primitives": {
            "avoid_top_center": {"type": "avoid", "params": {"point": "top_center", "radius": 3.0}},
            "nav": {"type": "move_to", "params": {"target": "west"}},
        }},
        "return_southeast": {"primitives": {
            "avoid_origin": {"type": "avoid", "params": {"point": "north_of_origin", "radius": 2.0}},
            "nav": {"type": "move_to", "params": {"target": "southeast"}},
        }},
    },
    "edges": {
        "head_east": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "loop_west"}],
        "loop_west": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "return_southeast"}],
        "return_southeast": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "head_east"}],
    },
    "start": "head_east",
}



#==========# Set up #==========#
hardware = BicycleHardware()
frontseater = BicycleFrontseater(hardware=hardware, debug=DEBUG)

knowledge = Knowledge()
knowledge.add("origin", Location(0.0, 0.0))
knowledge.add("northeast", Location(5.0, 5.0))
knowledge.add("southwest", Location(-5.0, -5.0))
knowledge.add("east", Location(7.0, 7.0))
knowledge.add("west", Location(-7.0, 7.0))
knowledge.add("southeast", Location(7.0, -7.0))
knowledge.add("top_center", Location(0.0, 9.0))
knowledge.add("north_of_origin", Location(0.0, 2.0))

backseater = Backseater(frontseater=frontseater, knowledge=knowledge, mission_graph=test_mission_2, debug=DEBUG)


environment = GroundPlaneEnv()
world = World(environment, backseaters={"ugv1": backseater}, debug=DEBUG)
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
