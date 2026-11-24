"""Tests confirming the mission editor's push path -- Backseater.write_mission() --
behaves correctly for the interface platform's privilege level (0, outranking the
default 1) set up in the VILLAGE_DEFAULT scenario: it can push a
mission graph onto an ordinary platform, an ordinary platform cannot push onto it
without sufficient privilege, and a structurally invalid graph is rejected before
ever reaching the target platform's Mission database. No Tk/window involved --
this exercises exactly what MissionEditorWindow._on_push() calls."""
import unittest

from mtofr.core.capability import Capability, CapabilityRegistry
from mtofr.database import KnowledgeDatabase
from mtofr.mission.validation import MissionStructuralError
from mtofr.platform.backseater import Backseater
from mtofr.platform.frontseater import Frontseater


class _FakeHardware:
    """Minimal stand-in for Hardware, only used as the platform_id cascade target."""
    platform_id: str | None = None


class _Idle(Capability):
    """A capability that does nothing."""
    ipl_type = "idle"
    description = "Does nothing."


class _FakeFrontseater(Frontseater):
    """Fake Frontseater advertising only the "idle" capability."""
    def __init__(self):
        """Advertise the one "idle" capability."""
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([_Idle])

    def compute_controls(self, state) -> dict:
        """Command nothing."""
        return {}

    def capabilities(self) -> CapabilityRegistry:
        """Return the one-capability ("idle") registry."""
        return self._registry

    def set_active_capabilities(self, capability_requests: dict) -> None:
        """Ignore capability request changes; nothing runs."""

    def describe_status(self) -> dict:
        """Report a fixed idle status."""
        return {"overall": "idle", "capabilities": {}}


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {"n1": {"capabilities": {}}}, "edges": {}, "start": "n1"}


def _make_backseater(platform_id: str, privilege_level: int) -> Backseater:
    """Build a Backseater over a fake Frontseater at the given privilege level."""
    return Backseater(frontseater=_FakeFrontseater(), knowledge_database=KnowledgeDatabase(),
                       mission_graph=dict(_EMPTY_GRAPH), platform_id=platform_id, privilege_level=privilege_level)


class TestMissionEditorPushPrivilege(unittest.TestCase):
    def setUp(self):
        """Build a privilege-0 interface and a privilege-1 ugv1 that already know each other's PlatformRecord."""
        self.interface =_make_backseater("interface", privilege_level=0)
        self.ugv1 = _make_backseater("ugv1", privilege_level=1)
        # The two platforms must know of each other's PlatformRecord for the
        # privilege gate to resolve -- normally seeded by mesh sync, done directly here.
        self.ugv1.platform_database.declare("interface", self.interface.platform_database.get("interface"))
        self.interface.platform_database.declare("ugv1", self.ugv1.platform_database.get("ugv1"))

    def test_higher_privilege_platform_can_push_a_mission_onto_a_lower_privilege_one(self):
        """The interface's push onto ugv1 stores the graph in ugv1's Mission entry."""
        graph = {"knowledge": {}, "nodes": {"n2": {"capabilities": {}}}, "edges": {}, "start": "n2"}
        self.ugv1.write_mission(graph, writer_platform_id="interface")
        self.assertIs(self.ugv1.mission_database.get("ugv1"), graph)

    def test_lower_privilege_platform_cannot_push_onto_a_higher_privilege_one(self):
        """ugv1 pushing onto the interface raises PermissionError."""
        graph = {"knowledge": {}, "nodes": {"n2": {"capabilities": {}}}, "edges": {}, "start": "n2"}
        with self.assertRaises(PermissionError):
            self.interface.write_mission(graph, writer_platform_id="ugv1")

    def test_structurally_invalid_graph_is_rejected(self):
        """A graph whose condition uses an undeclared key raises MissionStructuralError."""
        bad_graph = {
            "knowledge": {},   # references "arrived" below without declaring it
            "nodes": {"n2": {"capabilities": {}}},
            "edges": {"n2": [{"condition": ["arrived", "==", True], "to": "n2"}]},
            "start": "n2",
        }
        with self.assertRaises(MissionStructuralError):
            self.ugv1.write_mission(bad_graph, writer_platform_id="interface")

    def test_graph_the_target_cannot_bind_is_rejected_and_not_stored(self):
        """A capability request naming a capability the target lacks is rejected at write time, leaving the stored graph as is."""
        before = self.ugv1.mission_database.all().get("ugv1")
        graph = {"knowledge": {}, "edges": {}, "start": "n2",
                 "nodes": {"n2": {"capabilities": {"go": {"capability": "move_to", "inputs": {}, "outputs": {}}}}}}
        with self.assertRaisesRegex(MissionStructuralError, "move_to.*does not exist"):
            self.ugv1.write_mission(graph, writer_platform_id="interface")
        self.assertIs(self.ugv1.mission_database.all().get("ugv1"), before)

    def test_graph_using_a_capability_the_target_has_is_accepted(self):
        """A capability request using a capability the target has is accepted and stored."""
        graph = {"knowledge": {}, "edges": {}, "start": "n2",
                 "nodes": {"n2": {"capabilities": {"wait": {"capability": "idle", "inputs": {}, "outputs": {}}}}}}
        self.ugv1.write_mission(graph, writer_platform_id="interface")
        self.assertIs(self.ugv1.mission_database.get("ugv1"), graph)


if __name__ == "__main__":
    unittest.main()