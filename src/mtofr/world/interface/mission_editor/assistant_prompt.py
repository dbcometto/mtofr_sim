"""Defines the assistant's system prompt and the per-turn draft-state block injected into each user message."""
from mtofr.world.interface.mission_editor.serialization import KNOWLEDGE_TYPE_NAMES

#==========# System prompt #==========#
# Written for a 4B model: short imperative rules, one worked example, no fixed reply format (a MISSION:/PLAN:
# header made the model emit "MISSION" as a tool call). The Ranger Handbook's eight Troop Leading Procedures are
# collapsed to the five that do work for an editing assistant with no subordinate units to brief: receive the
# mission; tentative plan (the warning order folds into it as one announcing sentence); start movement and
# reconnoiter (execute, reading each result); complete the plan (verify); issue the order (summary). "Supervise"
# survives as the follow-up-fix sentence.

SYSTEM_PROMPT = """
You edit a robot mission graph for a user by calling tools. Work like a leader running Troop Leading Procedures.
You only draft the plan.  The user must verify and approve it.

THE MESSAGE
- SITUATION: includes the WORLD (map, positions, live state) the platform's Capabilities, and the current draft graph.
- MISSION: the user's request, last.

THE GRAPH
- Node: exactly one is active at a time; the start node is active first.
- Primitive: a capability (move_to, ...) that runs while its node is active.
- Edge: leaves a node for a different node when its condition becomes true. A task that is just "do X" needs NO edges. Add an edge only to go to another node. When a task finishes the mission simply stays in its node, so never add a "done" or "goal reached" node.
- Knowledge key: a named, typed value. Primitives and conditions share data only through keys. A place is ONE Location key, never two floats.

PLANNING CONSIDERATIONS
- Think about an operations order (5 considerations: Situation, Mission, Execution, Admin/Logistics, Command/Signal)
- Within execution, the correspondence is
    NODE <-> PHASE
    PRIMITIVE <-> KEY TASK
    EDGE <-> CONDITION FOR LEAVING THE PHASE
- Each group of concurrent capabilities needs one phase
- Each edge corresponds with a DECISION to switch active capabilities
- Only add a new node and corresponding edges if necessary

RULES
0. Ask questions when you do not know, but do not over-rely on the user.  You are filling the role of a leader.
1. Inputs/outputs map capability field names to knowledge KEY NAMES, not to literals. 
    e.g. for a tolerance of 0.5: declare key "tolerance" (float, 0.5), then inputs={"tolerance": "tolerance"}.
2. Declare every key before binding it, outputs included (arrived: bool, false).
3. Literals appear only inside edge conditions, e.g. ["arrived", "==", true].
4. Use only the listed capabilities and their exact field names.
5. Make the smallest change. Reuse existing nodes (including the start node) and keys. Leave unrelated primitives alone. Delete nothing you were not asked to.
6. Never invent coordinates; take them from WORLD (corners, regions, positions). If the request cannot be answered from WORLD, ask one short question and edit nothing.
7. A question (not a change request) gets 1-3 plain sentences and no tool calls.
8. Never describe a step without doing it. If you say what you will do next, the tool call must be in that same message. A message with no tool call ends your turn, so send one only when every call is made and you are giving the final summary or asking a necessary question.

TROOP LEADING PROCEDURES (complete steps in order to be successful)
1. Receive the mission: from the request, the draft and WORLD, settle the task and the end state.  Restate the mission to the user.
2. Make a tentative plan:  Describe the concept of the operation in terms of phases, tasks, and transitions.  Consider the current situation.
3. Initiate Movement/Conduct Recon: Make a list of any NECESSARY RFIs (Request for Information) and ask the user any NECESSARY questions.
4. Complete the Plan: Write 1-3 plain sentences saying what changes you will make to the current graph. the graph.  
    Then, make the graph.  Order of work is keys > nodes > primitives > edges > assign start node.
    Make ALL of the plan's tool calls together in ONE message, in that order. Every extra message is a slow model call, so do not send them one at a time.
    Then, confirm every bound key is declared, every edge target exists, and the start node is right.
5. Issue the order: 1-3 sentences saying what the graph now does, what you assumed, and that it is in the draft, not pushed.
6. Supervise/Refine: If the user reports a problem, fix it with the smallest edit_ or remove_ tool call and report again.


STYLE: 
- Plain text only, no markdown, do not repeat these rules. The only tools are the ones listed.

EXAMPLE (numbers invented for illustration; real ones come from WORLD)

User | Send UGV 1 to Point Alpha at (40,0).
Assistant | I will get right on this planning task.

Mission: UGV 1 needs to move to Point Alpha.  

Tentative Plan: UGV 1 will conduct the movement with one movement phase, and no phase transitions are needed.

Conduct Recon: I have no RFIs, so I'll implement the changes.

Implementation Plan: I am going to rename the starting node to "movement".  I'll declare the goal (40, 0), a tolerance, and an arrived flag, then add move_to to the start node. When it arrives, the UGV will remain in that node.  I'll call those tools now.

add_knowledge_key(key="goal", type="Location", value={"x": 40, "y": 0})
add_knowledge_key(key="tolerance", type="float", value=1.0)
add_knowledge_key(key="arrived", type="bool", value=false)
add_primitive(node_id="start", primitive_name="go", capability="move_to", inputs={"target": "goal", "tolerance": "tolerance"}, outputs={"arrived": "arrived"})

I renamed the start node to match the planned movement phase, and gave the node a movement to Point Alpha at (40,0) with a tolerance of 1.0 meters.  The draft changes are in for approval.  Let me know if I need to make any further edits.
"""


#==========# Per-turn state block #==========#

def describe_world(ground_map, platform_state) -> str:
    """The coordinate frame, map extent/corners/regions/terrain, and the target platform's position, as text."""
    lines = ["Units are meters. +x is right (east), +y is up (north). The origin (0, 0) is the center of the map."]
    if ground_map is None:
        lines.append("There is no map: the plane is unbounded, with no corners and no terrain.")
    else:
        half_width, half_height = ground_map.width_meters / 2, ground_map.height_meters / 2
        lines.append(f"Map '{ground_map.name}': x from {-half_width:g} to {half_width:g}, y from {-half_height:g} to {half_height:g}.")
        lines.append(f"Corners: top-left ({-half_width:g}, {half_height:g}), top-right ({half_width:g}, {half_height:g}), "
                     f"bottom-left ({-half_width:g}, {-half_height:g}), bottom-right ({half_width:g}, {-half_height:g}).")
        width_pixels = ground_map.width_meters / ground_map.meters_per_pixel
        height_pixels = ground_map.height_meters / ground_map.meters_per_pixel
        for region in ground_map.regions_lookup.values():   # region centers are stored in top-left-origin pixels
            x = (region.center_x - width_pixels / 2) * ground_map.meters_per_pixel
            y = (height_pixels / 2 - region.center_y) * ground_map.meters_per_pixel
            lines.append(f"Region '{region.name}': center ({x:.0f}, {y:.0f}).")
        for terrain in ground_map.traversability_lookup.values():
            effect = "blocked, never route through" if terrain.blocking else f"speed x{terrain.speed_multiplier:g}"
            lines.append(f"Terrain '{terrain.name}': {effect}.")
    if platform_state is not None:
        lines.append(f"Target platform is currently at ({platform_state.x:.1f}, {platform_state.y:.1f}).")
    return "\n".join(lines)


def _graph_signature(graph: dict) -> tuple:
    """Everything that makes two mission graphs the same, comparable even though Location values have no __eq__."""
    knowledge = {key: (declaration["type"].__name__, repr(declaration["value"]))
                 for key, declaration in graph.get("knowledge", {}).items()}
    return knowledge, graph.get("nodes"), graph.get("edges"), graph.get("start")


def describe_live(backseater, draft: dict = None) -> str:
    """The running platform's active node, framed as information only. It is the last PUSHED graph, so it routinely
    differs from the draft; saying so outright stopped the model from reading the difference as an inconsistency to fix.
    Live Knowledge values are left out on purpose: they are often left over from earlier missions and confused it."""
    if backseater is None:
        return ""
    if draft is None:
        comparison = ""
    elif _graph_signature(draft) == _graph_signature(backseater.mission_graph):
        comparison = " The draft is identical to the platform's graph."
    else:
        comparison = " The draft has unpushed changes, so it differs from the platform's graph. That is expected; keep editing the draft."
    return (f"Platform right now (information only, NOT what you edit): it is running the last pushed graph, currently in node "
            f"'{backseater.status()['active_node_id']}'.{comparison} Never try to make the draft match it.")


def _format_fields(specs) -> str:
    """'name (type: meaning)' for each ParamSpec, or 'none'."""
    return ", ".join(f"{spec.name} ({spec.type.__name__}: {spec.description})" for spec in specs) or "none"


def render_state(draft: dict, capability_registry, target_platform_id: str, world_description: str = "") -> str:
    """The SITUATION as compact plain text for the model: target platform, WORLD, its capabilities, and the current draft graph."""
    lines = ["SITUATION", f"Target platform (the one being edited): {target_platform_id}", "WORLD:",
             world_description or "(no world information)", "Capabilities:"]
    capabilities = capability_registry.all() if capability_registry is not None else {}
    for ipl_type, capability in capabilities.items():
        lines.append(f"- {ipl_type}: {capability.description} "
                     f"inputs: {_format_fields(capability.inputs)}; outputs: {_format_fields(capability.outputs)}")
    if not capabilities:
        lines.append("- (unknown)")

    lines.append("Current draft graph:")
    lines.append("Knowledge keys:")
    for key, declaration in draft["knowledge"].items():
        type_name = KNOWLEDGE_TYPE_NAMES.get(declaration["type"], declaration["type"].__name__)
        lines.append(f"- {key}: {type_name} = {declaration['value']!r}")
    if not draft["knowledge"]:
        lines.append("- (none)")

    lines.append(f"Nodes (start node: {draft.get('start')}):")
    for node_id, node in draft["nodes"].items():
        lines.append(f"- {node_id}")
        for name, primitive in node["primitives"].items():
            lines.append(f"    primitive {name}: {primitive['capability']} "
                         f"inputs={primitive.get('inputs', {})} outputs={primitive.get('outputs', {})}")

    lines.append("Edges:")
    edge_lines = [f"- {source_id} edge {index}: -> {edge['to']} when {edge['condition']}"
                  for source_id, edge_list in draft["edges"].items() for index, edge in enumerate(edge_list)]
    lines.extend(edge_lines or ["- (none)"])
    return "\n".join(lines)


def compose_user_message(user_text: str, draft: dict, capability_registry, target_platform_id: str,
                         world_description: str = "") -> str:
    """The text sent to the model for one turn: SITUATION first, then the MISSION (the user's request) last."""
    return f"{render_state(draft, capability_registry, target_platform_id, world_description)}\n\nMISSION: {user_text}"
