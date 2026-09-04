"""Defines MissionEditorWindow: the Tk Toplevel a MissionEditorFrontseater opens/
closes as its show_interface capability starts/stops. Owns one draft mission-graph
dict at a time (see mtofr.mission_editor.graph_draft for the mutation helpers it
calls), independent of any live platform until explicitly pushed via the
privilege-gated Backseater.write_mission() path. Form/table-based (Treeviews plus
small modal dialogs for adding/editing entries), not a drag-and-drop canvas -- a
read-only MissionGraphViewer preview (in its own tab, the seed of a future
graphical editor) is the only rendering of the draft graph itself."""
import ast
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from mtofr.condition.condition import parse_condition, ConditionSyntaxError
from mtofr.database import verify_mission_structure, MissionStructuralError
from mtofr.viz.mission_graph_view import MissionGraphViewer
from mtofr.mission_editor import graph_draft
from mtofr.mission_editor.serialization import (
    KNOWLEDGE_TYPES_BY_NAME, KNOWLEDGE_TYPE_NAMES, SCALAR_CASTERS,
    is_compound_knowledge_type, constructor_fields, save_mission_graph, load_mission_graph,
)

# Matches MissionDashboard's own graph panel background, for visual consistency
# between the draft preview here and the live mission graph shown there.
GRAPH_PLOT_BACKGROUND = "#808080"


class MissionEditorWindow(tk.Toplevel):
    """One window: a target-platform picker, load/new/load-file/save-file/validate/
    push controls, an "Editor" tab (node/primitive/edge/knowledge tables) and a
    "Graph" tab (read-only mission graph preview -- the seed of what will become a
    graphical editor). `own_platform_id` is the interface platform's own id -- the
    writer_platform_id a push goes through write_mission() as."""

    def __init__(self, root, world, own_platform_id: str):
        super().__init__(root)
        self.title("Mission Editor")
        self.geometry("1100x700")

        self.world = world
        self.own_platform_id = own_platform_id
        self.draft = graph_draft.blank_graph()
        self.selected_node_id = None
        self.selected_primitive_name = None
        self.mission_graph_viewer = MissionGraphViewer()

        self.target_platform_id = tk.StringVar()
        self._build_layout()
        self._refresh_all()

    #==========# Layout #==========#

    def _build_layout(self) -> None:
        self._build_top_bar()

        notebook = ttk.Notebook(self)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=6)

        editor_tab = ttk.Frame(notebook)
        graph_tab = ttk.Frame(notebook)
        notebook.add(editor_tab, text="Editor")
        notebook.add(graph_tab, text="Graph")

        self._build_nodes_panel(editor_tab)
        self._build_edges_panel(editor_tab)
        self._build_knowledge_panel(editor_tab)
        self._build_preview_panel(graph_tab)

        self.status_label = ttk.Label(self, text="", anchor="w")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(0, 6))

    def _build_top_bar(self) -> None:
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        ttk.Label(top, text="Target platform:").pack(side=tk.LEFT, padx=(0, 4))
        platform_ids = list(self.world.backseaters.keys())
        self.platform_dropdown = ttk.Combobox(top, values=platform_ids, textvariable=self.target_platform_id,
                                               state="readonly", width=14)
        if platform_ids:
            self.target_platform_id.set(platform_ids[0])
        self.platform_dropdown.pack(side=tk.LEFT, padx=4)

        ttk.Button(top, text="Load Live", command=self._on_load_live).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="New Blank", command=self._on_new_blank).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Load File...", command=self._on_load_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Save File...", command=self._on_save_file).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Validate", command=self._on_validate).pack(side=tk.LEFT, padx=(16, 4))
        ttk.Button(top, text="Push to Platform", command=self._on_push).pack(side=tk.LEFT, padx=4)

    def _build_nodes_panel(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Nodes")
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.nodes_tree = ttk.Treeview(frame, columns=("primitives",), show="tree headings", height=8)
        self.nodes_tree.heading("#0", text="Node")
        self.nodes_tree.heading("primitives", text="Primitives")
        self.nodes_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.nodes_tree.bind("<<TreeviewSelect>>", lambda event: self._on_node_selected())

        node_buttons = ttk.Frame(frame)
        node_buttons.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(node_buttons, text="Add", command=self._on_add_node).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(node_buttons, text="Rename", command=self._on_rename_node).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(node_buttons, text="Remove", command=self._on_remove_node).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(node_buttons, text="Set Start", command=self._on_set_start_node).pack(side=tk.LEFT, padx=2, pady=2)

        ttk.Separator(frame).pack(side=tk.TOP, fill=tk.X, pady=4)
        ttk.Label(frame, text="Primitives on selected node:").pack(side=tk.TOP, anchor="w")

        self.primitives_tree = ttk.Treeview(frame, columns=("capability", "inputs", "outputs"),
                                             show="headings", height=6)
        for column_id, heading in (("capability", "Capability"), ("inputs", "Inputs"), ("outputs", "Outputs")):
            self.primitives_tree.heading(column_id, text=heading)
        self.primitives_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.primitives_tree.bind("<<TreeviewSelect>>", lambda event: self._on_primitive_selected())

        primitive_buttons = ttk.Frame(frame)
        primitive_buttons.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(primitive_buttons, text="Add", command=self._on_add_primitive).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(primitive_buttons, text="Edit", command=self._on_edit_primitive).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(primitive_buttons, text="Remove", command=self._on_remove_primitive).pack(side=tk.LEFT, padx=2, pady=2)

    def _build_edges_panel(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Edges")
        frame.grid(row=0, column=1, sticky="nsew", padx=4)

        self.edges_tree = ttk.Treeview(frame, columns=("from", "to", "condition"), show="headings", height=14)
        for column_id, heading in (("from", "From"), ("to", "To"), ("condition", "Condition")):
            self.edges_tree.heading(column_id, text=heading)
        self.edges_tree.column("condition", width=220)
        self.edges_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        edge_buttons = ttk.Frame(frame)
        edge_buttons.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(edge_buttons, text="Add", command=self._on_add_edge).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(edge_buttons, text="Edit", command=self._on_edit_edge).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(edge_buttons, text="Remove", command=self._on_remove_edge).pack(side=tk.LEFT, padx=2, pady=2)

    def _build_knowledge_panel(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Knowledge")
        frame.grid(row=0, column=2, sticky="nsew", padx=(4, 0))

        self.knowledge_tree = ttk.Treeview(frame, columns=("type", "value"), show="headings", height=14)
        for column_id, heading in (("type", "Type"), ("value", "Value")):
            self.knowledge_tree.heading(column_id, text=heading)
        self.knowledge_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        knowledge_buttons = ttk.Frame(frame)
        knowledge_buttons.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(knowledge_buttons, text="Add", command=self._on_add_knowledge_key).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(knowledge_buttons, text="Edit", command=self._on_edit_knowledge_key).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(knowledge_buttons, text="Remove", command=self._on_remove_knowledge_key).pack(side=tk.LEFT, padx=2, pady=2)

        for column in range(3):
            parent.columnconfigure(column, weight=1)

    def _build_preview_panel(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Preview")
        frame.pack(fill=tk.BOTH, expand=True)

        self.preview_fig, self.preview_ax = plt.subplots(figsize=(6, 6))
        self.preview_fig.patch.set_facecolor(GRAPH_PLOT_BACKGROUND)
        self.preview_canvas = FigureCanvasTkAgg(self.preview_fig, master=frame)
        self.preview_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    #==========# Draft mutation actions #==========#

    def _set_draft(self, new_draft: dict) -> None:
        self.draft = new_draft
        self._refresh_all()

    def _set_status(self, text: str) -> None:
        self.status_label.config(text=text)

    def _on_load_live(self) -> None:
        backseater = self.world.backseaters.get(self.target_platform_id.get())
        if backseater is None:
            self._set_status("No target platform selected.")
            return
        self.selected_node_id = None
        self.selected_primitive_name = None
        self._set_draft(graph_draft.load_draft(backseater.mission_graph))
        self._set_status(f"Loaded live mission graph from '{self.target_platform_id.get()}'.")

    def _on_new_blank(self) -> None:
        self.selected_node_id = None
        self.selected_primitive_name = None
        self._set_draft(graph_draft.blank_graph())
        self._set_status("Started a new blank draft.")

    def _on_load_file(self) -> None:
        file_path = filedialog.askopenfilename(parent=self, filetypes=[("Mission graph JSON", "*.json")])
        if not file_path:
            return
        try:
            self.selected_node_id = None
            self.selected_primitive_name = None
            self._set_draft(load_mission_graph(file_path))
            self._set_status(f"Loaded draft from {file_path}.")
        except Exception as error:
            messagebox.showerror("Load failed", str(error), parent=self)

    def _on_save_file(self) -> None:
        file_path = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                                   filetypes=[("Mission graph JSON", "*.json")])
        if not file_path:
            return
        try:
            save_mission_graph(self.draft, file_path)
            self._set_status(f"Saved draft to {file_path}.")
        except Exception as error:
            messagebox.showerror("Save failed", str(error), parent=self)

    def _on_validate(self) -> None:
        try:
            verify_mission_structure(self.draft)
        except MissionStructuralError as error:
            messagebox.showerror("Invalid mission graph", str(error), parent=self)
            return
        self._set_status("Draft is structurally valid.")

    def _on_push(self) -> None:
        backseater = self.world.backseaters.get(self.target_platform_id.get())
        if backseater is None:
            self._set_status("No target platform selected.")
            return
        try:
            backseater.write_mission(self.draft, writer_platform_id=self.own_platform_id)
        except (PermissionError, ValueError, MissionStructuralError) as error:
            messagebox.showerror("Push failed", str(error), parent=self)
            return
        self._set_status(f"Pushed draft to '{self.target_platform_id.get()}'.")

    #==========# Node actions #==========#

    def _on_add_node(self) -> None:
        node_id = _TextInputDialog(self, "Add Node", "Node id:").result
        if not node_id:
            return
        try:
            self._set_draft(graph_draft.add_node(self.draft, node_id))
            # Auto-select the new node, so it's immediately ready for "Add
            # Primitive" without an extra click just to select what you just made.
            self.selected_node_id = node_id
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Add node failed", str(error), parent=self)

    def _on_rename_node(self) -> None:
        if self.selected_node_id is None:
            return
        new_id = _TextInputDialog(self, "Rename Node", "New node id:", initial_value=self.selected_node_id).result
        if not new_id:
            return
        try:
            self._set_draft(graph_draft.rename_node(self.draft, self.selected_node_id, new_id))
            self.selected_node_id = new_id
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Rename node failed", str(error), parent=self)

    def _on_remove_node(self) -> None:
        if self.selected_node_id is None:
            return
        removed_node_id = self.selected_node_id
        self.selected_node_id = None
        self.selected_primitive_name = None
        self._set_draft(graph_draft.remove_node(self.draft, removed_node_id))

    def _on_set_start_node(self) -> None:
        if self.selected_node_id is None:
            return
        try:
            self._set_draft(graph_draft.set_start_node(self.draft, self.selected_node_id))
        except ValueError as error:
            messagebox.showerror("Set start failed", str(error), parent=self)

    def _on_node_selected(self) -> None:
        selection = self.nodes_tree.selection()
        self.selected_node_id = selection[0] if selection else None
        self.selected_primitive_name = None
        self._refresh_primitives_tree()

    def _on_primitive_selected(self) -> None:
        selection = self.primitives_tree.selection()
        self.selected_primitive_name = selection[0] if selection else None

    #==========# Primitive actions #==========#

    def _on_add_primitive(self) -> None:
        if self.selected_node_id is None:
            messagebox.showinfo("Add primitive", "Select a node first.", parent=self)
            return
        capability_registry = self._target_capability_registry()
        if capability_registry is None:
            messagebox.showinfo("Add primitive", "Select a target platform first.", parent=self)
            return
        result = _PrimitiveDialog(self, capability_registry, sorted(self.draft["knowledge"])).result
        if result is None:
            return
        name, capability, inputs, outputs = result
        try:
            self._set_draft(graph_draft.add_primitive(self.draft, self.selected_node_id, name, capability, inputs, outputs))
            self.selected_primitive_name = name
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Add primitive failed", str(error), parent=self)

    def _on_edit_primitive(self) -> None:
        if self.selected_node_id is None or self.selected_primitive_name is None:
            messagebox.showinfo("Edit primitive", "Select a primitive first.", parent=self)
            return
        capability_registry = self._target_capability_registry()
        if capability_registry is None:
            messagebox.showinfo("Edit primitive", "Select a target platform first.", parent=self)
            return
        old_name = self.selected_primitive_name
        primitive = self.draft["nodes"][self.selected_node_id]["primitives"][old_name]
        existing = (old_name, primitive["capability"], primitive.get("inputs", {}), primitive.get("outputs", {}))
        result = _PrimitiveDialog(self, capability_registry, sorted(self.draft["knowledge"]), existing=existing).result
        if result is None:
            return
        new_name, capability, inputs, outputs = result
        try:
            self._set_draft(graph_draft.edit_primitive(
                self.draft, self.selected_node_id, old_name, new_name, capability, inputs, outputs
            ))
            self.selected_primitive_name = new_name
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Edit primitive failed", str(error), parent=self)

    def _on_remove_primitive(self) -> None:
        if self.selected_node_id is None or self.selected_primitive_name is None:
            return
        self._set_draft(graph_draft.remove_primitive(self.draft, self.selected_node_id, self.selected_primitive_name))
        self.selected_primitive_name = None

    def _target_capability_registry(self):
        backseater = self.world.backseaters.get(self.target_platform_id.get())
        return backseater.capabilities() if backseater is not None else None

    #==========# Edge actions #==========#

    def _on_add_edge(self) -> None:
        node_ids = sorted(self.draft["nodes"])
        if not node_ids:
            messagebox.showinfo("Add edge", "Add at least one node first.", parent=self)
            return
        result = _EdgeDialog(self, node_ids).result
        if result is None:
            return
        source_id, target_id, condition = result
        try:
            self._set_draft(graph_draft.add_edge(self.draft, source_id, target_id, condition))
        except ValueError as error:
            messagebox.showerror("Add edge failed", str(error), parent=self)

    def _on_edit_edge(self) -> None:
        selection = self.edges_tree.selection()
        if not selection:
            return
        source_id, index = self._edge_rows[selection[0]]
        edge = self.draft["edges"][source_id][index]
        node_ids = sorted(self.draft["nodes"])
        result = _EdgeDialog(self, node_ids, existing=(source_id, edge["to"], edge["condition"])).result
        if result is None:
            return
        new_source_id, new_target_id, condition = result
        try:
            self._set_draft(graph_draft.edit_edge(self.draft, source_id, index, new_source_id, new_target_id, condition))
        except ValueError as error:
            messagebox.showerror("Edit edge failed", str(error), parent=self)

    def _on_remove_edge(self) -> None:
        selection = self.edges_tree.selection()
        if not selection:
            return
        source_id, index = self._edge_rows[selection[0]]
        self._set_draft(graph_draft.remove_edge(self.draft, source_id, index))

    #==========# Knowledge actions #==========#

    def _on_add_knowledge_key(self) -> None:
        result = _KnowledgeDialog(self).result
        if result is None:
            return
        key, entry_type, value = result
        try:
            self._set_draft(graph_draft.add_knowledge_key(self.draft, key, entry_type, value))
        except ValueError as error:
            messagebox.showerror("Add knowledge key failed", str(error), parent=self)

    def _on_edit_knowledge_key(self) -> None:
        selection = self.knowledge_tree.selection()
        if not selection:
            return
        old_key = selection[0]
        declaration = self.draft["knowledge"][old_key]
        existing = (old_key, declaration["type"], declaration["value"])
        result = _KnowledgeDialog(self, existing=existing).result
        if result is None:
            return
        new_key, entry_type, value = result
        try:
            draft = self.draft
            if new_key != old_key:
                # Cascades the rename to every primitive binding/edge condition
                # that references old_key, rather than leaving them dangling.
                draft = graph_draft.rename_knowledge_key(draft, old_key, new_key)
            draft = graph_draft.edit_knowledge_key(draft, new_key, entry_type, value)
            self._set_draft(draft)
        except ValueError as error:
            messagebox.showerror("Edit knowledge key failed", str(error), parent=self)

    def _on_remove_knowledge_key(self) -> None:
        selection = self.knowledge_tree.selection()
        if not selection:
            return
        self._set_draft(graph_draft.remove_knowledge_key(self.draft, selection[0]))

    #==========# Refresh #==========#

    def _refresh_all(self) -> None:
        self._refresh_nodes_tree()
        self._refresh_primitives_tree()
        self._refresh_edges_tree()
        self._refresh_knowledge_tree()
        self._refresh_preview()

    def _refresh_nodes_tree(self) -> None:
        self.nodes_tree.delete(*self.nodes_tree.get_children())
        for node_id, node in self.draft["nodes"].items():
            label = f"{node_id} *" if node_id == self.draft.get("start") else node_id
            self.nodes_tree.insert("", tk.END, iid=node_id, text=label, values=(len(node["primitives"]),))
        if self.selected_node_id not in self.draft["nodes"]:
            self.selected_node_id = None
        elif self.selected_node_id in self.nodes_tree.get_children():
            self.nodes_tree.selection_set(self.selected_node_id)

    def _refresh_primitives_tree(self) -> None:
        self.primitives_tree.delete(*self.primitives_tree.get_children())
        if self.selected_node_id is None or self.selected_node_id not in self.draft["nodes"]:
            self.selected_primitive_name = None
            return
        primitives = self.draft["nodes"][self.selected_node_id]["primitives"]
        for name, primitive in primitives.items():
            self.primitives_tree.insert("", tk.END, iid=name, values=(
                primitive["capability"],
                ", ".join(f"{field}={key}" for field, key in primitive.get("inputs", {}).items()),
                ", ".join(f"{field}={key}" for field, key in primitive.get("outputs", {}).items()),
            ))
        if self.selected_primitive_name not in primitives:
            self.selected_primitive_name = None
        elif self.selected_primitive_name in self.primitives_tree.get_children():
            self.primitives_tree.selection_set(self.selected_primitive_name)

    def _refresh_edges_tree(self) -> None:
        self.edges_tree.delete(*self.edges_tree.get_children())
        self._edge_rows = {}   # row iid -> (source_id, index within that source's edge list)
        for source_id, edge_list in self.draft["edges"].items():
            for index, edge in enumerate(edge_list):
                row_id = f"{source_id}#{index}"
                self.edges_tree.insert("", tk.END, iid=row_id, values=(
                    source_id, edge["to"], " ".join(str(token) for token in edge["condition"]),
                ))
                self._edge_rows[row_id] = (source_id, index)

    def _refresh_knowledge_tree(self) -> None:
        self.knowledge_tree.delete(*self.knowledge_tree.get_children())
        for key, declaration in self.draft["knowledge"].items():
            type_name = KNOWLEDGE_TYPE_NAMES.get(declaration["type"], declaration["type"].__name__)
            self.knowledge_tree.insert("", tk.END, iid=key, values=(type_name, repr(declaration["value"])))

    def _refresh_preview(self) -> None:
        self.preview_ax.clear()
        self.preview_ax.set_facecolor(GRAPH_PLOT_BACKGROUND)
        self.mission_graph_viewer.render(self.preview_ax, self.draft, active_node_id=None)
        self.preview_canvas.draw_idle()

    #==========# Lifecycle #==========#

    def close(self) -> None:
        """Called by MissionEditorFrontseater when show_interface stops (or at
        shutdown) -- destroys this Toplevel. Tolerant of the window already being
        gone (e.g. the underlying Tk root was destroyed first during teardown).
        Flushes pending idle-draw callbacks and closes the preview figure before
        destroying the widgets they target, mirroring MissionDashboard._on_close --
        otherwise Tk logs "invalid command name ...idle_draw" errors."""
        try:
            self.update_idletasks()
            plt.close(self.preview_fig)
            self.destroy()
        except tk.TclError:
            pass


#==========# Small modal dialogs #==========#

def _center_over_parent(dialog, parent) -> None:
    """Positions `dialog` centered over `parent`'s current window. Without this, a
    freshly created Toplevel can appear whever the window manager's default
    placement happens to put it (often the screen's top-left corner) rather than
    near the button that opened it."""
    dialog.update_idletasks()
    parent_x, parent_y = parent.winfo_rootx(), parent.winfo_rooty()
    parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
    dialog_width, dialog_height = dialog.winfo_width(), dialog.winfo_height()
    x = parent_x + max((parent_width - dialog_width) // 2, 0)
    y = parent_y + max((parent_height - dialog_height) // 2, 0)
    dialog.geometry(f"+{x}+{y}")


class _TextInputDialog(tk.Toplevel):
    """A single-line text-entry modal (Add Node / Rename Node), replacing
    tkinter.simpledialog.askstring so every dialog in this window is centered the
    same reliable way."""
    def __init__(self, parent, title: str, prompt: str, initial_value: str = ""):
        super().__init__(parent)
        self.title(title)
        self.result = None

        ttk.Label(self, text=prompt).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        self.value_var = tk.StringVar(value=initial_value)
        entry = ttk.Entry(self, textvariable=self.value_var, width=30)
        entry.grid(row=1, column=0, padx=6, pady=(0, 6))
        entry.focus_set()
        entry.bind("<Return>", lambda event: self._on_confirm())

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, pady=(0, 6))
        ttk.Button(buttons, text="OK", command=self._on_confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        _center_over_parent(self, parent)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _on_confirm(self) -> None:
        self.result = self.value_var.get().strip() or None
        self.destroy()


class _PrimitiveDialog(tk.Toplevel):
    """Modal dialog for adding or editing a primitive on the selected node: a
    name, a capability dropdown (sourced from the target platform's own
    capabilities()), and one Knowledge-key-binding combobox per declared input/
    output field -- bindings are chosen from the draft's already-declared
    knowledge keys, mirroring the mission graph's own declare-before-use
    discipline. `existing`, when given, pre-fills every field for editing."""
    def __init__(self, parent, capability_registry, known_knowledge_keys: list, existing: tuple = None):
        super().__init__(parent)
        self.title("Edit Primitive" if existing else "Add Primitive")
        self.result = None
        self._capability_registry = capability_registry
        self._known_knowledge_keys = known_knowledge_keys
        self._binding_vars = {}   # (kind, field_name) -> StringVar

        ttk.Label(self, text="Primitive name:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.name_var = tk.StringVar(value=existing[0] if existing else "")
        ttk.Entry(self, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(self, text="Capability:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.capability_var = tk.StringVar(value=existing[1] if existing else "")
        capability_dropdown = ttk.Combobox(self, textvariable=self.capability_var, state="readonly",
                                            values=sorted(capability_registry.all()))
        capability_dropdown.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        capability_dropdown.bind("<<ComboboxSelected>>", lambda event: self._rebuild_binding_fields())

        self.bindings_frame = ttk.Frame(self)
        self.bindings_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, columnspan=2, pady=6)
        ttk.Button(buttons, text="Save" if existing else "Add", command=self._on_confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.columnconfigure(1, weight=1)
        if self.capability_var.get():
            self._rebuild_binding_fields(existing[2] if existing else None, existing[3] if existing else None)

        _center_over_parent(self, parent)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _rebuild_binding_fields(self, initial_inputs: dict = None, initial_outputs: dict = None) -> None:
        for widget in self.bindings_frame.winfo_children():
            widget.destroy()
        self._binding_vars = {}

        capability = self._capability_registry.get(self.capability_var.get())
        if capability is None:
            return
        initial_inputs = initial_inputs or {}
        initial_outputs = initial_outputs or {}

        row = 0
        for kind, specs, initial in (("input", capability.inputs, initial_inputs), ("output", capability.outputs, initial_outputs)):
            for spec in specs:
                ttk.Label(self.bindings_frame, text=f"{kind} '{spec.name}' ({spec.type.__name__}):").grid(
                    row=row, column=0, sticky="w", padx=4, pady=2
                )
                variable = tk.StringVar(value=initial.get(spec.name, ""))
                ttk.Combobox(self.bindings_frame, textvariable=variable, values=self._known_knowledge_keys,
                             width=20).grid(row=row, column=1, sticky="ew", padx=4, pady=2)
                self._binding_vars[(kind, spec.name)] = variable
                row += 1

    def _on_confirm(self) -> None:
        name = self.name_var.get().strip()
        capability = self.capability_var.get()
        if not name or not capability:
            messagebox.showerror("Primitive", "Name and capability are required.", parent=self)
            return

        inputs = {field_name: variable.get() for (kind, field_name), variable in self._binding_vars.items()
                   if kind == "input" and variable.get()}
        outputs = {field_name: variable.get() for (kind, field_name), variable in self._binding_vars.items()
                   if kind == "output" and variable.get()}
        self.result = (name, capability, inputs, outputs)
        self.destroy()


class _EdgeDialog(tk.Toplevel):
    """Modal dialog for adding or editing an edge: From/To node dropdowns plus a
    raw condition-token text field, evaluated as a Python literal (e.g.
    ["ugv1/arrived", "==", True]) and parsed via parse_condition() before being
    accepted -- per-project decision to expose the real token format directly
    rather than build a structural condition builder. `existing`, when given,
    pre-fills every field for editing."""
    def __init__(self, parent, node_ids: list, existing: tuple = None):
        super().__init__(parent)
        self.title("Edit Edge" if existing else "Add Edge")
        self.result = None

        ttk.Label(self, text="From:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.from_var = tk.StringVar(value=existing[0] if existing else node_ids[0])
        ttk.Combobox(self, textvariable=self.from_var, state="readonly", values=node_ids).grid(
            row=0, column=1, sticky="ew", padx=6, pady=4
        )

        ttk.Label(self, text="To:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.to_var = tk.StringVar(value=existing[1] if existing else node_ids[0])
        ttk.Combobox(self, textvariable=self.to_var, state="readonly", values=node_ids).grid(
            row=1, column=1, sticky="ew", padx=6, pady=4
        )

        ttk.Label(self, text='Condition tokens (Python literal, e.g. ["ugv1/arrived", "==", True]):').grid(
            row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(8, 0)
        )
        self.condition_var = tk.StringVar(value=repr(existing[2]) if existing else "[]")
        ttk.Entry(self, textvariable=self.condition_var, width=50).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=4
        )

        buttons = ttk.Frame(self)
        buttons.grid(row=4, column=0, columnspan=2, pady=6)
        ttk.Button(buttons, text="Save" if existing else "Add", command=self._on_confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.columnconfigure(1, weight=1)
        _center_over_parent(self, parent)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _on_confirm(self) -> None:
        try:
            condition = ast.literal_eval(self.condition_var.get())
            if not isinstance(condition, list):
                raise ValueError("Condition must be a list of tokens")
            parse_condition(condition)
        except (ValueError, SyntaxError, ConditionSyntaxError) as error:
            messagebox.showerror("Invalid condition", str(error), parent=self)
            return
        self.result = (self.from_var.get(), self.to_var.get(), condition)
        self.destroy()


class _KnowledgeDialog(tk.Toplevel):
    """Modal dialog for declaring or editing a Knowledge key: name, type (from
    mtofr.mission_editor.serialization's type registry, the same set the editor
    can round-trip to/from a saved file), and one labeled field per constructor
    parameter of the chosen type -- generic via constructor_fields() introspection
    rather than a hardcoded per-type form, so a future KnowledgeEntry subclass
    needs only a registry entry to become editable here. `existing`, when given,
    pre-fills every field for editing, including the key itself -- the caller
    (MissionEditorWindow._on_edit_knowledge_key) is responsible for cascading a
    changed key through graph_draft.rename_knowledge_key() before applying the
    type/value change, so every primitive binding/edge condition referencing the
    old key follows the rename instead of being left dangling."""
    def __init__(self, parent, existing: tuple = None):
        super().__init__(parent)
        self.title("Edit Knowledge Key" if existing else "Add Knowledge Key")
        self.result = None
        self._editing = existing is not None
        self._field_vars = {}   # field_name -> StringVar

        ttk.Label(self, text="Key:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.key_var = tk.StringVar(value=existing[0] if existing else "")
        ttk.Entry(self, textvariable=self.key_var).grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(self, text="Type:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        initial_type_name = KNOWLEDGE_TYPE_NAMES[existing[1]] if existing else "float"
        self.type_var = tk.StringVar(value=initial_type_name)
        type_dropdown = ttk.Combobox(self, textvariable=self.type_var, state="readonly",
                                      values=sorted(KNOWLEDGE_TYPES_BY_NAME))
        type_dropdown.grid(row=1, column=1, sticky="ew", padx=6, pady=4)
        type_dropdown.bind("<<ComboboxSelected>>", lambda event: self._rebuild_value_fields())

        self.fields_frame = ttk.Frame(self)
        self.fields_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=3, column=0, columnspan=2, pady=6)
        ttk.Button(buttons, text="Save" if self._editing else "Add", command=self._on_confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=4)

        self.columnconfigure(1, weight=1)
        self._rebuild_value_fields(existing[2] if existing else None)

        _center_over_parent(self, parent)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _rebuild_value_fields(self, initial_value=None) -> None:
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        self._field_vars = {}

        entry_type = KNOWLEDGE_TYPES_BY_NAME[self.type_var.get()]
        if is_compound_knowledge_type(entry_type):
            for row, (field_name, annotation) in enumerate(constructor_fields(entry_type)):
                type_label = getattr(annotation, "__name__", "str")
                ttk.Label(self.fields_frame, text=f"{field_name} ({type_label}):").grid(
                    row=row, column=0, sticky="w", padx=4, pady=2
                )
                initial_text = str(getattr(initial_value, field_name, "")) if initial_value is not None else ""
                variable = tk.StringVar(value=initial_text)
                ttk.Entry(self.fields_frame, textvariable=variable, width=20).grid(
                    row=row, column=1, sticky="ew", padx=4, pady=2
                )
                self._field_vars[field_name] = variable
        else:
            ttk.Label(self.fields_frame, text="Value:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
            initial_text = str(initial_value) if initial_value is not None else ""
            variable = tk.StringVar(value=initial_text)
            ttk.Entry(self.fields_frame, textvariable=variable, width=20).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
            self._field_vars["value"] = variable

    def _on_confirm(self) -> None:
        key = self.key_var.get().strip()
        entry_type = KNOWLEDGE_TYPES_BY_NAME[self.type_var.get()]
        if not key:
            messagebox.showerror("Knowledge key", "Key is required.", parent=self)
            return
        try:
            if is_compound_knowledge_type(entry_type):
                kwargs = {}
                for field_name, annotation in constructor_fields(entry_type):
                    caster = SCALAR_CASTERS.get(annotation, str)
                    kwargs[field_name] = caster(self._field_vars[field_name].get())
                value = entry_type(**kwargs)
            else:
                caster = SCALAR_CASTERS.get(entry_type, str)
                value = caster(self._field_vars["value"].get())
        except ValueError as error:
            messagebox.showerror("Knowledge key", f"Invalid value: {error}", parent=self)
            return
        self.result = (key, entry_type, value)
        self.destroy()