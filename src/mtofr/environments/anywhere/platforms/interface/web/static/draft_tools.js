"use strict";
/* Shared draft-editing tools for the panels that edit the window's draft (the graph editor,
   and the table Editor when it's enabled): the draft toolbar, command helpers, knowledge-key
   saving with namespaces, the condition builder, and the modal sub-forms.

       const tools = mtofr.draftTools(api, () => panelState);

   where panelState carries the EditorPanel's state fields (draft, name, draft_source, target,
   can_undo, can_redo, unset_keys, following_keys, draft_namespace, problems, edge_rows,
   target_capabilities, knowledge_types); the graph panel's state includes them. */

mtofr.draftTools = (api, getState) => {
  const ui = mtofr.ui;
  const DEFAULT_SAVE_FILE_NAME = "mission.json";
  const DEFAULT_KNOWLEDGE_TYPE = "float";
  const CONDITION_PLACEHOLDER = '["ugv1/arrived", "==", true]';
  const CONDITION_LABEL = "Condition (JSON tokens; true/false/null, not Python's True/False/None)";
  const NAMESPACE_SEPARATOR = "/";
  const NUMBER_TYPES = ["float", "int"];
  const EQUALITY_TYPES = ["bool", "str"];
  const ORDER_OPERATORS = ["==", "!=", "<", "<=", ">", ">="];
  const EQUALITY_OPERATORS = ["==", "!="];
  const IS_NONE = "is None";
  const IS_NOT_NONE = "is not None";
  const WARNING = "⚠";   // ⚠

  const draft = () => getState().draft;


  //==========// Commands //==========//

  /** Runs a command, alerting on failure; resolves to its reply. */
  async function run(command, args = {}) {
    return ui.reportFailure(await api.command(command, args));
  }

  /** Runs one step (a DraftToolbox tool or an editor step) on the draft, alerting on failure; resolves to whether it succeeded. */
  async function edit(tool, args) {
    return (await run("edit", {tool, arguments: args})).ok;
  }

  /** Runs several steps as one atomic, single-undo edit (see EditorPanel.edit_batch); resolves to whether it succeeded. */
  async function editBatch(steps) {
    return (await run("edit_batch", {steps})).ok;
  }


  //==========// Keys and Namespaces //==========//

  /** A key as [namespace, name], split at its last "/" ("" namespace if it has none). */
  function splitKey(key) {
    const split = key.lastIndexOf(NAMESPACE_SEPARATOR);
    return split < 0 ? ["", key] : [key.slice(0, split), key.slice(split + 1)];
  }

  const joinKey = (namespace, name) => (namespace ? `${namespace}${NAMESPACE_SEPARATOR}${name}` : name);

  /** `key`, or key_2, key_3, ... if the draft already declares it. */
  function uniqueKey(key) {
    let candidate = key;
    let number = 2;
    while (candidate in draft().knowledge) {
      candidate = `${key}_${number}`;
      number += 1;
    }
    return candidate;
  }

  /** The default namespace for new keys: the Target's id ("" if no Target). */
  const defaultNamespace = () => getState().target ?? "";

  /** Saves a knowledge declaration as one undo step: a new key (`oldKey` null), or an edit (rename
      if the key changed, then the type/value, then the follows-Target flag). The key follows the
      Target exactly when its namespace was left at the default. Resolves to the saved key or null. */
  async function saveKnowledge(oldKey, {namespace, name, typeName, values}) {
    const key = joinKey(namespace.trim(), name.trim());
    const value = ui.valueFromForm(typeName, getState().knowledge_types, values);
    const followsTarget = namespace.trim() === defaultNamespace();
    const steps = oldKey === null
      ? [{tool: "declare_key", arguments: {key, type_name: typeName, value, follows_target: followsTarget}}]
      : [
        ...(key !== oldKey ? [{tool: "rename_knowledge_key", arguments: {old_key: oldKey, new_key: key}}] : []),
        {tool: "edit_knowledge_key", arguments: {key, type: typeName, value}},
        {tool: "set_key_flags", arguments: {key, follows_target: followsTarget}},
      ];
    return (await editBatch(steps)) ? key : null;
  }

  const removeKnowledge = (key) => edit("remove_knowledge_key", {key});


  //==========// Toolbar //==========//

  const fileInput = ui.make("input", {type: "file", accept: ".json,application/json", hidden: true, onchange: loadFile});
  const undoButton = ui.make("button", {type: "button", text: "↶ Undo", title: "Undo (Ctrl+Z)", onclick: () => run("undo")});   // ↶
  const redoButton = ui.make("button", {type: "button", text: "↷ Redo", title: "Redo (Ctrl+Y)", onclick: () => run("redo")});   // ↷
  const nameInput = ui.make("input", {type: "text", class: "mission-name", placeholder: "Mission name", autocomplete: "off",
                                      title: "The mission's name; a named mission keeps its layout when pushed and loaded back",
                                      onchange: () => edit("set_mission_name", {name: nameInput.value})});
  const retargetButton = ui.make("button", {type: "button", hidden: true, onclick: () => run("retarget"),
                                            title: "Rename the keys whose namespace was left at the default into the current Target's namespace"});
  const sourceNote = ui.make("span", {class: "note"});
  const toolbar = ui.make("div", {class: "button-row"}, [
    ui.make("label", {class: "mission-name-label"}, ["Mission ", nameInput]),
    ui.make("button", {type: "button", text: "Load Live", title: "Draft a copy of the Target's mission", onclick: () => run("load_live")}),
    ui.make("button", {type: "button", text: "New Blank", onclick: () => run("new_blank")}),
    ui.make("button", {type: "button", text: "Load File...", onclick: () => fileInput.click()}),
    ui.make("button", {type: "button", text: "Save File...", onclick: saveFile}),
    undoButton, redoButton,
    ui.make("button", {type: "button", text: "Validate", onclick: validate}),
    ui.make("button", {type: "button", text: "Push to Target", onclick: () => run("push")}),
    retargetButton, sourceNote, fileInput,
  ]);

  async function loadFile() {
    const file = fileInput.files[0];
    fileInput.value = "";   // so choosing the same file again still fires change
    if (file) {
      run("load_file", {text: await file.text(), file_name: file.name});
    }
  }

  async function saveFile() {
    const values = await ui.formDialog("Save Draft", () => [
      {name: "file_name", label: "File name", value: getState().name ? `${getState().name}.json` : DEFAULT_SAVE_FILE_NAME},
    ]);
    if (!values) {
      return;
    }
    const result = await run("save_file");
    if (result.ok) {
      const link = ui.make("a", {href: URL.createObjectURL(new Blob([result.text], {type: "application/json"})), download: values.file_name});
      link.click();
      URL.revokeObjectURL(link.href);
    }
  }

  async function validate() {
    const result = await run("validate");
    if (result.ok) {
      alert(result.message);
    }
  }

  /** Refreshes the toolbar from the latest state (leaving the name field alone while it's being typed in). */
  function updateToolbar(state, fullState) {
    undoButton.disabled = !state.can_undo;
    redoButton.disabled = !state.can_redo;
    if (document.activeElement !== nameInput) {
      nameInput.value = state.name;
    }
    const retargetable = state.draft_namespace !== null && state.target !== null && state.draft_namespace !== state.target;
    retargetButton.hidden = !retargetable;
    retargetButton.textContent = retargetable ? `Retarget keys ${state.draft_namespace}/ → ${state.target}/` : "";
    const source = state.draft_source ? `loaded from '${state.draft_source}'` : "not loaded from a platform";
    const mismatch = state.draft_source && state.draft_source !== fullState.target ? " (differs from the Target!)" : "";
    sourceNote.textContent = `Draft ${source}${mismatch}`;
  }

  /** Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z while isActive() and no field or dialog has the keyboard. */
  function bindUndoKeys(isActive) {
    document.addEventListener("keydown", (event) => {
      if (!isActive() || isTyping() || document.querySelector("dialog[open]") || !(event.ctrlKey || event.metaKey)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "z" && !event.shiftKey) {
        event.preventDefault();
        run("undo");
      } else if (key === "y" || (key === "z" && event.shiftKey)) {
        event.preventDefault();
        run("redo");
      }
    });
  }

  /** Whether a text field currently has the keyboard. */
  const isTyping = () => ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);


  //==========// Condition Builder //==========//

  /** The operators that make sense for a key of `typeName`. */
  function operatorsFor(typeName) {
    if (NUMBER_TYPES.includes(typeName)) {
      return [...ORDER_OPERATORS, IS_NONE, IS_NOT_NONE];
    }
    if (EQUALITY_TYPES.includes(typeName)) {
      return [...EQUALITY_OPERATORS, IS_NONE, IS_NOT_NONE];
    }
    return [IS_NONE, IS_NOT_NONE];   // a compound value (e.g. Location) is only ever checked for None
  }

  /** A neutral literal of `typeName` for a fresh row. */
  const defaultLiteral = (typeName) => (typeName === "bool" ? true : NUMBER_TYPES.includes(typeName) ? 0 : "");

  /** One row's tokens: [not] key op value, or [not] key is [not] None. */
  function rowTokens(row) {
    const negation = row.negated ? ["not"] : [];
    if (row.operator === IS_NONE) {
      return [...negation, row.key, "is", null];
    }
    if (row.operator === IS_NOT_NONE) {
      return [...negation, row.key, "is", "not", null];
    }
    return [...negation, row.key, row.operator, row.value];
  }

  /** Builds the graphical condition editor: rows of [not] [key] [operator] [value], joined by one
      Match all/any switch, or a raw-token "Advanced" box for anything the rows can't express.
      `rows` is the server's condition_rows() (null opens Advanced with `tokens`). `onChange(tokens)`
      runs on every committed change when given (an existing edge applies as you edit); a new edge
      reads value() instead. Returns {element, value()}. */
  function conditionBuilder({rows, tokens, onChange}) {
    const knowledge = draft().knowledge;
    const keys = Object.keys(knowledge);
    const typeOf = (key) => knowledge[key]?.type;
    const freshRow = () => {
      const key = keys[0] ?? "";
      return {key, operator: operatorsFor(typeOf(key))[0], value: defaultLiteral(typeOf(key)), negated: false};
    };
    const model = {
      match: rows?.match ?? "all",
      rows: rows ? rows.rows.map((row) => ({...row})) : (tokens && tokens.length ? [] : [freshRow()]),
      advanced: !rows && Boolean(tokens && tokens.length),
      raw: JSON.stringify(tokens ?? []),
    };
    const element = ui.make("div", {class: "condition-builder"});

    const value = () => (model.advanced ? model.raw : model.rows.flatMap((row, index) =>
      [...(index > 0 ? [model.match === "any" ? "or" : "and"] : []), ...rowTokens(row)]));
    const changed = () => {
      render();
      if (onChange) {
        onChange(value());
      }
    };

    function keySelect(row) {
      const options = keys.map((key) => ui.make("option", {value: key, text: `${key} (${typeOf(key)})`}));
      if (row.key && !keys.includes(row.key)) {
        options.unshift(ui.make("option", {value: row.key, text: `${WARNING} ${row.key} (undeclared)`}));
      }
      if (options.length === 0) {
        options.push(ui.make("option", {value: "", text: "(declare a key first)"}));
      }
      const select = ui.make("select", {class: "condition-key"}, options);
      select.value = row.key;
      select.addEventListener("change", () => {
        row.key = select.value;
        const operators = operatorsFor(typeOf(row.key));
        if (!operators.includes(row.operator)) {
          row.operator = operators[0];
        }
        row.value = defaultLiteral(typeOf(row.key));
        changed();
      });
      return select;
    }

    function operatorSelect(row) {
      const select = ui.make("select", {class: "condition-operator"},
        operatorsFor(typeOf(row.key)).map((operator) => ui.make("option", {value: operator, text: operator})));
      select.value = row.operator;
      select.addEventListener("change", () => { row.operator = select.value; changed(); });
      return select;
    }

    function valueInput(row) {
      const typeName = typeOf(row.key);
      if (row.operator === IS_NONE || row.operator === IS_NOT_NONE) {
        return ui.make("span");
      }
      if (typeName === "bool") {
        const select = ui.make("select", {class: "condition-value"}, ["true", "false"].map((text) => ui.make("option", {value: text, text})));
        select.value = String(row.value === true);
        select.addEventListener("change", () => { row.value = select.value === "true"; changed(); });
        return select;
      }
      const numeric = NUMBER_TYPES.includes(typeName);
      const input = ui.make("input", {class: "condition-value", type: numeric ? "number" : "text", step: numeric ? "any" : null});
      input.value = row.value ?? "";
      input.addEventListener("change", () => {
        row.value = numeric ? Number(input.value || 0) : input.value;
        changed();
      });
      return input;
    }

    function render() {
      if (model.advanced) {
        const area = ui.make("textarea", {rows: 3, class: "condition-raw", placeholder: CONDITION_PLACEHOLDER});
        area.value = model.raw;
        area.addEventListener("change", () => { model.raw = area.value; changed(); });
        element.replaceChildren(
          ui.make("span", {class: "note", text: CONDITION_LABEL}), area,
          ui.make("button", {type: "button", class: "small link", text: "Use the row editor",
                             title: "Back to rows (rows can't express nested and/or; such a condition stays in tokens)",
                             onclick: () => { model.advanced = false; if (model.rows.length === 0) { model.rows = [freshRow()]; } render(); }}),
        );
        return;
      }
      const rowElements = model.rows.map((row, index) => ui.make("div", {class: "condition-row"}, [
        ui.make("label", {class: "condition-not", title: "Negate this check"}, [
          ui.make("input", {type: "checkbox", checked: row.negated, onchange: (event) => { row.negated = event.target.checked; changed(); }}),
          " not",
        ]),
        keySelect(row), operatorSelect(row), valueInput(row),
        ui.make("button", {type: "button", class: "small", text: "✕", title: "Remove this check",
                           onclick: () => { model.rows.splice(index, 1); changed(); }}),
      ]));
      const matchSelect = ui.make("select", {}, [
        ui.make("option", {value: "all", text: "all of (and)"}), ui.make("option", {value: "any", text: "any of (or)"}),
      ]);
      matchSelect.value = model.match;
      matchSelect.addEventListener("change", () => { model.match = matchSelect.value; changed(); });
      element.replaceChildren(
        ...(model.rows.length > 1 ? [ui.make("label", {class: "condition-match"}, ["True when ", matchSelect, " these hold:"])] : []),
        ...rowElements,
        ui.make("div", {class: "button-row"}, [
          ui.make("button", {type: "button", class: "small", text: "+ Check", onclick: () => { model.rows.push(freshRow()); changed(); }}),
          ui.make("button", {type: "button", class: "small link", text: "Advanced (tokens)",
                             onclick: () => { model.raw = JSON.stringify(value()); model.advanced = true; render(); }}),
        ]),
      );
    }

    render();
    return {element, value};
  }


  //==========// Capability Requests (modal form, used by the table Editor) //==========//

  const formatBindings = (bindings) => Object.entries(bindings || {}).map(([field, key]) => `${field}=${key}`).join(", ");

  /** The capability-request form: name, capability, then one binding select per input/output field of the chosen capability. */
  function capabilityFields(existing) {
    const capabilities = getState().target_capabilities;
    const keyOptions = [{value: "", label: "(unbound)"}].concat(
      Object.keys(draft().knowledge).map((key) => ({value: key, label: `${key} (${draft().knowledge[key].type})`})));
    return (values) => {
      const capabilityName = values.capability ?? existing?.request.capability ?? capabilities[0].ipl_type;
      const capability = capabilities.find((candidate) => candidate.ipl_type === capabilityName) || capabilities[0];
      const bindingFields = (direction, specs, bindings) => specs.map((spec) => ({
        name: `${direction}:${spec.name}`, kind: "select", options: keyOptions,
        label: `${direction === "inputs" ? "Input" : "Output"} ${spec.name} (${spec.type}): ${spec.description}`,
        value: bindings?.[spec.name] ?? "",
      }));
      return [
        {name: "request_name", label: "Request name", value: existing?.name ?? ""},
        {name: "capability", label: "Capability", kind: "select", value: capability.ipl_type,
         options: capabilities.map((candidate) => ({value: candidate.ipl_type, label: `${candidate.ipl_type}: ${candidate.description}`}))},
        ...bindingFields("inputs", capability.inputs, existing?.request.inputs),
        ...bindingFields("outputs", capability.outputs, existing?.request.outputs),
      ];
    };
  }

  /** The bound fields of one direction ("inputs"/"outputs") from a capability form's answers; unbound fields are dropped. */
  function bindingsFrom(values, direction) {
    const prefix = `${direction}:`;
    return Object.fromEntries(Object.entries(values)
      .filter(([name, key]) => name.startsWith(prefix) && key !== "")
      .map(([name, key]) => [name.slice(prefix.length), key]));
  }

  /** Prompts for a capability request (new, or editing `existing` = {name, request}); resolves to the answers or null. */
  async function promptCapability(title, existing) {
    const capabilities = getState().target_capabilities;
    if (!capabilities) {
      alert("The Target's capabilities aren't known here yet (pick a Target, and wait for a sync).");
      return null;
    }
    if (capabilities.length === 0) {
      alert("The Target advertises no capabilities.");
      return null;
    }
    return ui.formDialog(title, capabilityFields(existing));
  }

  async function addCapability(nodeId) {
    const values = await promptCapability(`Add Capability Request to '${nodeId}'`, null);
    return values !== null && edit("add_capability", {
      node_id: nodeId, request_name: values.request_name, capability: values.capability,
      inputs: bindingsFrom(values, "inputs"), outputs: bindingsFrom(values, "outputs"),
    });
  }

  async function editCapability(nodeId, name) {
    const request = draft().nodes[nodeId]?.capabilities[name];
    if (!request) {
      return false;
    }
    const values = await promptCapability(`Edit Capability Request on '${nodeId}'`, {name, request});
    return values !== null && edit("edit_capability", {
      node_id: nodeId, old_name: name, new_name: values.request_name, capability: values.capability,
      inputs: bindingsFrom(values, "inputs"), outputs: bindingsFrom(values, "outputs"),
    });
  }

  const removeCapability = (nodeId, name) => edit("remove_capability", {node_id: nodeId, request_name: name});


  //==========// Edges (modal form, used by the table Editor) //==========//

  /** Every edge as {key: "source#index", source, index, edge}, in draft order (first match wins). */
  const edgeRows = (graph = draft()) => Object.entries(graph.edges).flatMap(([source, edges]) =>
    edges.map((edge, index) => ({key: `${source}#${index}`, source, index, edge})));

  /** Prompts for an edge (new, or editing `existing` row); the condition is a JSON token list. */
  function promptEdge(title, existing, defaultSource) {
    const nodeIds = Object.keys(draft().nodes);
    if (nodeIds.length === 0) {
      alert("Add a node first.");
      return Promise.resolve(null);
    }
    return ui.formDialog(title, () => [
      {name: "source_id", label: "From", kind: "select", options: nodeIds, value: existing?.source ?? defaultSource},
      {name: "target_id", label: "To", kind: "select", options: nodeIds, value: existing?.edge.to},
      {name: "condition", label: CONDITION_LABEL, kind: "textarea",
       placeholder: CONDITION_PLACEHOLDER, value: existing ? JSON.stringify(existing.edge.condition) : ""},
    ]);
  }


  //==========// Knowledge (modal form, used by the table Editor) //==========//

  /** Prompts for a declaration (new, or editing `existing` = {key, declaration}): namespace, name, type, then that type's value fields. */
  function promptKnowledge(title, existing) {
    const types = getState().knowledge_types;
    const [namespace, name] = existing ? splitKey(existing.key) : [defaultNamespace(), ""];
    return ui.formDialog(title, (values) => {
      const typeName = values.type ?? existing?.declaration.type ?? DEFAULT_KNOWLEDGE_TYPE;
      const seed = typeName === existing?.declaration.type ? existing.declaration.value : undefined;
      return [
        {name: "namespace", label: "Namespace (default: the Target)", value: namespace},
        {name: "name", label: "Name", value: name},
        {name: "type", label: "Type", kind: "select", options: Object.keys(types), value: typeName},
        ...ui.valueFields(typeName, types, seed),
      ];
    });
  }

  async function addKnowledge() {
    const values = await promptKnowledge("Add Knowledge Key", null);
    return values !== null && saveKnowledge(null, {namespace: values.namespace, name: values.name, typeName: values.type, values});
  }

  /** Edits a declaration; resolves to its (possibly renamed) key, or null if nothing changed. */
  async function editKnowledge(key) {
    const declaration = draft().knowledge[key];
    if (!declaration) {
      return null;
    }
    const values = await promptKnowledge("Edit Knowledge Key", {key, declaration});
    return values === null ? null : saveKnowledge(key, {namespace: values.namespace, name: values.name, typeName: values.type, values});
  }


  return {
    toolbar, updateToolbar, bindUndoKeys, isTyping, run, edit, editBatch,
    splitKey, joinKey, uniqueKey, defaultNamespace, saveKnowledge, removeKnowledge,
    conditionBuilder, WARNING,
    formatBindings, addCapability, editCapability, removeCapability,
    edgeRows, promptEdge, CONDITION_LABEL, CONDITION_PLACEHOLDER,
    addKnowledge, editKnowledge,
  };
};
