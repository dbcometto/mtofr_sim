"use strict";
/* Graph panel (web/panels/graph.py): a graphical editor of the window's draft, plus a
   read-only Live view of the Target's mission (the default mode).

   Layout: [Knowledge panel | canvas | inspector], each side panel collapsible by its arrow.

   Gestures (Draft mode):
   - click selects (Shift/Ctrl-click toggles); drag on blank space box-selects (Shift adds);
   - drag a node to move the whole selection; middle-drag or Space+drag pans; the wheel zooms;
   - drag from a node's port (the dot on its right edge) to another node to draw an edge (the
     node it would attach to lights up), or to blank space to draw it to a new node there;
     drag a selected edge's end handle onto another node to re-route it;
   - double-click blank space to add a node, or a node/edge (or its pencil button) to edit it
     in a popover; the docked inspector always shows the selection;
   - right-click for a context menu; Delete, Ctrl+A, Escape, F (fit), Ctrl+Z/Y.
   Node positions are the draft's editor data (never the mission graph), so moves are undoable. */

mtofr.registerPanel("graph", (element, api) => {
  const ui = mtofr.ui;


  //==========// Config //==========//

  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const PIXELS_PER_UNIT = 150;   // canvas px per layout unit, at zoom 1
  const NODE_WIDTH = 124;        // px
  const NODE_HEIGHT = 46;        // px
  const NODE_CORNER_RADIUS = 9;  // px
  const PORT_RADIUS = 7;         // px
  const HANDLE_RADIUS = 7;       // px
  const EDIT_BUTTON_SIZE = 20;   // px
  const CURVE_STEP = 36;         // px of bend per extra edge between the same two nodes
  const LOOP_HEIGHT = 46;        // px a self-loop rises above its node
  const LOOP_STEP = 22;          // px higher for each further self-loop on the same node
  const HALO_END_TRIM = 22;      // px at each end of an edge where its halo is left off (so it never nicks a shared node's arrowheads)
  const BADGE_WIDTH = 26;        // px
  const BADGE_HEIGHT = 15;       // px
  const BADGE_POSITION = 0.22;   // fraction along an edge where its priority badge sits
  const WARNING_OFFSET = 4;      // px inset of a node's warning mark from its corner
  const LABEL_MAX_LENGTH = 28;   // characters, before a label is truncated with an ellipsis
  const ZOOM_FACTOR = 1.1;       // per wheel notch
  const MIN_ZOOM = 0.2;
  const MAX_ZOOM = 4;
  const MAX_FIT_ZOOM = 1.5;
  const FIT_MARGIN = 60;         // px kept around the graph by Fit view
  const DRAG_THRESHOLD = 4;      // screen px a press must travel before it counts as a drag
  const POPOVER_GAP = 12;        // px between a popover and what it points at
  const AUTO_NODE_PREFIX = "node_";
  const NEW_KEY_OPTION = "\u0000new";   // the "+ New key..." choice in a binding select (never a real key)
  const KNOWLEDGE_STORAGE_KEY = "mtofr.graphKnowledgeShown";
  const INSPECTOR_STORAGE_KEY = "mtofr.graphInspectorShown";
  const SYNC_AGE_DECIMALS = 1;
  const PRIMARY_BUTTON = 0;
  const MIDDLE_BUTTON = 1;
  const WARNING = "⚠";   // ⚠


  //==========// State //==========//

  let panelState = null;   // this panel's latest state: the editor's fields, draft_layout, live
  let mode = "live";       // "live" (the default view of the Target) or "draft"
  let showLabels = false;
  let positions = {};      // node id -> {x, y}: canvas px (y down) at zoom 1, from the layout
  const selection = {nodes: new Set(), edges: new Set()};   // node ids; edge keys "source#index"
  const view = {x: 0, y: 0, zoom: 1};   // screen = canvas * zoom + (x, y)
  let drag = null;         // the gesture in progress (see onPointerDown), or null
  let pendingSync = false; // a state update arrived mid-drag; apply it when the drag ends
  let spaceHeld = false;
  let fittedNodeIds = null;   // the node ids the view was last fitted to; a new graph re-fits
  let popover = null;      // {element, host} while a popover is open
  let renderedSignature = null;   // what the canvas last drew, so an unchanged poll never redraws it

  const tools = mtofr.draftTools(api, () => panelState);
  const editable = () => mode === "draft";
  const graph = () => (editable() ? panelState.draft : panelState.live?.graph) || null;
  const problems = () => (editable() ? panelState.problems : {requests: {}, edges: {}, keys: {}, graph: []});
  const ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"};
  const TEEN_MIN = 11;   // 11th-13th break the st/nd/rd rule
  const TEEN_MAX = 13;
  const byKey = ([first], [second]) => first.localeCompare(second);

  /** "1 node" / "2 nodes" (irregular plurals passed explicitly). */
  const plural = (count, word, pluralWord = `${word}s`) => `${count} ${count === 1 ? word : pluralWord}`;

  /** 1 -> "1st", 2 -> "2nd", 3 -> "3rd", 4 -> "4th", 11 -> "11th", 21 -> "21st". */
  function ordinal(number) {
    const lastTwo = number % 100;
    const suffix = lastTwo >= TEEN_MIN && lastTwo <= TEEN_MAX ? "th" : ORDINAL_SUFFIXES[number % 10] ?? "th";
    return `${number}${suffix}`;
  }


  //==========// Geometry //==========//

  const clampZoom = (zoom) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
  const truncate = (text) => (text.length > LABEL_MAX_LENGTH ? `${text.slice(0, LABEL_MAX_LENGTH - 1)}…` : text);
  const toLayoutUnits = ({x, y}) => [x / PIXELS_PER_UNIT, -y / PIXELS_PER_UNIT];
  const fromLayoutUnits = ([x, y]) => ({x: x * PIXELS_PER_UNIT, y: -y * PIXELS_PER_UNIT});

  /** "source#index" -> {source, index} (ids may contain "#"; the index never does). */
  function parseEdgeKey(key) {
    const split = key.lastIndexOf("#");
    return {source: key.slice(0, split), index: Number(key.slice(split + 1))};
  }

  /** 0, 1, 2, 3, 4, ... -> 0, +1, -1, +2, -2, ...: the first edge between two nodes is straight, later ones bow outward alternately. */
  const curvature = (groupIndex) => (groupIndex === 0 ? 0 : (groupIndex % 2 === 1 ? 1 : -1) * Math.ceil(groupIndex / 2));

  /** Where the ray from a node's center toward `toward` leaves its box. */
  function boxBoundary(center, toward) {
    const dx = toward.x - center.x;
    const dy = toward.y - center.y;
    if (dx === 0 && dy === 0) {
      return center;
    }
    const scale = Math.min(dx === 0 ? Infinity : (NODE_WIDTH / 2) / Math.abs(dx),
                           dy === 0 ? Infinity : (NODE_HEIGHT / 2) / Math.abs(dy));
    return {x: center.x + dx * scale, y: center.y + dy * scale};
  }

  const quadraticPoint = (start, control, end, t) => ({
    x: (1 - t) ** 2 * start.x + 2 * (1 - t) * t * control.x + t ** 2 * end.x,
    y: (1 - t) ** 2 * start.y + 2 * (1 - t) * t * control.y + t ** 2 * end.y,
  });
  const cubicPoint = (start, first, second, end, t) => ({
    x: (1 - t) ** 3 * start.x + 3 * (1 - t) ** 2 * t * first.x + 3 * (1 - t) * t ** 2 * second.x + t ** 3 * end.x,
    y: (1 - t) ** 3 * start.y + 3 * (1 - t) ** 2 * t * first.y + 3 * (1 - t) * t ** 2 * second.y + t ** 3 * end.y,
  });

  /** One edge between two different nodes, bowed by its index among the edges joining that pair. */
  function curveShape(source, target, canonical, groupIndex) {
    // Bend relative to one fixed direction per pair, so an edge and its reverse bow apart
    const [from, to] = canonical ? [source, target] : [target, source];
    const length = Math.hypot(to.x - from.x, to.y - from.y) || 1;
    const normal = {x: -(to.y - from.y) / length, y: (to.x - from.x) / length};
    const bend = curvature(groupIndex) * CURVE_STEP;
    const control = {x: (source.x + target.x) / 2 + normal.x * bend, y: (source.y + target.y) / 2 + normal.y * bend};
    const start = boxBoundary(source, control);
    const end = boxBoundary(target, control);
    return {
      path: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
      start, end, at: (t) => quadraticPoint(start, control, end, t),
    };
  }

  /** A node's edge to itself: an arc over its top, higher for each further loop. */
  function loopShape(center, loopIndex) {
    const height = LOOP_HEIGHT + loopIndex * LOOP_STEP;
    const top = center.y - NODE_HEIGHT / 2;
    const start = {x: center.x + NODE_WIDTH / 4, y: top};
    const end = {x: center.x - NODE_WIDTH / 4, y: top};
    const first = {x: center.x + NODE_WIDTH / 2, y: top - height};
    const second = {x: center.x - NODE_WIDTH / 2, y: top - height};
    return {
      path: `M ${start.x} ${start.y} C ${first.x} ${first.y} ${second.x} ${second.y} ${end.x} ${end.y}`,
      start, end, at: (t) => cubicPoint(start, first, second, end, t),
    };
  }

  /** Every drawable edge of `currentGraph` with its shape, in draft order. */
  function edgeShapes(currentGraph) {
    const groupCounts = {};
    return tools.edgeRows(currentGraph)
      .filter((row) => positions[row.source] && positions[row.edge.to])
      .map((row) => {
        const target = row.edge.to;
        const groupKey = [row.source, target].sort().join("\u0000");
        const groupIndex = groupCounts[groupKey] ?? 0;
        groupCounts[groupKey] = groupIndex + 1;
        const shape = row.source === target
          ? loopShape(positions[target], groupIndex)
          : curveShape(positions[row.source], positions[target], row.source < target, groupIndex);
        return {row, ...shape};
      });
  }


  //==========// DOM //==========//

  /** Builds an SVG element with attributes and children. */
  function svgElement(tag, attributes = {}, children = []) {
    const created = document.createElementNS(SVG_NAMESPACE, tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (value !== null && value !== undefined && value !== false) {
        created.setAttribute(name, value);
      }
    }
    created.append(...[].concat(children));
    return created;
  }

  /** An SVG text element (its content set as text, never markup). */
  const svgText = (attributes, text) => {
    const created = svgElement("text", attributes);
    created.textContent = text;
    return created;
  };

  /** An arrowhead marker definition. */
  const arrowMarker = (id, markerClass) => svgElement("marker", {
    id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: "auto-start-reverse",
  }, svgElement("path", {d: "M 0 0 L 10 5 L 0 10 z", class: markerClass}));

  const svg = svgElement("svg", {class: "graph-svg"});
  const viewport = svgElement("g");
  const edgeLayer = svgElement("g");
  const nodeLayer = svgElement("g");
  const handleLayer = svgElement("g");   // a selected edge's end handles: above the nodes they sit on, so they stay grabbable
  const overlayLayer = svgElement("g", {class: "graph-overlay"});
  viewport.append(edgeLayer, nodeLayer, handleLayer, overlayLayer);
  svg.append(svgElement("defs", {}, [
    arrowMarker("graph-arrow", "arrow-head"), arrowMarker("graph-arrow-selected", "arrow-head selected"),
  ]), viewport);

  const emptyNote = ui.make("div", {class: "graph-empty note", hidden: true});
  const menu = ui.make("div", {class: "graph-menu", hidden: true});
  const canvas = ui.make("div", {class: "graph-canvas"}, [svg, emptyNote, menu]);
  const knowledgePanel = ui.make("aside", {class: "graph-side graph-knowledge", "data-enter-scope": true});
  const inspector = ui.make("aside", {class: "graph-side graph-inspector", "data-enter-scope": true});

  /** A side panel's collapse arrow: points toward the panel's edge when open, inward when collapsed. */
  function collapseHandle(panel, side, storageKey) {
    const handle = ui.make("button", {type: "button", class: `side-handle side-handle-${side}`});
    const setShown = (shown) => {
      panel.hidden = !shown;
      const pointsLeft = (side === "left") === shown;
      handle.textContent = pointsLeft ? "◀" : "▶";   // ◀ ▶
      handle.title = `${shown ? "Hide" : "Show"} the ${side === "left" ? "Knowledge panel" : "inspector"}`;
      try {
        localStorage.setItem(storageKey, shown ? "1" : "0");
      } catch (error) {
        // NOTE: storage can be unavailable (private window, blocked site data); the choice just isn't remembered.
      }
      if (shown) {
        refreshSidePanels(true);
      }
    };
    handle.addEventListener("click", () => setShown(panel.hidden));
    let shown = true;
    try {
      shown = localStorage.getItem(storageKey) !== "0";
    } catch (error) {
      // NOTE: see above
    }
    return {handle, setShown, initiallyShown: shown};
  }

  const knowledgeCollapse = collapseHandle(knowledgePanel, "left", KNOWLEDGE_STORAGE_KEY);
  const inspectorCollapse = collapseHandle(inspector, "right", INSPECTOR_STORAGE_KEY);


  //==========// Toolbar //==========//

  const addButton = ui.make("button", {type: "button", text: "+ Node", title: "Add a node (or double-click blank space)", onclick: addNodeAtCenter});
  const editButton = ui.make("button", {type: "button", text: "Edit", title: "Edit the selection (or double-click it)", onclick: () => openPopoverForSelection()});
  const deleteButton = ui.make("button", {type: "button", text: "Delete", title: "Delete the selection (Delete key)", onclick: deleteSelection});
  const labelsBox = ui.make("input", {type: "checkbox", onchange: () => { showLabels = labelsBox.checked; render(); }});
  const modeRadio = (value, label) => ui.make("label", {}, [
    ui.make("input", {type: "radio", name: "graph-mode", value, checked: value === mode, onchange: () => setMode(value)}),
    ` ${label}`,
  ]);
  element.append(
    tools.toolbar,
    ui.make("div", {class: "button-row"}, [
      modeRadio("live", "Live (read-only)"), modeRadio("draft", "Draft (edit)"),
      ui.make("span", {class: "toolbar-gap"}),
      addButton, editButton, deleteButton,
      ui.make("button", {type: "button", text: "Fit", title: "Fit the graph in view (F)", onclick: fitView}),
      ui.make("label", {}, [labelsBox, " Edge labels"]),
    ]),
    ui.make("div", {class: "graph-editor"}, [
      knowledgePanel, knowledgeCollapse.handle, canvas, inspectorCollapse.handle, inspector,
    ]),
  );

  function setMode(value) {
    mode = value;
    clearSelection();
    closePopover();
    fittedNodeIds = null;   // re-fit to the other graph
    syncFromState();
  }


  //==========// Rendering //==========//

  function applyViewTransform() {
    viewport.setAttribute("transform", `translate(${view.x} ${view.y}) scale(${view.zoom})`);
    if (popover) {
      positionPopover();
    }
  }

  /** Everything the canvas draws from, for change detection. */
  function canvasSignature() {
    return JSON.stringify([mode, panelState && graph(), positions, [...selection.nodes], [...selection.edges], showLabels,
                           panelState && problems(), editable() ? null : panelState?.live?.active_node_id]);
  }

  /** Redraws only if something the canvas shows changed (a redraw replaces every element,
      which would cut a double-click in two and reset hover). */
  function renderIfChanged() {
    if (canvasSignature() !== renderedSignature) {
      render();
    }
  }

  /** The selected edge's endpoints, for the origin/recipient highlight (null unless exactly one edge is selected). */
  function selectedEdgeEnds(currentGraph) {
    if (selection.edges.size !== 1 || selection.nodes.size !== 0) {
      return null;
    }
    const {source, index} = parseEdgeKey([...selection.edges][0]);
    const edge = currentGraph.edges[source]?.[index];
    return edge ? {origin: source, recipient: edge.to} : null;
  }

  /** Redraws every node and edge from `positions` and the selection. */
  function render() {
    renderedSignature = canvasSignature();
    edgeLayer.replaceChildren();
    nodeLayer.replaceChildren();
    handleLayer.replaceChildren();
    applyViewTransform();
    const currentGraph = panelState ? graph() : null;
    emptyNote.hidden = currentGraph !== null;
    emptyNote.textContent = editable() ? "" : "No mission graph is known here for the Target yet.";
    addButton.disabled = deleteButton.disabled = !editable();
    if (!currentGraph) {
      return;
    }
    for (const shape of edgeShapes(currentGraph)) {
      edgeLayer.append(drawEdge(currentGraph, shape));
    }
    trimHalos();
    const ends = selectedEdgeEnds(currentGraph);
    for (const nodeId of Object.keys(currentGraph.nodes)) {
      if (positions[nodeId]) {
        nodeLayer.append(drawNode(currentGraph, nodeId, ends));
      }
    }
  }

  /** Leaves each halo off the last HALO_END_TRIM px at both ends (it needs the path's real length, so it runs once the paths are in the DOM). */
  function trimHalos() {
    for (const halo of edgeLayer.querySelectorAll(".edge-halo")) {
      const length = halo.getTotalLength();
      halo.setAttribute("stroke-dasharray", length > 2 * HALO_END_TRIM
        ? `0 ${HALO_END_TRIM} ${length - 2 * HALO_END_TRIM} ${HALO_END_TRIM}` : `0 ${length}`);
    }
  }

  function drawEdge(currentGraph, shape) {
    const {row} = shape;
    const selected = selection.edges.has(row.key);
    const condition = JSON.stringify(row.edge.condition);
    const siblingCount = currentGraph.edges[row.source].length;
    const edgeProblems = problems().edges[row.key];
    const group = svgElement("g", {class: `graph-edge${selected ? " selected" : ""}`, "data-edge": row.key}, [
      svgElement("title", {}, `${row.source} → ${row.edge.to}: ${condition}` + (edgeProblems ? `\n${WARNING} ${edgeProblems.join("\n")}` : "")),
      // NOTE: the halo is a wider stroke in the canvas color under the line, drawn in draft order, so a later edge cuts a gap where it crosses an earlier one
      svgElement("path", {class: "edge-halo", d: shape.path}),
      svgElement("path", {class: "edge-hit", d: shape.path}),
      svgElement("path", {class: "edge-line", d: shape.path, "marker-end": `url(#${selected ? "graph-arrow-selected" : "graph-arrow"})`}),
    ]);
    // Priority is behavior (edges are checked in order; the first true one fires), so it stays visible wherever there's a choice
    if (siblingCount > 1) {
      const point = shape.at(BADGE_POSITION);
      const emphasized = selection.nodes.has(row.source) ? " emphasized" : "";
      group.append(svgElement("g", {class: `edge-badge${emphasized}`}, [
        svgElement("title", {}, `Checked ${ordinal(row.index + 1)} of ${siblingCount} from '${row.source}'; the first true condition wins`),
        svgElement("rect", {x: point.x - BADGE_WIDTH / 2, y: point.y - BADGE_HEIGHT / 2, width: BADGE_WIDTH, height: BADGE_HEIGHT, rx: BADGE_HEIGHT / 2}),
        svgText({class: "edge-badge-text", x: point.x, y: point.y}, ordinal(row.index + 1)),
      ]));
    }
    const middle = shape.at(0.5);
    if (showLabels) {
      group.append(svgText({class: "edge-label", x: middle.x, y: middle.y}, truncate(condition)));
    }
    if (edgeProblems) {
      group.append(svgText({class: "edge-warning", x: middle.x, y: middle.y - 10}, WARNING));
    }
    if (selected && editable()) {
      handleLayer.append(
        svgElement("circle", {class: "edge-handle", cx: shape.start.x, cy: shape.start.y, r: HANDLE_RADIUS, "data-handle": "source", "data-edge": row.key}),
        svgElement("circle", {class: "edge-handle", cx: shape.end.x, cy: shape.end.y, r: HANDLE_RADIUS, "data-handle": "target", "data-edge": row.key}));
    }
    return group;
  }

  function drawNode(currentGraph, nodeId, ends) {
    const position = positions[nodeId];
    const requests = currentGraph.nodes[nodeId].capabilities;
    const requestCount = Object.keys(requests).length;
    const nodeProblems = problems().requests[nodeId];
    const classes = ["graph-node"];
    if (selection.nodes.has(nodeId)) classes.push("selected");
    if (currentGraph.start === nodeId) classes.push("start");
    if (!editable() && panelState.live?.active_node_id === nodeId) classes.push("active");
    if (ends?.origin === nodeId) classes.push("edge-origin");
    if (ends?.recipient === nodeId) classes.push("edge-recipient");
    if (nodeProblems) classes.push("warning");
    const problemLines = nodeProblems ? Object.entries(nodeProblems).flatMap(([name, messages]) => messages.map((message) => `${WARNING} ${name}: ${message}`)) : [];
    const tooltip = [nodeId, ...Object.entries(requests).map(([name, request]) => `  ${name}: ${request.capability}`), ...problemLines].join("\n");

    const group = svgElement("g", {class: classes.join(" "), "data-node": nodeId, transform: `translate(${position.x} ${position.y})`}, [
      svgElement("title", {}, tooltip),
      svgElement("rect", {x: -NODE_WIDTH / 2, y: -NODE_HEIGHT / 2, width: NODE_WIDTH, height: NODE_HEIGHT, rx: NODE_CORNER_RADIUS}),
      svgText({class: "node-label", x: 0, y: -4}, truncate(nodeId)),
      svgText({class: "node-sub", x: 0, y: 13}, plural(requestCount, "capability", "capabilities")),
    ]);
    if (currentGraph.start === nodeId) {
      group.append(svgText({class: "node-tag", x: -NODE_WIDTH / 2 + 4, y: -NODE_HEIGHT / 2 - 5}, "start"));
    }
    if (nodeProblems) {
      group.append(svgText({class: "node-warning", x: -NODE_WIDTH / 2 + WARNING_OFFSET + 6, y: -NODE_HEIGHT / 2 + WARNING_OFFSET + 8}, WARNING));
    }
    if (editable()) {
      group.append(svgElement("circle", {class: "node-port", cx: NODE_WIDTH / 2, cy: 0, r: PORT_RADIUS, "data-port": nodeId}));
    }
    if (selection.nodes.has(nodeId)) {
      const left = NODE_WIDTH / 2 - EDIT_BUTTON_SIZE / 2;
      const top = -NODE_HEIGHT / 2 - EDIT_BUTTON_SIZE / 2;
      group.append(svgElement("g", {class: "node-edit", "data-edit": nodeId}, [
        svgElement("title", {}, "Edit (or double-click the node)"),
        svgElement("rect", {x: left, y: top, width: EDIT_BUTTON_SIZE, height: EDIT_BUTTON_SIZE, rx: 4}),
        svgText({x: left + EDIT_BUTTON_SIZE / 2, y: top + EDIT_BUTTON_SIZE / 2}, "✎"),   // ✎
      ]));
    }
    return group;
  }

  /** The in-progress gesture's overlay: a rubber-band box, or the line of an edge being drawn
      (to a ghost node when the pointer is over blank space during a connect). */
  function drawOverlay() {
    overlayLayer.replaceChildren();
    if (drag?.kind === "box" && drag.moved) {
      const {start, current} = drag;
      overlayLayer.append(svgElement("rect", {
        class: "selection-box", x: Math.min(start.x, current.x), y: Math.min(start.y, current.y),
        width: Math.abs(current.x - start.x), height: Math.abs(current.y - start.y),
      }));
    } else if ((drag?.kind === "connect" || drag?.kind === "reroute") && drag.moved) {
      overlayLayer.append(svgElement("line", {
        class: "connect-line", x1: drag.anchor.x, y1: drag.anchor.y, x2: drag.current.x, y2: drag.current.y,
      }));
      if (drag.kind === "connect" && drag.hoverNode === null) {
        overlayLayer.append(svgElement("rect", {
          class: "ghost-node", x: drag.current.x - NODE_WIDTH / 2, y: drag.current.y - NODE_HEIGHT / 2,
          width: NODE_WIDTH, height: NODE_HEIGHT, rx: NODE_CORNER_RADIUS,
        }));
      }
    }
  }

  /** Marks the node a drawn edge would attach to if released now (without redrawing the canvas). */
  function markDropTarget(nodeId) {
    nodeLayer.querySelectorAll(".drop-target").forEach((node) => node.classList.remove("drop-target"));
    if (nodeId !== null) {
      nodeLayer.querySelector(`[data-node="${CSS.escape(nodeId)}"]`)?.classList.add("drop-target");
    }
  }

  /** Frames the whole graph in the canvas (skipped while the tab is hidden, when it has no size). */
  function fitView() {
    const width = svg.clientWidth;
    const height = svg.clientHeight;
    const points = Object.values(positions);
    if (width === 0 || height === 0) {
      return false;
    }
    if (points.length === 0) {
      Object.assign(view, {x: width / 2, y: height / 2, zoom: 1});
      applyViewTransform();
      return true;
    }
    const minX = Math.min(...points.map((point) => point.x)) - NODE_WIDTH / 2;
    const maxX = Math.max(...points.map((point) => point.x)) + NODE_WIDTH / 2;
    const minY = Math.min(...points.map((point) => point.y)) - NODE_HEIGHT / 2 - LOOP_HEIGHT;
    const maxY = Math.max(...points.map((point) => point.y)) + NODE_HEIGHT / 2;
    const zoom = clampZoom(Math.min((width - 2 * FIT_MARGIN) / (maxX - minX), (height - 2 * FIT_MARGIN) / (maxY - minY), MAX_FIT_ZOOM));
    Object.assign(view, {zoom, x: width / 2 - zoom * (minX + maxX) / 2, y: height / 2 - zoom * (minY + maxY) / 2});
    applyViewTransform();
    return true;
  }


  //==========// State Sync //==========//

  /** Takes positions from the latest state, drops a vanished selection, redraws, and fits a new graph. */
  function syncFromState() {
    const currentGraph = graph();
    const layout = (editable() ? panelState.draft_layout : panelState.live?.layout) || {};
    positions = Object.fromEntries(Object.entries(layout).map(([nodeId, point]) => [nodeId, fromLayoutUnits(point)]));
    pruneSelection(currentGraph);
    renderIfChanged();

    const nodeIds = currentGraph ? Object.keys(currentGraph.nodes) : [];
    const replaced = fittedNodeIds === null || !nodeIds.some((nodeId) => fittedNodeIds.includes(nodeId));
    if (api.isVisible() && replaced && fitView()) {
      fittedNodeIds = nodeIds;
    }
    refreshSidePanels(false);
  }

  function refreshSidePanels(force) {
    if (!panelState) {
      return;
    }
    inspectorHost.refresh(force);
    knowledgeHost.refresh(force);
    if (popover) {
      popover.host.refresh();
    }
  }

  function pruneSelection(currentGraph) {
    const nodeIds = new Set(currentGraph ? Object.keys(currentGraph.nodes) : []);
    const edgeKeys = new Set(currentGraph ? tools.edgeRows(currentGraph).map((row) => row.key) : []);
    selection.nodes.forEach((nodeId) => nodeIds.has(nodeId) || selection.nodes.delete(nodeId));
    selection.edges.forEach((key) => edgeKeys.has(key) || selection.edges.delete(key));
    if (popover && !itemExists(popover.host.item)) {
      closePopover();
    }
  }


  //==========// Selection //==========//

  function clearSelection() {
    selection.nodes.clear();
    selection.edges.clear();
    selectionChanged();
  }

  function selectOnly({nodes = [], edges = []}) {
    selection.nodes = new Set(nodes);
    selection.edges = new Set(edges);
    selectionChanged();
  }

  function toggleSelected(kind, key) {
    if (selection[kind].has(key)) {
      selection[kind].delete(key);
    } else {
      selection[kind].add(key);
    }
    selectionChanged();
  }

  function selectionChanged() {
    renderIfChanged();
    inspectorHost.show(selectionItem());
    knowledgeHost.refresh();   // its "bound by the selected node" highlight
  }

  /** What the inspector shows for the selection: one node, one edge, several items, or nothing. */
  function selectionItem() {
    const nodeCount = selection.nodes.size;
    const edgeCount = selection.edges.size;
    if (nodeCount === 1 && edgeCount === 0) {
      return {kind: "node", id: [...selection.nodes][0]};
    }
    if (edgeCount === 1 && nodeCount === 0) {
      return {kind: "edge", key: [...selection.edges][0]};
    }
    return nodeCount + edgeCount > 1 ? {kind: "multiple"} : {kind: "none"};
  }

  function itemExists(item) {
    const currentGraph = graph();
    if (!currentGraph || !item) {
      return false;
    }
    if (item.kind === "node") {
      return item.id in currentGraph.nodes;
    }
    if (item.kind === "edge") {
      const {source, index} = parseEdgeKey(item.key);
      return Boolean(currentGraph.edges[source]?.[index]);
    }
    return true;
  }


  //==========// Pointer Gestures //==========//

  /** The canvas point (px, zoom 1) under a pointer event. */
  function toCanvas(event) {
    const bounds = svg.getBoundingClientRect();
    return {x: (event.clientX - bounds.left - view.x) / view.zoom, y: (event.clientY - bounds.top - view.y) / view.zoom};
  }

  /** The node id under a point on screen, or null. */
  function nodeAtScreen(event) {
    return document.elementFromPoint(event.clientX, event.clientY)?.closest("[data-node]")?.dataset.node ?? null;
  }

  function onPointerDown(event) {
    closeMenu();
    const target = event.target;
    const point = toCanvas(event);
    const pressed = {clientX: event.clientX, clientY: event.clientY};
    if (event.button === MIDDLE_BUTTON || (event.button === PRIMARY_BUTTON && spaceHeld)) {
      event.preventDefault();
      drag = {kind: "pan", last: pressed};
    } else if (event.button !== PRIMARY_BUTTON) {
      return;   // the right button opens the context menu instead
    } else if (target.closest("[data-edit]")) {
      openPopover({kind: "node", id: target.closest("[data-edit]").dataset.edit});
      return;
    } else if (editable() && target.closest("[data-port]")) {
      const source = target.closest("[data-port]").dataset.port;
      drag = {kind: "connect", source, anchor: positions[source], current: point, pressed, moved: false, hoverNode: null};
    } else if (editable() && target.closest("[data-handle]")) {
      const handle = target.closest("[data-handle]");
      const {source, index} = parseEdgeKey(handle.dataset.edge);
      const edge = panelState.draft.edges[source][index];
      // Dragging the source end pivots on the target, and vice versa
      const anchorNode = handle.dataset.handle === "source" ? edge.to : source;
      drag = {kind: "reroute", key: handle.dataset.edge, end: handle.dataset.handle, anchor: positions[anchorNode],
              current: point, pressed, moved: false, hoverNode: null};
    } else if (target.closest("[data-node]")) {
      const nodeId = target.closest("[data-node]").dataset.node;
      if (event.shiftKey || event.ctrlKey || event.metaKey) {
        toggleSelected("nodes", nodeId);
        return;
      }
      if (!selection.nodes.has(nodeId)) {
        selectOnly({nodes: [nodeId]});
      }
      if (editable()) {
        const origins = Object.fromEntries([...selection.nodes].map((selectedId) => [selectedId, {...positions[selectedId]}]));
        drag = {kind: "move", start: point, origins, pressed, moved: false};
      }
    } else if (target.closest("[data-edge]")) {
      const key = target.closest("[data-edge]").dataset.edge;
      if (event.shiftKey || event.ctrlKey || event.metaKey) {
        toggleSelected("edges", key);
      } else {
        selectOnly({edges: [key]});
      }
      return;
    } else {
      closePopover();
      if (!event.shiftKey) {
        clearSelection();
      }
      drag = {kind: "box", start: point, current: point, base: new Set(selection.nodes), pressed, moved: false};
    }
    if (drag) {
      svg.setPointerCapture(event.pointerId);
    }
  }

  function onPointerMove(event) {
    if (!drag) {
      return;
    }
    if (drag.kind === "pan") {
      view.x += event.clientX - drag.last.clientX;
      view.y += event.clientY - drag.last.clientY;
      drag.last = {clientX: event.clientX, clientY: event.clientY};
      applyViewTransform();
      return;
    }
    if (!drag.moved && Math.hypot(event.clientX - drag.pressed.clientX, event.clientY - drag.pressed.clientY) < DRAG_THRESHOLD) {
      return;
    }
    drag.moved = true;
    const point = toCanvas(event);
    if (drag.kind === "move") {
      for (const [nodeId, origin] of Object.entries(drag.origins)) {
        positions[nodeId] = {x: origin.x + point.x - drag.start.x, y: origin.y + point.y - drag.start.y};
      }
      render();
    } else if (drag.kind === "box") {
      drag.current = point;
      const [left, right] = [Math.min(drag.start.x, point.x), Math.max(drag.start.x, point.x)];
      const [top, bottom] = [Math.min(drag.start.y, point.y), Math.max(drag.start.y, point.y)];
      const inside = Object.entries(positions)
        .filter(([, position]) => position.x >= left && position.x <= right && position.y >= top && position.y <= bottom)
        .map(([nodeId]) => nodeId);
      selection.nodes = new Set([...drag.base, ...inside]);
      render();
    } else {
      drag.current = point;
      drag.hoverNode = nodeAtScreen(event);
      markDropTarget(drag.hoverNode);
    }
    drawOverlay();
  }

  async function onPointerUp(event) {
    const finished = drag;
    drag = null;
    overlayLayer.replaceChildren();
    markDropTarget(null);
    if (!finished) {
      return;
    }
    if (finished.kind === "move" && finished.moved) {
      await tools.run("move_nodes", {positions: layoutInUnits()});
    } else if (finished.kind === "box") {
      selectionChanged();
    } else if (finished.kind === "connect" && finished.moved) {
      const target = nodeAtScreen(event);
      openPopover({kind: "new-edge", source: finished.source, target, drop: target === null ? toCanvas(event) : null});
    } else if (finished.kind === "reroute" && finished.moved) {
      await reroute(finished.key, finished.end, nodeAtScreen(event));
    }
    if (pendingSync) {
      pendingSync = false;
      syncFromState();
    }
  }

  function onDoubleClick(event) {
    // NOTE: what's under the pointer now, not event.target: a click that changed the selection
    // redrew the canvas, so the double-click may not report the element it actually landed on.
    const target = document.elementFromPoint(event.clientX, event.clientY) || event.target;
    if (target.closest("[data-node]")) {
      openPopover({kind: "node", id: target.closest("[data-node]").dataset.node});
    } else if (target.closest("[data-edge]")) {
      openPopover({kind: "edge", key: target.closest("[data-edge]").dataset.edge});
    } else if (editable()) {
      addNodeAt(toCanvas(event));
    }
  }

  function onWheel(event) {
    event.preventDefault();
    const bounds = svg.getBoundingClientRect();
    const screenX = event.clientX - bounds.left;
    const screenY = event.clientY - bounds.top;
    const zoom = clampZoom(view.zoom * (event.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR));
    view.x = screenX - (screenX - view.x) * (zoom / view.zoom);
    view.y = screenY - (screenY - view.y) * (zoom / view.zoom);
    view.zoom = zoom;
    applyViewTransform();
  }

  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", onPointerUp);
  svg.addEventListener("pointercancel", () => { drag = null; overlayLayer.replaceChildren(); markDropTarget(null); syncFromState(); });
  svg.addEventListener("dblclick", onDoubleClick);
  svg.addEventListener("contextmenu", onContextMenu);
  svg.addEventListener("wheel", onWheel, {passive: false});


  //==========// Draft Edits //==========//

  /** Every displayed node position in layout units, so a move pins the whole graph (nothing re-flows). */
  function layoutInUnits(extra = {}) {
    const placed = {...positions, ...extra};
    return Object.fromEntries(Object.entries(placed).map(([nodeId, point]) => [nodeId, toLayoutUnits(point)]));
  }

  /** The first free automatic node id: node_1, node_2, ... */
  function nextNodeId() {
    let number = 1;
    while (`${AUTO_NODE_PREFIX}${number}` in panelState.draft.nodes) {
      number += 1;
    }
    return `${AUTO_NODE_PREFIX}${number}`;
  }

  /** `base`, or base_2, base_3, ... if `taken` already has it. */
  function uniqueName(base, taken) {
    let candidate = base;
    let number = 2;
    while (candidate in taken) {
      candidate = `${base}_${number}`;
      number += 1;
    }
    return candidate;
  }

  /** Adds a node at a canvas point, then opens it in a popover with its id ready to rename. */
  async function addNodeAt(point) {
    if (!editable()) {
      return;
    }
    const nodeId = nextNodeId();
    const added = await tools.editBatch([
      {tool: "add_node", arguments: {node_id: nodeId}},
      {tool: "move_nodes", arguments: {positions: layoutInUnits({[nodeId]: point})}},
    ]);
    if (added) {
      selectOnly({nodes: [nodeId]});
      openPopover({kind: "node", id: nodeId}, {focusId: true});
    }
  }

  function addNodeAtCenter() {
    const bounds = svg.getBoundingClientRect();
    addNodeAt(toCanvas({clientX: bounds.left + bounds.width / 2, clientY: bounds.top + bounds.height / 2}));
  }

  /** Deletes every selected edge and node as one undo step. */
  async function deleteSelection() {
    if (!editable()) {
      return;
    }
    // Edges first, highest index first within a source, so earlier removals never shift a later one's index
    const edgeSteps = [...selection.edges].map(parseEdgeKey)
      .filter(({source}) => !selection.nodes.has(source))
      .sort((first, second) => first.source.localeCompare(second.source) || second.index - first.index)
      .map(({source, index}) => ({tool: "remove_edge", arguments: {source_id: source, index}}));
    const nodeSteps = [...selection.nodes].map((nodeId) => ({tool: "remove_node", arguments: {node_id: nodeId}}));
    if (edgeSteps.length + nodeSteps.length > 0 && await tools.editBatch([...edgeSteps, ...nodeSteps])) {
      closePopover();
      clearSelection();
    }
  }

  /** Moves one end of an edge onto `nodeId`, keeping its condition (the target keeps its priority slot). */
  async function reroute(key, end, nodeId) {
    const {source, index} = parseEdgeKey(key);
    const edge = panelState.draft.edges[source]?.[index];
    if (!edge || nodeId === null || nodeId === (end === "source" ? source : edge.to)) {
      return;
    }
    const newSource = end === "source" ? nodeId : source;
    const newKey = newSource === source ? key : `${newSource}#${(panelState.draft.edges[newSource] || []).length}`;
    const edited = await tools.edit("edit_edge", {
      source_id: source, index, new_source_id: newSource,
      new_target_id: end === "target" ? nodeId : edge.to, condition: edge.condition,
    });
    if (edited) {
      selectOnly({edges: [newKey]});
    }
  }

  /** Moves an edge one step earlier (-1) or later (+1) in its source's priority order; resolves to its new key or null. */
  async function shiftEdge(key, step) {
    const {source, index} = parseEdgeKey(key);
    const newIndex = index + step;
    if (newIndex < 0 || newIndex >= (panelState.draft.edges[source] || []).length) {
      return null;
    }
    if (!(await tools.run("move_edge", {source_id: source, index, new_index: newIndex})).ok) {
      return null;
    }
    const newKey = `${source}#${newIndex}`;
    selectOnly({edges: [newKey]});
    return newKey;
  }


  //==========// Item Hosts (inspector, popover, knowledge panel) //==========//

  /** A container showing one item's editor, rebuilt when its data changes, but never while
      something inside it has the keyboard (so a poll can't clobber what's being typed). */
  function makeItemHost(container, build, options = {}) {
    let signature = null;
    const host = {
      item: null,
      options,
      show(item, showOptions = {}) {
        host.item = item;
        host.options = {...options, ...showOptions};
        signature = null;
        host.refresh(true);
      },
      refresh(force = false) {
        if (!host.item || !panelState || container.hidden) {
          return;
        }
        if (!force && container.contains(document.activeElement)) {
          return;
        }
        const next = JSON.stringify([mode, host.item, itemData(host.item)]);
        if (force || next !== signature) {
          signature = next;
          container.replaceChildren(...build(host.item, host.options, host));
        }
      },
    };
    container.addEventListener("focusout", () => setTimeout(() => host.refresh(), 0));
    return host;
  }

  /** The data an item's editor shows, for change detection. */
  function itemData(item) {
    const currentGraph = graph();
    if (!currentGraph) {
      return null;
    }
    const live = editable() ? null : panelState.live;   // live status only matters in Live mode; in Draft mode it would rebuild every poll
    if (item.kind === "node") {
      return [currentGraph.nodes[item.id], currentGraph.start, currentGraph.edges[item.id], live,
              panelState.target_capabilities, currentGraph.knowledge, problems().requests[item.id], panelState.target];
    }
    if (item.kind === "edge") {
      return [currentGraph.edges[parseEdgeKey(item.key).source], Object.keys(currentGraph.nodes), currentGraph.knowledge,
              problems().edges[item.key], panelState.edge_rows?.[item.key]];
    }
    if (item.kind === "knowledge") {
      return [currentGraph.knowledge, panelState.unset_keys, panelState.following_keys, problems().keys, live?.values,
              item.editing, [...selection.nodes], panelState.target];
    }
    if (item.kind === "none") {
      return [problems().graph, live, panelState.name];
    }
    return [selection.nodes.size, selection.edges.size];
  }

  const inspectorHost = makeItemHost(inspector, buildItemEditor);
  const knowledgeHost = makeItemHost(knowledgePanel, buildKnowledgePanel);
  knowledgeHost.item = {kind: "knowledge", editing: null};

  /** The editor for one item: a node, an edge, a new edge, a multi-selection, or (inspector only) the overview. */
  function buildItemEditor(item, options, host) {
    if (item.kind === "new-edge") {
      return newEdgeEditor(item);
    }
    if (!itemExists(item)) {
      return [ui.make("p", {class: "note", text: graph() ? "Nothing selected." : "No graph."})];
    }
    if (item.kind === "node") {
      return editable() ? nodeEditor(item.id, options, host) : liveNodeView(item.id);
    }
    if (item.kind === "edge") {
      return edgeEditor(item.key, host);
    }
    if (item.kind === "multiple") {
      return multipleEditor();
    }
    return editable() ? overviewEditor() : liveOverview();
  }

  const heading = (text) => ui.make("h3", {text});
  const field = (label, input) => ui.make("label", {class: "inspector-field"}, [ui.make("span", {text: label}), input]);
  const smallButton = (label, onClick, title) => ui.make("button", {type: "button", class: "small", text: label, title, onclick: onClick});
  const listRow = (text, buttons = [], onClick = null) => ui.make("div", {class: `inspector-row${onClick ? " clickable" : ""}`, onclick: onClick},
    [ui.make("span", {class: "inspector-row-text", text}), ...buttons]);
  const warningList = (messages) => (messages?.length
    ? [ui.make("ul", {class: "warning-list"}, messages.map((message) => ui.make("li", {text: `${WARNING} ${message}`})))] : []);


  //==========// Node Editor (inline capability requests) //==========//

  function nodeEditor(nodeId, options, host) {
    const currentGraph = panelState.draft;
    const node = currentGraph.nodes[nodeId];

    const idInput = ui.make("input", {type: "text", value: nodeId, autocomplete: "off"});
    idInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        idInput.value = nodeId;
        idInput.blur();
      }
    });
    idInput.addEventListener("change", async () => {
      const newId = idInput.value.trim();
      if (!newId || newId === nodeId) {
        idInput.value = nodeId;
        return;
      }
      // Point the host at the new id before the edit's state arrives, so it follows the node instead of closing
      const previousItem = host.item;
      host.item = {kind: "node", id: newId};
      if (await tools.edit("rename_node", {old_id: nodeId, new_id: newId})) {
        selectOnly({nodes: [newId]});
      } else {
        host.show(previousItem);
      }
    });
    if (options.focusId) {
      setTimeout(() => { idInput.focus(); idInput.select(); }, 0);
    }

    const startBox = ui.make("input", {type: "checkbox", checked: currentGraph.start === nodeId, disabled: currentGraph.start === nodeId,
                                       onchange: () => tools.edit("set_start_node", {node_id: nodeId})});
    const requestProblems = problems().requests[nodeId] || {};
    const requestBlocks = Object.entries(node.capabilities).map(([name, request]) => requestBlock(nodeId, name, request, requestProblems[name]));
    const outgoing = (currentGraph.edges[nodeId] || []).map((edge, index, edges) => listRow(
      `${edges.length > 1 ? `${ordinal(index + 1)}: ` : ""}→ ${edge.to}  ${truncate(JSON.stringify(edge.condition))}`,
      [smallButton("↑", (event) => { event.stopPropagation(); shiftEdge(`${nodeId}#${index}`, -1); }, "Checked earlier"),
       smallButton("↓", (event) => { event.stopPropagation(); shiftEdge(`${nodeId}#${index}`, 1); }, "Checked later")],
      () => focusItem(host, {kind: "edge", key: `${nodeId}#${index}`}),
    ));

    return [
      heading("Node"),
      field("Id", idInput),
      field("Start node", startBox),
      heading("Capability requests"),
      ...(requestBlocks.length ? requestBlocks : [ui.make("p", {class: "note", text: "None yet."})]),
      addCapabilitySelect(nodeId),
      heading("Outgoing edges (checked in order; first true wins)"),
      ...(outgoing.length ? outgoing : [ui.make("p", {class: "note", text: "None: drag this node's port (●) to another node."})]),
      ui.buttonRow([{label: "Delete node", onClick: () => tools.edit("remove_node", {node_id: nodeId}).then((removed) => removed && closePopover())}]),
    ];
  }

  /** A "+ Capability" select: picking one adds a request named after it, with nothing bound yet (flagged until it is). */
  function addCapabilitySelect(nodeId) {
    const capabilities = panelState.target_capabilities;
    const select = ui.make("select", {class: "add-capability", disabled: !capabilities?.length}, [
      ui.make("option", {value: "", text: capabilities ? "+ Capability..." : "+ Capability (the Target's capabilities aren't known yet)"}),
      ...(capabilities || []).map((capability) => ui.make("option", {value: capability.ipl_type, text: `${capability.ipl_type}: ${capability.description}`})),
    ]);
    select.addEventListener("change", () => {
      const capability = select.value;
      if (capability) {
        const name = uniqueName(capability, panelState.draft.nodes[nodeId].capabilities);
        tools.edit("add_capability", {node_id: nodeId, request_name: name, capability, inputs: {}, outputs: {}});
      }
    });
    return select;
  }

  /** One capability request, edited inline: name, capability, and a binding select per field (each applies on change). */
  function requestBlock(nodeId, name, request, messages) {
    const capabilities = panelState.target_capabilities || [];
    const capability = capabilities.find((candidate) => candidate.ipl_type === request.capability);
    const save = (changes) => {
      const next = {name, capability: request.capability, inputs: {...request.inputs}, outputs: {...request.outputs}, ...changes};
      return tools.edit("edit_capability", {node_id: nodeId, old_name: name, new_name: next.name, capability: next.capability,
                                            inputs: next.inputs, outputs: next.outputs});
    };

    const nameInput = ui.make("input", {type: "text", value: name, autocomplete: "off"});
    nameInput.addEventListener("change", () => {
      const newName = nameInput.value.trim();
      if (newName && newName !== name) {
        save({name: newName});
      } else {
        nameInput.value = name;
      }
    });
    const capabilitySelect = ui.make("select", {}, [
      ...(capability ? [] : [ui.make("option", {value: request.capability, text: `${WARNING} ${request.capability} (not on the Target)`})]),
      ...capabilities.map((candidate) => ui.make("option", {value: candidate.ipl_type, text: candidate.ipl_type})),
    ]);
    capabilitySelect.value = request.capability;
    capabilitySelect.addEventListener("change", () => {
      // Keep only the bindings whose field names the new capability also has
      const chosen = capabilities.find((candidate) => candidate.ipl_type === capabilitySelect.value);
      if (!chosen) {
        return;
      }
      const keep = (bindings, specs) => Object.fromEntries(Object.entries(bindings || {}).filter(([field]) => specs.some((spec) => spec.name === field)));
      save({capability: chosen.ipl_type, inputs: keep(request.inputs, chosen.inputs), outputs: keep(request.outputs, chosen.outputs)});
    });

    const bindingRows = capability ? [
      ...capability.inputs.map((spec) => bindingRow(nodeId, name, "inputs", spec, request, save)),
      ...capability.outputs.map((spec) => bindingRow(nodeId, name, "outputs", spec, request, save)),
    ] : [];
    return ui.make("div", {class: `request-block${messages ? " warning" : ""}`}, [
      ui.make("div", {class: "request-header"}, [
        ...(messages ? [ui.make("span", {class: "warning-mark", text: WARNING, title: messages.join("\n")})] : []),
        nameInput, capabilitySelect,
        smallButton("✕", () => tools.removeCapability(nodeId, name), "Remove this capability request"),
      ]),
      ...bindingRows,
      ...warningList(messages),
    ]);
  }

  /** One field's binding: (unbound), the declared keys (matching type first), or "+ New key..." (an unset placeholder, opened in the Knowledge panel). */
  function bindingRow(nodeId, requestName, direction, spec, request, save) {
    const knowledge = panelState.draft.knowledge;
    const bound = request[direction]?.[spec.name] ?? "";
    const matching = Object.keys(knowledge).filter((key) => knowledge[key].type === spec.type);
    const others = Object.keys(knowledge).filter((key) => knowledge[key].type !== spec.type);
    const option = (key) => ui.make("option", {value: key, text: `${key} (${knowledge[key].type})`});
    const select = ui.make("select", {}, [
      ui.make("option", {value: "", text: direction === "inputs" ? `${WARNING} (unbound: required)` : "(unbound)"}),
      ...(bound && !(bound in knowledge) ? [ui.make("option", {value: bound, text: `${WARNING} ${bound} (undeclared)`})] : []),
      ...(matching.length ? [ui.make("optgroup", {label: `${spec.type} keys`}, matching.map(option))] : []),
      ...(others.length ? [ui.make("optgroup", {label: "Other types"}, others.map(option))] : []),
      ui.make("option", {value: NEW_KEY_OPTION, text: `+ New ${spec.type} key...`}),
    ]);
    select.value = bound;
    select.addEventListener("change", async () => {
      const bindings = {...request[direction]};
      if (select.value === NEW_KEY_OPTION) {
        // Declared with no value: flagged unset (never a default that could pass for a real one) until set in the Knowledge panel
        const key = tools.uniqueKey(tools.joinKey(tools.defaultNamespace(), spec.name));
        bindings[spec.name] = key;
        const next = {inputs: {...request.inputs}, outputs: {...request.outputs}, [direction]: bindings};
        const declared = await tools.editBatch([
          {tool: "declare_key", arguments: {key, type_name: spec.type, follows_target: true}},
          {tool: "edit_capability", arguments: {node_id: nodeId, old_name: requestName, new_name: requestName,
                                                capability: request.capability, inputs: next.inputs, outputs: next.outputs}},
        ]);
        if (declared) {
          openKnowledgeEditor(key);
        }
        return;
      }
      if (select.value) {
        bindings[spec.name] = select.value;
      } else {
        delete bindings[spec.name];
      }
      save({[direction]: bindings});
    });
    return ui.make("label", {class: "binding-row"}, [
      ui.make("span", {text: `${direction === "inputs" ? "in" : "out"} ${spec.name}`, title: `${spec.type}: ${spec.description}`}),
      select,
    ]);
  }


  //==========// Edge Editors //==========//

  function edgeEditor(key, host) {
    const {source, index} = parseEdgeKey(key);
    const currentGraph = graph();
    const edge = currentGraph.edges[source][index];
    const siblingCount = currentGraph.edges[source].length;
    const priority = siblingCount > 1 ? `Checked ${ordinal(index + 1)} of ${siblingCount} from '${source}' (the first true condition wins)` : "The only edge from its node";
    if (!editable()) {
      return [
        heading("Edge (live)"),
        ui.make("p", {text: `${source} → ${edge.to}`}),
        ui.make("pre", {class: "inspector-code", text: JSON.stringify(edge.condition)}),
        ui.make("p", {class: "note", text: priority}),
      ];
    }

    const nodeIds = Object.keys(currentGraph.nodes);
    const nodeSelect = (value) => {
      const select = ui.make("select", {}, nodeIds.map((nodeId) => ui.make("option", {value: nodeId, text: nodeId})));
      select.value = value;
      select.addEventListener("change", () => apply(edge.condition));
      return select;
    };
    const fromSelect = nodeSelect(source);
    const toSelect = nodeSelect(edge.to);
    const builder = tools.conditionBuilder({rows: panelState.edge_rows?.[key] ?? null, tokens: edge.condition, onChange: (tokens) => apply(tokens)});

    async function apply(condition) {
      const newSource = fromSelect.value;
      const newKey = newSource === source ? key : `${newSource}#${(currentGraph.edges[newSource] || []).length}`;
      // Point the host at the edge's new key before the edit's state arrives (see nodeEditor's rename)
      const previousItem = host.item;
      host.item = {kind: "edge", key: newKey};
      const edited = await tools.edit("edit_edge", {source_id: source, index, new_source_id: newSource,
                                                    new_target_id: toSelect.value, condition});
      if (edited) {
        selectOnly({edges: [newKey]});
      } else {
        host.show(previousItem);
      }
    }

    async function shift(step) {
      const newKey = await shiftEdge(key, step);
      if (newKey) {
        host.item = {kind: "edge", key: newKey};
        host.refresh(true);
      }
    }

    return [
      heading("Edge"),
      field("From", fromSelect),
      field("To", toSelect),
      ui.make("div", {class: "inspector-field"}, [ui.make("span", {text: "Taken when"}), builder.element]),
      ...warningList(problems().edges[key]),
      ui.make("div", {class: "button-row"}, [
        ui.make("span", {class: "note", text: priority}),
        ...(siblingCount > 1 ? [smallButton("↑ Earlier", () => shift(-1)), smallButton("↓ Later", () => shift(1))] : []),
      ]),
      ui.buttonRow([{label: "Delete edge", onClick: () => tools.edit("remove_edge", {source_id: source, index}).then((removed) => removed && closePopover())}]),
    ];
  }

  function newEdgeEditor(item) {
    const builder = tools.conditionBuilder({rows: null, tokens: null});

    async function create() {
      const draftEdges = panelState.draft.edges;
      let targetId = item.target;
      const steps = [];
      if (targetId === null) {
        targetId = nextNodeId();
        steps.push({tool: "add_node", arguments: {node_id: targetId}},
                   {tool: "move_nodes", arguments: {positions: layoutInUnits({[targetId]: item.drop})}});
      }
      const newKey = `${item.source}#${(draftEdges[item.source] || []).length}`;
      steps.push({tool: "add_edge", arguments: {source_id: item.source, target_id: targetId, condition: builder.value()}});
      if (await tools.editBatch(steps)) {
        closePopover();
        selectOnly({edges: [newKey]});
      }
    }

    setTimeout(() => builder.element.querySelector("select, input, textarea")?.focus(), 0);
    return [
      heading("New edge"),
      ui.make("p", {text: `${item.source} → ${item.target ?? "a new node here"}`}),
      ui.make("div", {class: "inspector-field"}, [ui.make("span", {text: "Taken when"}), builder.element]),
      ui.buttonRow([{label: "Create edge", onClick: create, primary: true}, {label: "Cancel", onClick: closePopover}]),
    ];
  }

  function multipleEditor() {
    return [
      heading("Selection"),
      ui.make("p", {text: `${plural(selection.nodes.size, "node")} and ${plural(selection.edges.size, "edge")} selected.`}),
      ui.make("p", {class: "note", text: "Drag any selected node to move them together."}),
      ...(editable() ? [ui.buttonRow([{label: "Delete selection", onClick: deleteSelection}])] : []),
    ];
  }

  function overviewEditor() {
    return [
      heading(panelState.name ? `Draft: ${panelState.name}` : "Draft (unnamed)"),
      ...warningList(problems().graph),
      ui.make("p", {class: "note", text: "Select a node or edge to edit it here. Knowledge keys are in the panel on the left."}),
      heading("How to"),
      ui.make("ul", {class: "note help-list"}, [
        "Double-click blank space to add a node.",
        "Drag a node's port (●) to another node to draw an edge, or to blank space for a new node.",
        "Drag a selected edge's end handle onto another node to re-route it.",
        "Drag blank space to box-select; Shift-click to add to the selection.",
        "Middle-drag or Space+drag to pan; scroll to zoom; F to fit.",
        "Double-click, or the ✎ button, to edit in a popover; right-click for more.",
        `${WARNING} marks something to fix before pushing; hover it for why.`,
        "Enter leaves a field; with no field selected, Enter confirms.",
      ].map((text) => ui.make("li", {text}))),
    ];
  }

  function liveOverview() {
    const live = panelState.live;
    if (!live) {
      return [heading("Live mission"), ui.make("p", {class: "note", text: "No mission graph is known here for the Target yet."})];
    }
    const age = live.last_sync_age;
    return [
      heading(live.name ? `Live mission: ${live.name}` : "Live mission (unnamed)"),
      ui.make("p", {text: `Active node: ${live.active_node_id ?? "none"}${live.blocked ? " (BLOCKED)" : ""}`}),
      ui.make("p", {class: "note", text: live.overall_status}),
      ui.make("p", {class: "note", text: `Last sync with ${panelState.target}: ${age === null ? "never" : `${age.toFixed(SYNC_AGE_DECIMALS)} s ago`}`}),
      ui.make("p", {class: "note", text: "Switch to Draft and Load Live to edit a copy."}),
    ];
  }

  function liveNodeView(nodeId) {
    const live = panelState.live;
    const active = live.active_node_id === nodeId;
    const requests = Object.entries(live.graph.nodes[nodeId].capabilities).map(([name, request]) => listRow(
      `${name}: ${request.capability}${active ? ` — ${live.capability_statuses[name]?.status ?? "unknown"}` : ""}`));
    return [
      heading(`Node ${nodeId} (live)`),
      ui.make("p", {text: active ? `Active${live.blocked ? " (BLOCKED)" : ""}: ${live.overall_status}` : "Not active."}),
      heading("Capability requests"),
      ...(requests.length ? requests : [ui.make("p", {class: "note", text: "None."})]),
    ];
  }

  /** Shows `item` in the host it was clicked from: the popover follows it, the inspector selects it. */
  function focusItem(host, item) {
    if (popover && host === popover.host) {
      openPopover(item);
    } else {
      selectOnly(item.kind === "edge" ? {edges: [item.key]} : {nodes: [item.id]});
    }
  }


  //==========// Knowledge Panel //==========//

  /** Opens `key`'s inline editor in the Knowledge panel (showing the panel if collapsed). */
  function openKnowledgeEditor(key) {
    if (knowledgePanel.hidden) {
      knowledgeCollapse.setShown(true);
    }
    knowledgeHost.show({kind: "knowledge", editing: key});
    setTimeout(() => knowledgePanel.querySelector(".knowledge-editor input, .knowledge-editor select")?.focus(), 0);
  }

  const closeKnowledgeEditor = () => knowledgeHost.show({kind: "knowledge", editing: null});

  /** The panel: one row per draft key (or, in Live mode, the live mission's keys with their mesh values), plus an inline editor. */
  function buildKnowledgePanel(item) {
    const currentGraph = graph();
    if (!currentGraph) {
      return [heading("Knowledge"), ui.make("p", {class: "note", text: "No graph."})];
    }
    if (!editable()) {
      const values = panelState.live?.values || {};
      return [
        heading("Knowledge (live)"),
        ...Object.entries(currentGraph.knowledge).sort(byKey).map(([key, declaration]) => knowledgeRow(key, declaration,
          key in values ? values[key] : declaration.value, {pending: !(key in values)})),
      ];
    }
    const boundBySelection = new Set([...selection.nodes].flatMap((nodeId) =>
      Object.values(currentGraph.nodes[nodeId]?.capabilities || {}).flatMap((request) =>
        [...Object.values(request.inputs || {}), ...Object.values(request.outputs || {})])));
    const rows = Object.entries(currentGraph.knowledge).sort(byKey).map(([key, declaration]) => (item.editing === key
      ? knowledgeEditor(key, declaration)
      : knowledgeRow(key, declaration, declaration.value, {unset: panelState.unset_keys.includes(key), bound: boundBySelection.has(key),
                                                          messages: problems().keys[key], editable: true})));
    return [
      ui.make("div", {class: "knowledge-heading"}, [
        heading("Knowledge"),
        smallButton("+ Key", () => knowledgeHost.show({kind: "knowledge", editing: ""}), "Declare a new knowledge key"),
      ]),
      ...(item.editing === "" ? [knowledgeEditor(null, null)] : []),
      ...(rows.length ? rows : [ui.make("p", {class: "note", text: "No keys declared yet."})]),
    ];
  }

  /** One key's row: dimmed namespace, name, type, value; hover shows edit/remove; double-click edits. */
  function knowledgeRow(key, declaration, value, {unset = false, pending = false, bound = false, messages = null, editable: canEdit = false}) {
    const [namespace, name] = tools.splitKey(key);
    const classes = ["knowledge-row", unset ? "unset" : "", pending ? "pending" : "", bound ? "bound" : ""].filter(Boolean).join(" ");
    const shownValue = unset ? "no value yet" : ui.formatValue(value);
    return ui.make("div", {class: classes, title: messages ? messages.map((message) => `${WARNING} ${message}`).join("\n") : key,
                           ondblclick: canEdit ? () => knowledgeHost.show({kind: "knowledge", editing: key}) : null}, [
      ...(messages ? [ui.make("span", {class: "warning-mark", text: WARNING})] : []),
      ui.make("span", {class: "knowledge-key"}, [
        ...(namespace ? [ui.make("span", {class: "knowledge-namespace", text: `${namespace}/`})] : []),
        ui.make("span", {text: name}),
      ]),
      ui.make("span", {class: "knowledge-type", text: declaration.type}),
      ui.make("span", {class: "knowledge-value", text: shownValue}),
      ...(canEdit ? [ui.make("span", {class: "row-actions"}, [
        smallButton("✎", () => knowledgeHost.show({kind: "knowledge", editing: key}), "Edit"),
        smallButton("✕", () => tools.removeKnowledge(key), "Remove"),
      ])] : []),
    ]);
  }

  /** The inline editor for a key (`key` null declares a new one): namespace, name, type, value; Save is what Enter confirms. */
  function knowledgeEditor(key, declaration) {
    const types = panelState.knowledge_types;
    const [namespace, name] = key ? tools.splitKey(key) : [tools.defaultNamespace(), ""];
    const unset = key !== null && panelState.unset_keys.includes(key);
    const namespaceInput = ui.make("input", {type: "text", value: namespace, placeholder: "(none)", autocomplete: "off"});
    const nameInput = ui.make("input", {type: "text", value: name, placeholder: "name", autocomplete: "off"});
    const typeSelect = ui.make("select", {}, Object.keys(types).map((typeName) => ui.make("option", {value: typeName, text: typeName})));
    typeSelect.value = declaration?.type ?? "float";
    const valueBox = ui.make("div", {class: "knowledge-value-fields"});
    const renderValueFields = () => {
      const seed = !unset && typeSelect.value === declaration?.type ? declaration.value : undefined;
      valueBox.replaceChildren(...ui.valueFields(typeSelect.value, types, seed).map((valueField) => {
        const input = valueField.kind === "select"
          ? ui.make("select", {name: valueField.name}, valueField.options.map((text) => ui.make("option", {value: text, text})))
          : ui.make("input", {type: "text", name: valueField.name, autocomplete: "off", placeholder: unset ? "set a value" : ""});
        input.value = valueField.value;
        return field(valueField.label, input);
      }));
    };
    typeSelect.addEventListener("change", renderValueFields);
    renderValueFields();

    async function save() {
      const values = Object.fromEntries([...valueBox.querySelectorAll("[name]")].map((input) => [input.name, input.value]));
      const saved = await tools.saveKnowledge(key, {namespace: namespaceInput.value, name: nameInput.value, typeName: typeSelect.value, values});
      if (saved) {
        closeKnowledgeEditor();
      }
    }

    return ui.make("div", {class: "knowledge-editor"}, [
      ui.make("div", {class: "knowledge-name-row"}, [field("Namespace", namespaceInput), field("Name", nameInput)]),
      field("Type", typeSelect),
      valueBox,
      ...(unset ? [ui.make("p", {class: "note", text: `${WARNING} This key has no value yet; enter one to clear the warning.`})] : []),
      ui.buttonRow([{label: "Save", onClick: save, primary: true}, {label: "Cancel", onClick: closeKnowledgeEditor}]),
    ]);
  }


  //==========// Popover //==========//

  /** Where a popover points, in canvas px: a node's right edge, an edge's midpoint, or a new edge's drop point. */
  function anchorOf(item) {
    if (!panelState || !graph()) {
      return null;
    }
    if (item.kind === "node" && positions[item.id]) {
      return {x: positions[item.id].x + NODE_WIDTH / 2, y: positions[item.id].y};
    }
    if (item.kind === "edge") {
      const shape = edgeShapes(graph()).find((candidate) => candidate.row.key === item.key);
      return shape ? shape.at(0.5) : null;
    }
    if (item.kind === "new-edge") {
      return item.drop ?? (positions[item.target] && {x: positions[item.target].x + NODE_WIDTH / 2, y: positions[item.target].y});
    }
    return null;
  }

  function openPopover(item, options = {}) {
    closeMenu();
    closePopover();
    const popoverElement = ui.make("div", {class: "graph-popover", "data-enter-scope": true});
    const closeButton = ui.make("button", {type: "button", class: "small popover-close", text: "✕", title: "Close (Escape)", onclick: closePopover});
    const body = ui.make("div");
    popoverElement.append(closeButton, body);
    canvas.append(popoverElement);
    popover = {element: popoverElement, host: makeItemHost(body, buildItemEditor)};
    popover.host.show(item, options);
    positionPopover();
  }

  function openPopoverForSelection() {
    const item = selectionItem();
    if (item.kind === "node" || item.kind === "edge") {
      openPopover(item);
    }
  }

  function closePopover() {
    if (popover) {
      popover.element.remove();
      popover = null;
    }
  }

  /** Keeps the popover beside its item (as the view pans or zooms), inside the canvas. */
  function positionPopover() {
    const anchor = anchorOf(popover.host.item);
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const popoverWidth = popover.element.offsetWidth;
    const popoverHeight = popover.element.offsetHeight;
    const screen = anchor ? {x: view.x + anchor.x * view.zoom, y: view.y + anchor.y * view.zoom} : {x: width / 2, y: height / 2};
    const left = Math.min(Math.max(screen.x + POPOVER_GAP, 0), Math.max(width - popoverWidth, 0));
    const top = Math.min(Math.max(screen.y - popoverHeight / 2, 0), Math.max(height - popoverHeight, 0));
    popover.element.style.left = `${left}px`;
    popover.element.style.top = `${top}px`;
  }


  //==========// Context Menu //==========//

  function onContextMenu(event) {
    event.preventDefault();
    const target = event.target;
    const point = toCanvas(event);
    let items;
    if (target.closest("[data-node]")) {
      const nodeId = target.closest("[data-node]").dataset.node;
      if (!selection.nodes.has(nodeId)) {
        selectOnly({nodes: [nodeId]});
      }
      items = editable()
        ? [["Edit...", () => openPopover({kind: "node", id: nodeId})],
           ["Set as start", () => tools.edit("set_start_node", {node_id: nodeId})],
           ["Delete", deleteSelection]]
        : [["Inspect...", () => openPopover({kind: "node", id: nodeId})]];
    } else if (target.closest("[data-edge]")) {
      const key = target.closest("[data-edge]").dataset.edge;
      selectOnly({edges: [key]});
      items = editable()
        ? [["Edit...", () => openPopover({kind: "edge", key})],
           ["Check earlier", () => shiftEdge(key, -1)], ["Check later", () => shiftEdge(key, 1)],
           ["Delete", deleteSelection]]
        : [["Inspect...", () => openPopover({kind: "edge", key})]];
    } else {
      items = [
        ...(editable() ? [["Add node here", () => addNodeAt(point)]] : []),
        ["Select all", selectAll], ["Fit view", fitView],
      ];
    }
    const bounds = canvas.getBoundingClientRect();
    menu.replaceChildren(...items.map(([label, action]) => ui.make("button", {
      type: "button", text: label, onclick: () => { closeMenu(); action(); },
    })));
    menu.style.left = `${event.clientX - bounds.left}px`;
    menu.style.top = `${event.clientY - bounds.top}px`;
    menu.hidden = false;
  }

  function closeMenu() {
    menu.hidden = true;
  }

  function selectAll() {
    const currentGraph = graph();
    if (currentGraph) {
      selectOnly({nodes: Object.keys(currentGraph.nodes), edges: tools.edgeRows(currentGraph).map((row) => row.key)});
    }
  }

  document.addEventListener("pointerdown", (event) => {
    if (!menu.hidden && !menu.contains(event.target)) {
      closeMenu();
    }
  });


  //==========// Keyboard //==========//

  const keyboardIsOurs = () => api.isVisible() && !tools.isTyping() && !document.querySelector("dialog[open]");

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && api.isVisible() && !document.querySelector("dialog[open]")) {
      if (!menu.hidden) {
        closeMenu();
      } else if (popover) {
        closePopover();
      } else if (!tools.isTyping()) {
        clearSelection();
      }
      return;
    }
    if (!keyboardIsOurs()) {
      return;
    }
    if (event.key === " ") {
      event.preventDefault();   // pan instead of scrolling the page
      spaceHeld = true;
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      deleteSelection();
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      event.preventDefault();
      selectAll();
    } else if (event.key.toLowerCase() === "f" && !event.ctrlKey && !event.metaKey) {
      fitView();
    }
  });
  document.addEventListener("keyup", (event) => {
    if (event.key === " ") {
      spaceHeld = false;
    }
  });
  tools.bindUndoKeys(api.isVisible);


  //==========// Start //==========//

  knowledgeCollapse.setShown(knowledgeCollapse.initiallyShown);
  inspectorCollapse.setShown(inspectorCollapse.initiallyShown);

  return {
    update(state, fullState) {
      panelState = state;
      tools.updateToolbar(state, fullState);
      if (drag) {
        pendingSync = true;   // never yank nodes out from under a drag; catch up when it ends
        return;
      }
      syncFromState();
      if (!inspectorHost.item) {
        inspectorHost.show(selectionItem());
      }
    },
  };
});
