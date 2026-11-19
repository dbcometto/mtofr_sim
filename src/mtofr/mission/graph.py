"""Defines the shape of a mission graph: the one place to read what a mission is.

A mission graph is a plain dict (so it copies, diffs, and serializes freely); the
TypedDicts below only document and type-hint that shape, they never wrap it.

    {"knowledge": {key: {"type": type, "value": value}, ...},
     "nodes": {node_id: {"capabilities": {name: {"capability": ipl_type,
                                                 "inputs": {field_name: key, ...},
                                                 "outputs": {field_name: key, ...}}}}},
     "edges": {node_id: [{"condition": [token, ...], "to": next_node_id}, ...]},
     "start": node_id}

- "knowledge": every Knowledge key the graph touches, with its locked type and the
  default value it is reset to whenever this graph becomes a platform's mission.
- "nodes": one node is active at a time; all of its capability requests run
  concurrently.  A capability request names a capability (its `ipl_type`) and binds that
  capability's fields to Knowledge keys, never to literals.
- "edges": per source node, checked in order; the first edge whose condition (a
  pre-tokenized boolean expression over Knowledge keys, see condition.py) is true is
  taken.  Capability request status never drives a transition; capabilities write
  Knowledge.
- "start": the node activated when the graph becomes a platform's mission.

Every key referenced by a condition or a binding must be declared in "knowledge"
(validation.verify_mission_structure), and every capability request must be bindable by the
platform it runs on (validation.find_binding_problems).
"""
from typing import TypedDict


#========================================#
# Mission Graph Shape
#========================================#

# NOTE: functional syntax, since "type" is a key of the format and would otherwise
# shadow the built-in inside a class body.
KnowledgeDeclaration = TypedDict("KnowledgeDeclaration", {"type": type, "value": object})


class CapabilityRequest(TypedDict, total=False):
    """One capability request inside a node: "capability" is always present, while
    "inputs"/"outputs" (field_name -> Knowledge key) may be omitted when empty."""
    capability: str
    inputs: dict[str, str]
    outputs: dict[str, str]


class Node(TypedDict):
    """One mission state: the capability requests that run together while it is active."""
    capabilities: dict[str, CapabilityRequest]


class Edge(TypedDict):
    """One transition out of a node, taken when `condition` evaluates true."""
    condition: list
    to: str


class MissionGraph(TypedDict):
    """A whole mission; see this module's docstring for the semantics."""
    knowledge: dict[str, KnowledgeDeclaration]
    nodes: dict[str, Node]
    edges: dict[str, list[Edge]]
    start: str | None
