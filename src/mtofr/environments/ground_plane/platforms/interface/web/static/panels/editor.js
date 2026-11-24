"use strict";
/* Editor panel (web/panels/editor.py): one draft mission graph as tables, edited through the
   same DraftToolbox tools the LLM assistant uses, then pushed to the Target as a mesh write.
   The toolbar and sub-forms are the shared mtofr.draftTools (static/draft_tools.js). */

mtofr.registerPanel("editor", (element, api) => {
  const ui = mtofr.ui;
  const START_NODE_MARKER = " *";
  let panelState = null;
  const tools = mtofr.draftTools(api, () => panelState);
  const {edit} = tools;

  const draft = () => panelState.draft;
  const nodeIds = () => Object.keys(draft().nodes);
  const knowledgeKeys = () => Object.keys(draft().knowledge);
  const problems = () => panelState.problems;
  /** "⚠ " when `messages` is non-empty, so a row with problems stands out. */
  const flag = (messages) => (messages && Object.keys(messages).length ? `${tools.WARNING} ` : "");


  //==========// Nodes //==========//

  const nodeTable = ui.createTable({
    columns: [
      {label: "Node", value: (nodeId) => flag(problems().requests[nodeId]) + nodeId + (nodeId === draft().start ? START_NODE_MARKER : "")},
      {label: "Capabilities", value: (nodeId) => Object.keys(draft().nodes[nodeId].capabilities).length},
    ],
    rowKey: (nodeId) => nodeId,
    onSelect: () => renderCapabilities(),
    onActivate: () => renameNode(),
  });

  async function addNode() {
    const values = await ui.formDialog("Add Node", () => [{name: "node_id", label: "Node id"}]);
    if (values && await edit("add_node", {node_id: values.node_id})) {
      nodeTable.setSelected(values.node_id);   // ready for Add Capability straight away
    }
  }

  async function renameNode() {
    const oldId = nodeTable.selectedKey;
    if (!oldId) {
      return;
    }
    const values = await ui.formDialog("Rename Node", () => [{name: "new_id", label: "New node id", value: oldId}]);
    if (values && await edit("rename_node", {old_id: oldId, new_id: values.new_id})) {
      nodeTable.setSelected(values.new_id);
    }
  }

  const removeNode = () => nodeTable.selectedKey && edit("remove_node", {node_id: nodeTable.selectedKey});
  const setStartNode = () => nodeTable.selectedKey && edit("set_start_node", {node_id: nodeTable.selectedKey});


  //==========// Capability Requests (on the selected node) //==========//

  const selectedRequests = () => (draft().nodes[nodeTable.selectedKey] || {capabilities: {}}).capabilities;

  const capabilityTable = ui.createTable({
    columns: [
      {label: "Name", value: (name) => flag(problems().requests[nodeTable.selectedKey]?.[name]) + name},
      {label: "Capability", value: (name) => selectedRequests()[name].capability},
      {label: "Inputs", value: (name) => tools.formatBindings(selectedRequests()[name].inputs)},
      {label: "Outputs", value: (name) => tools.formatBindings(selectedRequests()[name].outputs)},
    ],
    rowKey: (name) => name,
    onActivate: () => editCapability(),
    emptyText: "(select a node)",
  });
  const capabilityHeading = ui.make("h3", {text: "Capabilities"});

  function addCapability() {
    if (!nodeTable.selectedKey) {
      alert("Select a node first.");
      return;
    }
    tools.addCapability(nodeTable.selectedKey);
  }

  function editCapability() {
    if (selectedRequests()[capabilityTable.selectedKey]) {
      tools.editCapability(nodeTable.selectedKey, capabilityTable.selectedKey);
    }
  }

  function removeCapability() {
    if (selectedRequests()[capabilityTable.selectedKey]) {
      tools.removeCapability(nodeTable.selectedKey, capabilityTable.selectedKey);
    }
  }

  function renderCapabilities() {
    capabilityHeading.textContent = nodeTable.selectedKey && draft().nodes[nodeTable.selectedKey]
      ? `Capabilities on '${nodeTable.selectedKey}'` : "Capabilities";
    capabilityTable.setRows(Object.keys(selectedRequests()));
  }


  //==========// Edges //==========//

  const edgeTable = ui.createTable({
    columns: [
      {label: "From", value: (row) => flag(problems().edges[row.key]) + row.source},
      {label: "#", value: (row) => row.index + 1},
      {label: "To", value: (row) => row.edge.to},
      {label: "Condition", value: (row) => JSON.stringify(row.edge.condition)},
    ],
    rowKey: (row) => row.key,
    onActivate: () => editEdge(),
  });
  const selectedEdge = () => tools.edgeRows().find((candidate) => candidate.key === edgeTable.selectedKey);

  async function addEdge() {
    const values = await tools.promptEdge("Add Edge", null, nodeTable.selectedKey);
    if (values) {
      edit("add_edge", {source_id: values.source_id, target_id: values.target_id, condition: values.condition});
    }
  }

  async function editEdge() {
    const row = selectedEdge();
    if (!row) {
      return;
    }
    const values = await tools.promptEdge("Edit Edge", row);
    if (values) {
      edit("edit_edge", {source_id: row.source, index: row.index, new_source_id: values.source_id,
                         new_target_id: values.target_id, condition: values.condition});
    }
  }

  function removeEdge() {
    const row = selectedEdge();
    if (row) {
      edit("remove_edge", {source_id: row.source, index: row.index});
    }
  }

  /** Moves the selected edge one step earlier (-1) or later (+1) in its source's priority order. */
  async function shiftEdge(step) {
    const row = selectedEdge();
    const newIndex = row ? row.index + step : -1;
    if (!row || newIndex < 0 || newIndex >= draft().edges[row.source].length) {
      return;
    }
    if ((await tools.run("move_edge", {source_id: row.source, index: row.index, new_index: newIndex})).ok) {
      edgeTable.setSelected(`${row.source}#${newIndex}`);
    }
  }


  //==========// Knowledge (the draft's declarations) //==========//

  const knowledgeTable = ui.createTable({
    columns: [
      {label: "Key", value: (key) => flag(problems().keys[key]) + key},
      {label: "Type", value: (key) => draft().knowledge[key].type},
      {label: "Value", value: (key) => ui.formatValue(draft().knowledge[key].value)},
    ],
    rowKey: (key) => key,
    onActivate: () => editKnowledge(),
  });

  async function editKnowledge() {
    const editedKey = await tools.editKnowledge(knowledgeTable.selectedKey);
    if (editedKey) {
      knowledgeTable.setSelected(editedKey);
    }
  }

  function removeKnowledge() {
    if (draft().knowledge[knowledgeTable.selectedKey]) {
      tools.removeKnowledge(knowledgeTable.selectedKey);
    }
  }


  //==========// Layout //==========//

  /** One titled section: a heading, Add/Edit/Remove-style buttons, and a scrolling table. */
  const section = (heading, buttons, tableElement) => ui.make("div", {class: "editor-section"}, [
    typeof heading === "string" ? ui.make("h3", {text: heading}) : heading,
    ui.buttonRow(buttons),
    ui.make("div", {class: "table-scroll"}, tableElement),
  ]);

  element.append(tools.toolbar, ui.make("div", {class: "editor-grid"}, [
    section("Nodes", [
      {label: "Add", onClick: addNode}, {label: "Rename", onClick: renameNode},
      {label: "Remove", onClick: removeNode}, {label: "Set Start", onClick: setStartNode},
    ], nodeTable.element),
    section(capabilityHeading, [
      {label: "Add", onClick: addCapability}, {label: "Edit", onClick: editCapability}, {label: "Remove", onClick: removeCapability},
    ], capabilityTable.element),
    section("Edges (# = priority; first true condition wins)", [
      {label: "Add", onClick: addEdge}, {label: "Edit", onClick: editEdge}, {label: "Remove", onClick: removeEdge},
      {label: "↑ Up", onClick: () => shiftEdge(-1)}, {label: "↓ Down", onClick: () => shiftEdge(1)},   // ↑ ↓
    ], edgeTable.element),
    section("Knowledge", [
      {label: "Add", onClick: () => tools.addKnowledge()}, {label: "Edit", onClick: editKnowledge}, {label: "Remove", onClick: removeKnowledge},
    ], knowledgeTable.element),
  ]));

  tools.bindUndoKeys(api.isVisible);

  return {
    update(state, fullState) {
      panelState = state;
      tools.updateToolbar(state, fullState);
      nodeTable.setRows(nodeIds());
      renderCapabilities();
      edgeTable.setRows(tools.edgeRows());
      knowledgeTable.setRows(knowledgeKeys());
    },
  };
});
