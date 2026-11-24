"""What a mission is and how it is checked: the graph's shape (graph.py), its edge
conditions (condition.py), its validation (validation.py), and its JSON form
(serialization.py).  Builds on core (capabilities) and database (knowledge types);
never imports platform, environments, or scenarios."""
from .graph import MissionGraph, Node, CapabilityRequest, Edge, KnowledgeDeclaration
from .condition import parse_condition, ConditionSyntaxError
from .validation import (
    MissionStructuralError,
    verify_mission_structure,
    declared_types,
    find_capability_problems,
    find_binding_problems,
    find_condition_problems,
)
from .serialization import save_mission_graph, load_mission_graph
