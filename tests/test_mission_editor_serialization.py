"""Tests for mtofr.mission_editor.serialization: save/load a mission graph to/from
JSON, including the type-name round-trip for a graph's "knowledge" section (which
stores real `type` objects) and Location's custom encode/decode."""
import tempfile
import unittest
from pathlib import Path

from mtofr.database import Location
from mtofr.mission_editor.serialization import save_mission_graph, load_mission_graph


class TestMissionGraphSerialization(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.file_path = Path(self._temp_dir.name) / "graph.json"

    def test_round_trips_a_graph_with_plain_and_location_knowledge_types(self):
        graph = {
            "knowledge": {
                "arrived": {"type": bool, "value": False},
                "tolerance": {"type": float, "value": 0.5},
                "count": {"type": int, "value": 3},
                "label": {"type": str, "value": "hello"},
                "target": {"type": Location, "value": Location(1.5, -2.5)},
            },
            "nodes": {"n1": {"primitives": {
                "nav": {"capability": "move_to", "inputs": {"target": "target"}, "outputs": {"arrived": "arrived"}},
            }}},
            "edges": {"n1": [{"condition": ["arrived", "==", True], "to": "n1"}]},
            "start": "n1",
        }

        save_mission_graph(graph, self.file_path)
        loaded = load_mission_graph(self.file_path)

        self.assertEqual(loaded["knowledge"]["arrived"], {"type": bool, "value": False})
        self.assertEqual(loaded["knowledge"]["tolerance"], {"type": float, "value": 0.5})
        self.assertEqual(loaded["knowledge"]["count"], {"type": int, "value": 3})
        self.assertEqual(loaded["knowledge"]["label"], {"type": str, "value": "hello"})
        self.assertEqual(loaded["knowledge"]["target"]["type"], Location)
        self.assertEqual(loaded["knowledge"]["target"]["value"].x, 1.5)
        self.assertEqual(loaded["knowledge"]["target"]["value"].y, -2.5)
        self.assertEqual(loaded["nodes"], graph["nodes"])
        self.assertEqual(loaded["edges"], graph["edges"])
        self.assertEqual(loaded["start"], "n1")


if __name__ == "__main__":
    unittest.main()