"""The main simulator entry point"""
import time

from mtofr.viz import PlanePlotter
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.hardware import BicycleHardware
from mtofr.world.ground_plane.frontseater import BicycleFrontseater
from mtofr.backseater.backseater import Backseater
from mtofr.memory.memory import Memory






#==========# Config #==========#
DT = 0.1
ENABLE_HEADLESS = False

test_mission = {
    "nodes": {
        "n1": {"primitives": {
            "avoid1": {"type": "avoid", "params": {"point": (0.0, 0.0), "radius": 2.0}},
            "nav": {"type": "move_to", "params": {"target": (5.0, 5.0)}},
        }},
        "n2": {"primitives": {
            "avoid1": {"type": "avoid", "params": {"point": (0.0, 0.0), "radius": 2.0}},
            "nav": {"type": "move_to", "params": {"target": (-5.0, -5.0)}},
        }},
    },
    "edges": {
        "n1": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "n2"}],
        "n2": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "n1"}],
    },
    "start": "n1",
}


test_mission_2 = {
    "nodes": {
        "n1": {"primitives": {
            "nav": {"type": "move_to", "params": {"target": (7.0, 7.0)}},
        }},
        "n2": {"primitives": {
            "avoid_top_center": {"type": "avoid", "params": {"point": (0.0, 9.0), "radius": 3.0}},
            "nav": {"type": "move_to", "params": {"target": (-7.0, 7.0)}},
        }},
        "n3": {"primitives": {
            "avoid_origin": {"type": "avoid", "params": {"point": (0.0, 2.0), "radius": 2.0}},
            "nav": {"type": "move_to", "params": {"target": (7.0, -7.0)}},
        }},
    },
    "edges": {
        "n1": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "n2"}],
        "n2": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "n3"}],
        "n3": [{"conditions": [{"primitive": "nav", "status": "success"}], "to": "n1"}],
    },
    "start": "n1",
}



#==========# Set up #==========#
hardware = BicycleHardware()
frontseater = BicycleFrontseater(hardware=hardware)
memory = Memory()
backseater = Backseater(frontseater=frontseater, memory=memory, mission_graph=test_mission_2)


environment = GroundPlaneEnv()
world = World(environment, backseaters={"ugv1": backseater})
vizualizer = None if ENABLE_HEADLESS else PlanePlotter()



#==========# Main #==========#
accumulator = 0.0
last_time = time.perf_counter()
if __name__ == "__main__":
    try:
        while True:
            if vizualizer is not None and not vizualizer.is_open():
                break

            current_time = time.perf_counter()
            accumulator += current_time - last_time
            last_time = current_time

            if accumulator > 5 * DT:
                print(f"[main.py] Falling behind, skipping {accumulator - DT:.3f}s")
                accumulator = DT   # drop the backlog instead of stepping through it

            while accumulator >= DT:
                world.step(DT)
                accumulator -= DT

                if vizualizer is not None:
                    world_states = world.get_states()
                    vizualizer.update(world_states)

    except KeyboardInterrupt:
        pass

    except Exception as e:
        raise

    finally:
        print("Shutting down...")