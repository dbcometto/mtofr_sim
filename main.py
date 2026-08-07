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





#==========# Set up #==========#
platform = BicycleUGV()
memory = Memory()
agent = Agent(platform=platform, memory=memory, controls={"vel": 1.0, "steer": 0.1})

env = GroundPlaneEnv()
world = World(env, agents={"ugv1": agent})
vizualizer = PlanePlotter()



#==========# Main #==========#
last_time = time.perf_counter()
if __name__ == "__main__":
    try:
        while True:
            #-----# Handle timing #-----#
            current_time = time.perf_counter()
            delta_t = current_time-last_time
            if delta_t > DT:
                last_time = current_time
                if delta_t > 2*DT:
                    print(f"Falling behind by {1000*(delta_t-DT):3.3f}ms")

                #-----# Step #-----#
                world.step(delta_t)

                #-----# Visualize #-----#
                world_states = world.get_states()
                vizualizer.update(world_states)
                # print(world.get_states()["ugv1"])

    except KeyboardInterrupt:
        pass

    except Exception as e:
        raise

    finally:
        print("Shutting down...")