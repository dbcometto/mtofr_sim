"use strict";
/* Core of the interface platform's web UI (web/panel.py is the Python half of the seam).
   Polls /api/state, owns the Target dropdown, the tabs, and the console, and hosts panels:
   each panel's script calls

       mtofr.registerPanel(name, (element, api) => { ...build inside element...; return {update(panelState, state) {...}}; });

   where api = {command(command, args) -> Promise<{ok, message, ...}>, isVisible(), refresh()},
   and mtofr.ui holds shared helpers (tables, the form dialog, knowledge-value forms). */


//==========// Config //==========//

const POLL_INTERVAL_MS = 1000;
const AT_BOTTOM_TOLERANCE_PX = 4;   // console scroll offset still counted as "at the bottom"
const TAB_STORAGE_KEY = "mtofr.selectedTab";
const SESSION_STORAGE_KEY = "mtofr.sessionId";
const SESSION_HEADER = "X-Session-Id";
const SYNC_AGE_DECIMALS = 1;
const VALUE_FIELD_PREFIX = "value:";   // form-field name prefix for a knowledge value's fields
const BOOL_TEXTS = ["true", "false"];



//==========// Session //==========//

/** This window's session id: kept in sessionStorage, so a reload keeps the same Target, draft,
    and undo history, while a new tab gets its own. */
const SESSION_ID = (() => {
  let sessionId = null;
  try {
    sessionId = sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch (error) {
    // NOTE: storage can be unavailable (private window, blocked site data); the session then lasts one page load.
  }
  if (!sessionId) {
    sessionId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    } catch (error) {
      // NOTE: see above
    }
  }
  return sessionId;
})();



//==========// Server Calls //==========//

/** GETs `path` as JSON, as this window's session. */
async function getJson(path) {
  const response = await fetch(path, {cache: "no-store", headers: {[SESSION_HEADER]: SESSION_ID}});
  return response.json();
}

/** POSTs `body` to `path` as JSON, as this window's session; resolves to the reply (or a failed one if the server is unreachable). */
async function postJson(path, body) {
  try {
    const response = await fetch(path, {
      method: "POST", headers: {"Content-Type": "application/json", [SESSION_HEADER]: SESSION_ID},
      body: JSON.stringify(body),
    });
    return await response.json();
  } catch (error) {
    return {ok: false, message: `Could not reach the interface platform: ${error}`};
  }
}



//==========// UI Helpers (mtofr.ui) //==========//

/** Builds an element: attributes ("text" sets textContent, "on<event>" adds a listener, true/false toggles) and children. */
function make(tag, attributes = {}, children = []) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "text") {
      element.textContent = value;
    } else if (name.startsWith("on")) {
      element.addEventListener(name.slice(2), value);
    } else if (value === true) {
      element.setAttribute(name, "");
    } else if (value !== false && value !== null && value !== undefined) {
      element.setAttribute(name, value);
    }
  }
  element.append(...[].concat(children));
  return element;
}

/** A row of buttons: [{label, onClick, disabled, primary}]. A primary button is what Enter presses
    when no field has the keyboard (see the Enter handling below). */
function buttonRow(buttons) {
  return make("div", {class: "button-row"},
    buttons.map(({label, onClick, disabled, primary, title}) => make("button", {
      type: "button", onclick: onClick, disabled: !!disabled, text: label, title, "data-primary": !!primary,
    })));
}

/** A persistent table: columns [{label, value(row)}], one <tr> per row keyed by rowKey(row) (a string).
    setRows() reconciles by key, reusing each row's element and touching only changed cells, so a
    poll never interrupts a double-click or resets scrolling. Click selects; double-click activates.
    `rowClass(row)` optionally gives each row a class (e.g. "pending").
    Returns {element, setRows(rows), setSelected(key), selectedKey}. */
function createTable({columns, rowKey, onSelect, onActivate, rowClass, emptyText = "(none)"}) {
  const body = make("tbody");
  const element = make("table", {}, [
    make("thead", {}, make("tr", {}, columns.map((column) => make("th", {text: column.label})))),
    body,
  ]);
  const emptyRow = make("tr", {class: "empty"}, make("td", {colspan: columns.length, text: emptyText}));
  let rowElements = new Map();   // key -> <tr>, in display order
  let selectedKey = null;

  function applySelection() {
    for (const [key, rowElement] of rowElements) {
      rowElement.classList.toggle("selected", key === selectedKey);
    }
  }

  function setSelected(key) {
    selectedKey = key;
    applySelection();
  }

  function setRows(rows) {
    const nextElements = new Map();
    for (const row of rows) {
      const key = rowKey(row);
      const rowElement = rowElements.get(key) || make("tr", {"data-key": key}, columns.map(() => make("td")));
      rowElement.className = rowClass ? rowClass(row) || "" : "";   // applySelection() re-adds "selected" below
      columns.forEach((column, index) => {
        const text = String(column.value(row));
        if (rowElement.cells[index].textContent !== text) {
          rowElement.cells[index].textContent = text;
        }
      });
      nextElements.set(key, rowElement);
    }
    rowElements = nextElements;
    const desired = rows.length > 0 ? [...nextElements.values()] : [emptyRow];
    desired.forEach((rowElement, index) => {
      if (body.children[index] !== rowElement) {
        body.insertBefore(rowElement, body.children[index] || null);
      }
    });
    while (body.children.length > desired.length) {
      body.lastElementChild.remove();
    }
    applySelection();
  }

  /** The keyed row an event happened in, or null. */
  function keyOf(event) {
    const rowElement = event.target.closest("tr[data-key]");
    return rowElement ? rowElement.dataset.key : null;
  }

  body.addEventListener("click", (event) => {
    const key = keyOf(event);
    if (key !== null) {
      setSelected(key);
      if (onSelect) {
        onSelect(key);
      }
    }
  });
  body.addEventListener("dblclick", (event) => {
    const key = keyOf(event);
    if (key !== null && onActivate) {
      onActivate(key);
    }
  });

  return {
    element,
    setRows,
    setSelected,
    get selectedKey() { return selectedKey; },
  };
}

/** A knowledge value as short text: "x=1, y=2" for a field dict, else the value itself. */
function formatValue(value) {
  if (value !== null && typeof value === "object") {
    return Object.entries(value).map(([name, fieldValue]) => `${name}=${fieldValue}`).join(", ");
  }
  return String(value);
}

/** The modal form every panel uses. buildFields(values) returns
    [{name, label, kind: "text"|"select"|"textarea", options: [string | {value, label}], value, placeholder}]
    and is re-run whenever a select changes, so fields can depend on earlier answers.
    Resolves to {name: text} on OK, or null on Cancel/Escape. */
function formDialog(title, buildFields) {
  const dialog = document.getElementById("form-dialog");
  const fieldsElement = document.getElementById("form-dialog-fields");
  document.getElementById("form-dialog-title").textContent = title;
  const values = {};

  function collect() {
    for (const input of fieldsElement.querySelectorAll("[name]")) {
      values[input.name] = input.value;
    }
  }

  function render() {
    fieldsElement.replaceChildren();
    for (const field of buildFields(values)) {
      const id = `form-field-${field.name}`;
      let input;
      if (field.kind === "select") {
        const options = field.options.map((option) => typeof option === "string" ? {value: option, label: option} : option);
        input = make("select", {id, name: field.name, onchange: () => { collect(); render(); }},
          options.map((option) => make("option", {value: option.value, text: option.label})));
      } else if (field.kind === "textarea") {
        input = make("textarea", {id, name: field.name, rows: 3, placeholder: field.placeholder});
      } else {
        input = make("input", {id, name: field.name, type: "text", placeholder: field.placeholder, autocomplete: "off"});
      }
      input.value = values[field.name] ?? field.value ?? "";
      fieldsElement.append(make("label", {for: id, text: field.label}), input);
    }
  }

  render();
  return new Promise((resolve) => {
    document.getElementById("form-dialog-cancel").onclick = () => dialog.close("cancel");
    dialog.onclose = () => {
      collect();
      resolve(dialog.returnValue === "ok" ? values : null);
    };
    dialog.returnValue = "";
    dialog.showModal();
    const firstInput = fieldsElement.querySelector("[name]");
    if (firstInput) {
      firstInput.focus();
    }
  });
}

/** Form fields for a value of knowledge type `typeName` (one per constructor field, or one "Value"), seeded from `encodedValue`. */
function valueFields(typeName, knowledgeTypes, encodedValue) {
  const typeSpec = knowledgeTypes[typeName];
  if (!typeSpec) {
    return [];
  }
  return typeSpec.fields.map(([fieldName, fieldType]) => {
    const current = typeSpec.compound ? encodedValue?.[fieldName] : encodedValue;
    const field = {
      name: VALUE_FIELD_PREFIX + fieldName,
      label: typeSpec.compound ? `${fieldName} (${fieldType})` : `Value (${fieldType})`,
      value: current === undefined || current === null ? "" : String(current),
    };
    return fieldType === "bool" ? {...field, kind: "select", options: BOOL_TEXTS} : field;
  });
}

/** Reverses valueFields(): a field-text dict for a compound type, or the scalar's text (what as_knowledge_value() accepts). */
function valueFromForm(typeName, knowledgeTypes, values) {
  const typeSpec = knowledgeTypes[typeName];
  if (!typeSpec.compound) {
    return values[VALUE_FIELD_PREFIX + typeSpec.fields[0][0]];
  }
  return Object.fromEntries(typeSpec.fields.map(([fieldName]) => [fieldName, values[VALUE_FIELD_PREFIX + fieldName]]));
}

/** Alerts a failed command's message (the web counterpart of the Tk editor's error dialogs). */
function reportFailure(result) {
  if (!result.ok) {
    alert(result.message);
  }
  return result;
}



//==========// Enter //==========//
// Enter leaves the field being edited (committing it through its change handler); with no
// field focused, it presses the [data-primary] button of the open dialog, or else of the
// [data-enter-scope] container (popover, inspector, knowledge editor) used last.

const FIELD_TAGS = ["INPUT", "SELECT", "TEXTAREA"];
const NON_TEXT_INPUT_TYPES = ["checkbox", "radio", "button", "submit", "file"];
let lastEnterScope = null;

/** Remembers the enter-scope container an event happened in. */
function noteEnterScope(event) {
  const scope = event.target.closest?.("[data-enter-scope]");
  if (scope) {
    lastEnterScope = scope;
  }
}
document.addEventListener("focusin", noteEnterScope);
document.addEventListener("pointerdown", noteEnterScope, true);

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.isComposing) {
    return;
  }
  const active = document.activeElement;
  const inField = active && FIELD_TAGS.includes(active.tagName) && !NON_TEXT_INPUT_TYPES.includes(active.type);
  if (inField) {
    if (!(active.tagName === "TEXTAREA" && event.shiftKey)) {   // Shift+Enter still types a newline
      event.preventDefault();
      active.blur();
    }
    return;
  }
  if (active?.tagName === "BUTTON") {
    return;   // a focused button presses itself
  }
  const scope = document.querySelector("dialog[open]") || (lastEnterScope?.isConnected ? lastEnterScope : null);
  const primary = scope?.querySelector("[data-primary]:not([disabled])");
  if (primary) {
    event.preventDefault();
    primary.click();
  }
});



//==========// Panels and Tabs //==========//

const panels = {};   // name -> {title, element, tab, view: {update} once registered}
let selectedTab = null;
let latestState = null;

/** Called by each panel's script: builds the panel in its tab and feeds it the latest state. */
function registerPanel(name, mount) {
  const panel = panels[name];
  if (!panel) {
    console.warn(`[web] panel script registered unknown panel '${name}'`);
    return;
  }
  const api = {
    // Resolves only once the state the command produced has been applied, so a panel can act on it right away.
    command: async (command, args = {}) => {
      const result = await postJson(`/api/panels/${name}/${command}`, args);
      await refresh();
      return result;
    },
    isVisible: () => selectedTab === name,
    refresh,
  };
  panel.view = mount(panel.element, api);
  updatePanel(name);
}

/** Feeds one panel its slice of the latest state; a broken panel only breaks itself. */
function updatePanel(name) {
  const panel = panels[name];
  if (!latestState || !panel.view) {
    return;
  }
  try {
    panel.view.update(latestState.panels[name], latestState);
  } catch (error) {
    console.error(`[web] panel '${name}' update failed`, error);
  }
}

/** Shows one tab's panel, remembering the choice for next time. */
function selectTab(name) {
  selectedTab = name;
  for (const [panelName, panel] of Object.entries(panels)) {
    panel.element.hidden = panelName !== name;
    panel.tab.classList.toggle("selected", panelName === name);
  }
  try {
    localStorage.setItem(TAB_STORAGE_KEY, name);
  } catch (error) {
    // NOTE: storage can be unavailable (private window, blocked site data); the choice just isn't remembered.
  }
  updatePanel(name);
}

/** The tab to open first: the remembered one if it still exists, else the first. */
function initialTab(names) {
  let remembered = null;
  try {
    remembered = localStorage.getItem(TAB_STORAGE_KEY);
  } catch (error) {
    // NOTE: see selectTab()
  }
  return names.includes(remembered) ? remembered : names[0];
}



//==========// Polling //==========//

let requestedSequence = 0;   // numbers every /api/state fetch, in the order they were sent
let appliedSequence = 0;     // the latest fetch whose state has been applied

/** Fetches /api/state and updates the header, console, and every panel. Fetches may overlap
    (a poll and a command's own refresh), so a reply older than the last applied one is dropped. */
async function refresh() {
  const sequence = ++requestedSequence;
  try {
    const state = await getJson("/api/state");
    if (sequence < appliedSequence) {
      return;
    }
    appliedSequence = sequence;
    latestState = state;
    document.getElementById("connection").textContent = "";
    renderHeader(latestState);
    renderConsole(latestState.console);
    Object.keys(panels).forEach(updatePanel);
  } catch (error) {
    document.getElementById("connection").textContent = "disconnected (is the sim running?)";
  }
}

/** The title and the Target dropdown (left alone while the user has it focused). */
function renderHeader(state) {
  document.getElementById("title").textContent = `Mission Interface: ${state.own_platform_id}`;
  const select = document.getElementById("target");
  const options = state.platforms.filter((platformId) => platformId !== state.own_platform_id);
  if (document.activeElement === select) {
    return;
  }
  if (select.dataset.options !== JSON.stringify(options)) {
    select.dataset.options = JSON.stringify(options);
    select.replaceChildren(...options.map((platformId) => make("option", {value: platformId, text: platformId})));
  }
  select.value = state.target ?? "";
  const age = state.target_sync_age;
  document.getElementById("sync-age").textContent = state.target === null ? ""
    : age === null ? "never synced" : `synced ${age.toFixed(SYNC_AGE_DECIMALS)} s ago`;
}

/** The console lines, following the output only if the user hasn't scrolled up. */
function renderConsole(lines) {
  const consoleElement = document.getElementById("console");
  const text = lines.join("\n");
  if (consoleElement.textContent === text) {
    return;
  }
  const atBottom = consoleElement.scrollHeight - consoleElement.scrollTop - consoleElement.clientHeight <= AT_BOTTOM_TOLERANCE_PX;
  consoleElement.textContent = text;
  if (atBottom) {
    consoleElement.scrollTop = consoleElement.scrollHeight;
  }
}



//==========// Start //==========//

/** Builds a tab per panel, loads each panel's script, and starts polling. */
async function start() {
  const descriptions = await getJson("/api/panels");
  const tabs = document.getElementById("tabs");
  const container = document.getElementById("panels");
  for (const {name, title} of descriptions) {
    const tab = make("button", {type: "button", class: "tab", text: title, onclick: () => selectTab(name)});
    const element = make("section", {class: "panel", hidden: true});
    tabs.append(tab);
    container.append(element);
    panels[name] = {title, element, tab, view: null};
  }
  selectTab(initialTab(descriptions.map(({name}) => name)));
  for (const {name} of descriptions) {
    document.body.append(make("script", {src: `/panels/${name}.js`}));
  }

  document.getElementById("target").addEventListener("change", async (event) => {
    reportFailure(await postJson("/api/target", {platform_id: event.target.value}));
    event.target.blur();
    refresh();
  });

  refresh();
  setInterval(refresh, POLL_INTERVAL_MS);
}

window.mtofr = {
  registerPanel,
  ui: {make, buttonRow, createTable, formatValue, formDialog, valueFields, valueFromForm, reportFailure},
};
start();
