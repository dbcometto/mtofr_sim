"""Tests confirming the mission editor's push path -- Backseater.write_mission() --
behaves correctly for the interface platform's privilege level (0, outranking the
default 1) set up in missions.py's VILLAGE_DEFAULT mission set: it can push a
mission graph onto an ordinary platform, an ordinary platform cannot push onto it
without sufficient privilege, and a structurally invalid graph is rejected before
ever reaching the target platform's Mission database. No Tk/window involved --
this exercises exactly what MissionEditorWindow._on_push() calls."""
import unittest

from mtofr.backseater.backseater import Backseater
from mtofr.capability.capability import Capability, CapabilityRegistry
from mtofr.database import KnowledgeDatabase, MissionStructuralError
from mtofr.world.base import Frontseater


class _FakeHardware:
    platform_id: str | None = None


class _FakeFrontseater(Frontseater):
    def __init__(self):
        self.hardware = _FakeHardware()
        self._registry = CapabilityRegistry([Capability(ipl_type="idle", description="Does nothing.")])

    def compute_controls(self, state) -> dict:
        return {}

    def capabilities(self) -> CapabilityRegistry:
        return self._registry

    def set_active_primitives(self, primitives: dict) -> None:
        pass

    def describe_status(self) -> dict:
        return {"overall": "idle", "primitives": {}}


_EMPTY_GRAPH = {"knowledge": {}, "nodes": {"n1": {"primitives": {}}}, "edges": {}, "start": "n1"}


def _make_backseater(platform_id: str, privilege_level: int) -> Backseater:
    return Backseater(frontseater=_FakeFrontseater(), knowledge_database=KnowledgeDatabase(),
                       mission_graph=dict(_EMPTY_GRAPH), platform_id=platform_id, privilege_level=privilege_level)


class TestMissionEditorPushPrivilege(unittest.TestCase):
    def setUp(self):
        self.interface = _make_backseater("interface", privilege_level=0)
        self.ugv1 = _make_backseater("ugv1", privilege_level=1)
        # The two platforms must know of each other's PlatformRecord for the
        # privilege gate to resolve -- normally seeded by mesh sync, done directly here.
        self.ugv1.platform_database.declare("interface", self.interface.platform_database.get("interface"))
        self.interface.platform_database.declare("ugv1", self.ugv1.platform_database.get("ugv1"))

    def test_higher_privilege_platform_can_push_a_mission_onto_a_lower_privilege_one(self):
        graph = {"knowledge": {}, "nodes": {"n2": {"primitives": {}}}, "edges": {}, "start": "n2"}
        self.ugv1.write_mission(graph, writer_platform_id="interface")
        self.assertIs(self.ugv1.mission_database.get("ugv1"), graph)

    def test_lower_privilege_platform_cannot_push_onto_a_higher_privilege_one(self):
        graph = {"knowledge": {}, "nodes": {"n2": {"primitives": {}}}, "edges": {}, "start": "n2"}
        with self.assertRaises(PermissionError):
            self.interface.write_mission(graph, writer_platform_id="ugv1")

    def test_structurally_invalid_graph_is_rejected(self):
        bad_graph = {
            "knowledge": {},   # references "arrived" below without declaring it
            "nodes": {"n2": {"primitives": {}}},
            "edges": {"n2": [{"condition": ["arrived", "==", True], "to": "n2"}]},
            "start": "n2",
        }
        with self.assertRaises(MissionStructuralError):
            self.ugv1.write_mission(bad_graph, writer_platform_id="interface")


if __name__ == "__main__":
    unittest.main()