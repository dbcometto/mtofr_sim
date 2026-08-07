"""The main simulator entry point"""
import time

from mtofr.viz import PlanePlotter
from mtofr.world.ground_plane.env import GroundPlaneEnv
from mtofr.world.ground_plane.platforms import BicycleUGV






#==========# Config #==========#
DT = 0.1
N_STEPS = 50





#==========# Set up #==========#
platforms = {"ugv1": BicycleUGV()}
env = GroundPlaneEnv(platforms)

controls = {"ugv1": {"vel": 1.0, "steer": 0.1}}

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
                env.step_all(controls, delta_t)

                #-----# Visualize #-----#
                world_states = env.get_states()
                vizualizer.update(world_states)
                # print(env.get_states()["ugv1"])

    except KeyboardInterrupt:
        pass

    except Exception as e:
        raise

    finally:
        print("Shutting down...")