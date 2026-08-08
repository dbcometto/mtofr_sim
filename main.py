"""The main simulator entry point"""
import time

from mtofr.viz import PlanePlotter
from mtofr.world.world import World
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.platforms import BicycleUGV
from mtofr.agent.agent import Agent
from mtofr.memory.memory import Memory






#==========# Config #==========#
DT = 0.1

test_mission = [
    {"target": (5.0, 5.0),"avoid": [{"point": (0.0, 0.0), "radius": 2.0}]},
    {"target": (-5.0, -5.0), "avoid": [{"point": (0.0, 0.0), "radius": 2.0}]},
]



#==========# Set up #==========#
platform = BicycleUGV()
memory = Memory()
agent = Agent(platform=platform, memory=memory, mission=test_mission)


env = GroundPlaneEnv()
world = World(env, agents={"ugv1": agent})
vizualizer = PlanePlotter()



#==========# Main #==========#
accumulator = 0.0
last_time = time.perf_counter()
if __name__ == "__main__":
    try:
        while True:
            current_time = time.perf_counter()
            accumulator += current_time - last_time
            last_time = current_time

            if accumulator > 5 * DT:
                print(f"Falling behind, skipping {accumulator - DT:.3f}s")
                accumulator = DT   # drop the backlog instead of stepping through it

            while accumulator >= DT:
                world.step(DT)
                accumulator -= DT

                world_states = world.get_states()
                vizualizer.update(world_states)

    except KeyboardInterrupt:
        pass

    except Exception as e:
        raise

    finally:
        print("Shutting down...")