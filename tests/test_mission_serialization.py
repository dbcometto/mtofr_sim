"""Tests for mtofr.mission.serialization: save/load a mission graph to/from
JSON (a file, or a JSON-native dict), including the type-name round-trip for a graph's
"knowledge" section (which stores real `type` objects) and the generic KnowledgeEntry
(Location, Pose) encode/decode."""
import json
import tempfile
import unittest
from pathlib import Path

from mtofr.database import Location, Pose, Trajectory
from mtofr.mission.serialization import (
    decode_mission_graph,
    encode_mission_graph,
    load_mission_graph,
    save_mission_graph,
)


class TestMissionGraphSerialization(unittest.TestCase):
    def setUp(self):
        """Create a temporary directory (cleaned up after the test) and a graph file path inside it."""
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.file_path = Path(self._temp_dir.name) / "graph.json"

    def test_round_trips_a_graph_with_plain_and_location_knowledge_types(self):
        """Saving then loading preserves plain and Location knowledge types/values, nodes, edges, and start."""
        graph = {
            "knowledge": {
                "arrived": {"type": bool, "value": False},
                "tolerance": {"type": float, "value": 0.5},
                "count": {"type": int, "value": 3},
                "label": {"type": str, "value": "hello"},
                "target": {"type": Location, "value": Location(1.5, -2.5)},
            },
            "nodes": {"n1": {"capabilities": {
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


class TestMissionGraphDictEncoding(unittest.TestCase):
    def test_encoded_graph_is_json_native_and_round_trips_a_pose(self):
        """encode_mission_graph() yields JSON-serializable data that decode_mission_graph() turns back into a Pose."""
        graph = {
            "knowledge": {"ugv1/pose": {"type": Pose, "value": Pose(1.0, 2.0, 0.5)}},
            "nodes": {"n1": {"capabilities": {}}},
            "edges": {},
            "start": "n1",
        }
        encoded = encode_mission_graph(graph)
        self.assertEqual(encoded["knowledge"]["ugv1/pose"], {"type": "Pose", "value": {"x": 1.0, "y": 2.0, "theta": 0.5}})

        decoded = decode_mission_graph(json.loads(json.dumps(encoded)))
        pose = decoded["knowledge"]["ugv1/pose"]["value"]
        self.assertEqual(decoded["knowledge"]["ugv1/pose"]["type"], Pose)
        self.assertEqual((pose.x, pose.y, pose.theta), (1.0, 2.0, 0.5))

    def test_a_trajectory_round_trips_as_its_text(self):
        """A Trajectory encodes as its one text field and decodes back to the same waypoints."""
        graph = {
            "knowledge": {"ugv1/route": {"type": Trajectory, "value": Trajectory("[[0, 0], [5, 5]]")}},
            "nodes": {"n1": {"capabilities": {}}},
            "edges": {},
            "start": "n1",
        }
        encoded = encode_mission_graph(graph)
        self.assertEqual(encoded["knowledge"]["ugv1/route"], {"type": "Trajectory", "value": {"waypoints": "[[0, 0], [5, 5]]"}})
        decoded = decode_mission_graph(json.loads(json.dumps(encoded)))
        self.assertEqual(decoded["knowledge"]["ugv1/route"]["value"].points, ((0.0, 0.0), (5.0, 5.0)))

    def test_a_name_round_trips_and_a_missing_one_stays_missing(self):
        """The optional mission name survives encode/decode; a graph without one gets none."""
        graph = {"knowledge": {}, "nodes": {"n1": {"capabilities": {}}}, "edges": {}, "start": "n1"}
        self.assertNotIn("name", decode_mission_graph(encode_mission_graph(graph)))
        encoded = json.loads(json.dumps(encode_mission_graph({**graph, "name": "patrol"})))
        self.assertEqual(decode_mission_graph(encoded)["name"], "patrol")

    def test_other_top_level_sections_are_ignored(self):
        """A web-editor file's "editor" section loads fine through the plain loader, and isn't in the graph."""
        encoded = {"knowledge": {}, "nodes": {"n1": {"capabilities": {}}}, "edges": {}, "start": "n1",
                   "editor": {"layout": {"n1": [0, 0]}}}
        self.assertNotIn("editor", decode_mission_graph(encoded))

    def test_decoding_an_unknown_type_name_raises_value_error(self):
        """An unregistered knowledge type name is a ValueError naming the known types, not a bare KeyError."""
        encoded = {"knowledge": {"k": {"type": "Banana", "value": 1}}, "nodes": {}, "edges": {}, "start": None}
        with self.assertRaises(ValueError):
            decode_mission_graph(encoded)


if __name__ == "__main__":
    unittest.main()