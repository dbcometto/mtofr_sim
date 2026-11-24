"use strict";
/* Live Control panel (web/panels/live_control.py): the interface platform's view of every
   Knowledge key in the mesh, editable in place. Pending rows (a queued value, or a key a
   pushed mission declares that hasn't arrived yet) are shown in italics. */

mtofr.registerPanel("live_control", (element, api) => {
  const ui = mtofr.ui;
  const AGE_DECIMALS = 1;
  let panelState = null;

  const seconds = (age) => (age === null || age === undefined ? "" : age.toFixed(AGE_DECIMALS));
  const knowledgeTable = ui.createTable({
    columns: [
      {label: "Key", value: (row) => row.key},
      {label: "Type", value: (row) => row.type},
      {label: "Value", value: (row) => ui.formatValue(row.value) + (row.pending ? "  (pending)" : "")},
      {label: "Origin", value: (row) => row.origin ?? ""},
      {label: "Written (s ago)", value: (row) => seconds(row.age)},
      {label: "Origin synced (s ago)", value: (row) => seconds(row.synced_age)},
    ],
    rowKey: (row) => row.key,
    rowClass: (row) => (row.pending ? "pending" : ""),
    onActivate: (key) => editValue(key),
    emptyText: "(no Knowledge yet)",
  });

  element.append(
    ui.make("p", {class: "help", text:
      "Every Knowledge key this interface platform holds (its own and every peer's, as synced). " +
      "Edit a value to steer a running mission through its existing edges; the change publishes " +
      "on the next tick and reaches the other platforms by mesh sync. Italic rows are pending: a " +
      "value you set that hasn't applied yet, or a key a pushed mission declares that hasn't arrived yet."}),
    ui.buttonRow([{label: "Edit Value...", onClick: () => editValue(knowledgeTable.selectedKey)}]),
    ui.make("div", {class: "table-scroll tall"}, knowledgeTable.element),
  );

  /** Prompts for a new value of `key` (in its own type's fields) and queues it. */
  async function editValue(key) {
    const row = panelState && panelState.rows.find((candidate) => candidate.key === key);
    if (!row) {
      return;
    }
    const values = await ui.formDialog(`Set ${row.key} (${row.type})`,
      () => ui.valueFields(row.type, panelState.knowledge_types, row.value));
    if (values) {
      const value = ui.valueFromForm(row.type, panelState.knowledge_types, values);
      ui.reportFailure(await api.command("set_value", {key: row.key, value}));
    }
  }

  return {
    update(state) {
      panelState = state;
      knowledgeTable.setRows(state.rows);
    },
  };
});
