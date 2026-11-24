"""Village-default scenario: the same map as village, but every platform boots straight
onto its own Frontseater.default_mission_graph() -- ugv1/ugv2 idle-loiter (gossiping
their poses), and the interface platform serves its web UI -- until a mission is
authored and pushed live via that UI."""
from mtofr.environments.ground_plane.env import GroundPlaneEnv
from mtofr.environments.ground_plane.maps import load_map
from mtofr.environments.ground_plane.platforms.bicycle_ugv.spec import bicycle_ugv
from mtofr.environments.ground_plane.platforms.interface.spec import interface
from mtofr.environments.ground_plane.state import GroundPlaneState
from mtofr.environments.ground_plane.viz import PlanePlotter
from mtofr.scenarios.base import ScenarioConfig


#========================================#
# Scenario
#========================================#

SCENARIO = ScenarioConfig(
    build_environment=lambda: GroundPlaneEnv(load_map("simple_village")),
    build_viewer=PlanePlotter.for_environment,
    platforms=[
        bicycle_ugv("ugv1", 45.0, -20.0, start_theta=1.57),
        bicycle_ugv("ugv2", 45.0, -30.0, start_theta=1.57),
        # (0, -30) is clear, unblocked terrain on simple_village's map -- verified
        # against GroundMap.is_blocked()/speed_multiplier_at() directly. interface()
        # defaults to privilege 0, outranking ugv1/ugv2's default 1 so its pushes pass
        # write_mission()'s privilege gate.
        interface("interface", GroundPlaneState(x=50.0, y=-50.0)),
    ],
)
