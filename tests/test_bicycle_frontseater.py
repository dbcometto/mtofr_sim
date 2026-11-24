"""Tests for BicycleFrontseater's capability implementations (set_active_capabilities/
_step_active_capabilities/describe_status) exercised directly, independent of any
Backseater/mission-graph driving them. A capability calls query()/publish() on its own
Backseater, so these tests wire in a minimal fake backseater (a plain dict-backed
query/publish) instead of a full Backseater."""
import unittest

from mtofr.database import Location, Pose
from mtofr.environments.ground_plane.platforms.bicycle_ugv.hardware import BicycleHardware
from mtofr.environments.ground_plane.platforms.bicycle_ugv.frontseater import BicycleFrontseater


class _FakeBackseater:
    """Minimal query()/publish() stand-in over a plain dict — enough for a capability to
    read its bound inputs and write its outputs, without needing a real Backseater/Knowledge."""
    def __init__(self, knowledge: dict):
        """Wrap the given dict as the Knowledge store."""
        self.knowledge = knowledge

    def query(self, database_name: str, key):
        """Return the Knowledge value for key (only the "knowledge" database is supported)."""
        assert database_name == "knowledge"
        return self.knowledge[key]

    def publish(self, database_name: str, key, value, timestamp=None) -> None:
        """Store value under key in Knowledge (only the "knowledge" database is supported)."""
        assert database_name == "knowledge"
        self.knowledge[key] = value


class TestBicycleFrontseaterCapabilities(unittest.TestCase):
    def setUp(self):
        """Build a BicycleFrontseater wired to a fake dict-backed backseater."""
        self.hardware = BicycleHardware()
        self.frontseater = BicycleFrontseater(hardware=self.hardware)
        self.knowledge = {}
        self.frontseater.backseater = _FakeBackseater(self.knowledge)

    def tearDown(self):
        """Shut down the frontseater's MPC worker process."""
        self.frontseater.shutdown()

    def _activate_move_to(self, target: Location, tolerance: float, with_output=True, name="nav"):
        """Seed target/tolerance in Knowledge and make a single move_to capability request active."""
        self.knowledge["target"] = target
        self.knowledge["tolerance"] = tolerance
        outputs = {"arrived": "arrived"} if with_output else {}
        self.frontseater.set_active_capabilities({
            name: {"capability": "move_to", "inputs": {"target": "target", "tolerance": "tolerance"}, "outputs": outputs}
        })

    def _activate_avoid(self, point: Location, radius: float, with_output=True, name="avoid"):
        """Seed point/radius in Knowledge and make a single avoid capability request active."""
        self.knowledge["point"] = point
        self.knowledge["radius"] = radius
        outputs = {"registered": "registered"} if with_output else {}
        self.frontseater.set_active_capabilities({
            name: {"capability": "avoid", "inputs": {"point": "point", "radius": "radius"}, "outputs": outputs}
        })

    def _activate_stopwatch(self, with_output=True, name="watch"):
        """Make a single stopwatch capability request active."""
        outputs = {"elapsed_time": "elapsed_time"} if with_output else {}
        self.frontseater.set_active_capabilities({name: {"capability": "stopwatch", "inputs": {}, "outputs": outputs}})

    def test_capabilities_advertises_move_to_and_avoid(self):
        """The capability registry includes move_to and avoid."""
        registry = self.frontseater.capabilities()
        self.assertIsNotNone(registry.get("move_to"))
        self.assertIsNotNone(registry.get("avoid"))

    def test_capabilities_advertises_stopwatch(self):
        """The capability registry includes stopwatch."""
        self.assertIsNotNone(self.frontseater.capabilities().get("stopwatch"))

    def test_set_active_capabilities_unknown_capability_raises(self):
        """Activating a capability request whose capability the platform lacks raises ValueError."""
        with self.assertRaises(ValueError):
            self.frontseater.set_active_capabilities({"fly": {"capability": "fly", "inputs": {}, "outputs": {}}})





    #===============# move_to #===============#

    def test_move_to_starts_en_route_while_far_from_target(self):
        """A move_to far from its target reports "en route"."""
        self._activate_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater._step_active_capabilities()
        self.assertEqual(self.frontseater.describe_status()["capabilities"]["nav"], "en route")

    def test_move_to_reports_arrived_false_while_far_from_target(self):
        """A move_to far from its target publishes arrived = False."""
        self._activate_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater._step_active_capabilities()
        self.assertEqual(self.knowledge["arrived"], False)

    def test_move_to_reports_arrived_once_within_tolerance(self):
        """A move_to within tolerance of its target reports "arrived"."""
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self._activate_move_to(Location(0.1, 0.0), 0.5)
        self.frontseater._step_active_capabilities()
        self.assertEqual(self.frontseater.describe_status()["capabilities"]["nav"], "arrived")

    def test_move_to_publishes_arrived_to_its_bound_knowledge_key(self):
        """A move_to within tolerance publishes True to its bound arrived key."""
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self._activate_move_to(Location(0.1, 0.0), 0.5)
        self.frontseater._step_active_capabilities()
        self.assertTrue(self.knowledge["arrived"])

    def test_move_to_reads_a_retargeted_knowledge_key_on_the_next_step(self):
        """A move_to re-queries its target each step, so changing the Knowledge value retargets it."""
        self._activate_move_to(Location(100.0, 0.0), 0.5)
        self.frontseater._step_active_capabilities()
        self.knowledge["target"] = Location(0.0, 0.0)
        self.hardware.state.x, self.hardware.state.y = 0.0, 0.0
        self.frontseater._step_active_capabilities()
        self.assertEqual(self.frontseater.describe_status()["capabilities"]["nav"], "arrived")

    def test_deactivating_a_move_to_clears_its_target(self):
        """Removing the move_to from the active capability requests clears the frontseater's target."""
        self._activate_move_to(Location(5.0, 0.0), 0.5)
        self.frontseater.set_active_capabilities({})
        self.assertIsNone(self.frontseater._active_target)

    def test_compute_controls_is_idle_with_no_active_target(self):
        """With no target, compute_controls() commands zero velocity and steering."""
        controls = self.frontseater.compute_controls(self.hardware.read_state())
        self.assertEqual(controls, {"vel": 0.0, "steer": 0.0})





    #===============# avoid #===============#

    def test_avoid_reports_registered(self):
        """An active avoid reports "registered"."""
        self._activate_avoid(Location(0.0, 0.0), 1.0)
        self.frontseater._step_active_capabilities()
        self.assertEqual(self.frontseater.describe_status()["capabilities"]["avoid"], "registered")

    def test_avoid_publishes_registered_to_its_bound_knowledge_key(self):
        """An active avoid publishes True to its bound registered key."""
        self._activate_avoid(Location(0.0, 0.0), 1.0)
        self.frontseater._step_active_capabilities()
        self.assertTrue(self.knowledge["registered"])





    #===============# stopwatch #===============#

    def test_stopwatch_reports_zero_elapsed_time_right_after_starting(self):
        """A freshly started stopwatch publishes zero elapsed time."""
        self._activate_stopwatch()
        self.frontseater._step_active_capabilities()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 0.0)

    def test_stopwatch_elapsed_time_advances_with_simulation_time(self):
        """Elapsed time tracks the hardware's simulation clock, not wall time."""
        self._activate_stopwatch()
        self.hardware.state.t += 5.0
        self.frontseater._step_active_capabilities()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 5.0)

    def test_stopwatch_publishes_elapsed_time_to_its_bound_knowledge_key(self):
        """The stopwatch publishes its elapsed time to its bound elapsed_time key."""
        self._activate_stopwatch()
        self.hardware.state.t += 3.0
        self.frontseater._step_active_capabilities()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 3.0)

    def test_restarting_the_stopwatch_resets_elapsed_time_to_zero(self):
        """Stopping and restarting a stopwatch of the same name starts it again from zero."""
        self._activate_stopwatch(name="watch")
        self.hardware.state.t += 10.0
        self.frontseater._step_active_capabilities()

        self.frontseater.set_active_capabilities({})   # stop it
        self._activate_stopwatch(name="watch")        # start a fresh instance
        self.frontseater._step_active_capabilities()
        self.assertAlmostEqual(self.knowledge["elapsed_time"], 0.0)





    #===============# sense_pose #===============#

    def test_capabilities_advertises_sense_pose_with_a_pose_output(self):
        """sense_pose is advertised, with one Pose-typed "pose" output and no inputs."""
        capability = self.frontseater.capabilities().get("sense_pose")
        self.assertIsNotNone(capability)
        self.assertEqual(capability.inputs, ())
        self.assertEqual([(spec.name, spec.type) for spec in capability.outputs], [("pose", Pose)])

    def test_sense_pose_publishes_the_sensed_pose_every_step(self):
        """Each step publishes a fresh Pose matching the hardware's (sensed) state."""
        self.frontseater.set_active_capabilities({
            "pose": {"capability": "sense_pose", "inputs": {}, "outputs": {"pose": "ugv1/pose"}}
        })
        self.hardware.state.x, self.hardware.state.y, self.hardware.state.theta = 1.0, 2.0, 0.5
        self.frontseater._step_active_capabilities()
        first_pose = self.knowledge["ugv1/pose"]
        self.assertIsInstance(first_pose, Pose)
        self.assertEqual((first_pose.x, first_pose.y, first_pose.theta), (1.0, 2.0, 0.5))

        self.hardware.state.x = 4.0
        self.frontseater._step_active_capabilities()
        self.assertEqual(self.knowledge["ugv1/pose"].x, 4.0)

    def test_sense_pose_reports_sensing(self):
        """An active sense_pose request's status reads "sensing"."""
        self.frontseater.set_active_capabilities({
            "pose": {"capability": "sense_pose", "inputs": {}, "outputs": {"pose": "ugv1/pose"}}
        })
        self.assertEqual(self.frontseater.describe_status()["capabilities"]["pose"], "sensing")





    #===============# Default Mission Graph #===============#

    def test_default_mission_graph_starts_on_a_startup_node_running_stopwatch_and_pose(self):
        """The default graph starts on a "startup" node running a stopwatch and the pose sensor."""
        graph = self.frontseater.default_mission_graph()
        self.assertEqual(graph["start"], "startup")
        capability_requests = graph["nodes"]["startup"]["capabilities"]
        self.assertEqual({name: request["capability"] for name, request in capability_requests.items()},
                         {"loiter": "stopwatch", "pose": "sense_pose"})

    def test_default_mission_graph_binds_pose_to_a_platform_prefixed_key(self):
        """The default pose request publishes to "<platform_id>/pose", declared as a Pose seeded at the current pose."""
        self.frontseater.platform_id = "ugv1"
        self.hardware.state.x = 3.0
        graph = self.frontseater.default_mission_graph()
        self.assertEqual(graph["nodes"]["startup"]["capabilities"]["pose"]["outputs"], {"pose": "ugv1/pose"})
        declaration = graph["knowledge"]["ugv1/pose"]
        self.assertEqual(declaration["type"], Pose)
        self.assertEqual(declaration["value"].x, 3.0)

    def test_default_mission_graph_declares_its_own_output_knowledge_key(self):
        """The default graph declares its stopwatch's output key as a float in its knowledge section."""
        graph = self.frontseater.default_mission_graph()
        loiter = graph["nodes"]["startup"]["capabilities"]["loiter"]
        output_key = loiter["outputs"]["elapsed_time"]
        self.assertIn(output_key, graph["knowledge"])
        self.assertEqual(graph["knowledge"][output_key]["type"], float)

    def test_default_mission_graph_has_no_edges(self):
        """The default graph has no edges, so it loiters indefinitely."""
        graph = self.frontseater.default_mission_graph()
        self.assertEqual(graph["edges"], {})


if __name__ == "__main__":
    unittest.main()
