"""Defines MissionEditorWindow: the Tk Toplevel a MissionEditorFrontseater opens/
closes as its show_interface capability starts/stops. Owns one draft mission-graph
dict at a time (see graph_draft for the mutation helpers it calls), independent of
any live platform until explicitly pushed via the privilege-gated
Backseater.write_mission() path. Form/table-based (Treeviews plus small modal
dialogs for adding/editing entries, each double-click-to-edit too), not a
drag-and-drop canvas -- a read-only MissionGraphViewer preview (in its own tab, the
seed of a future graphical editor) is the only rendering of the draft graph itself.
The default tab, Live Control, is a separate, simpler surface: it edits a live
platform's already-declared Knowledge values directly (immediately, no draft/push
staging), letting an already-running mission be steered via its own existing edges
without authoring a new graph at all."""
import ast
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from mtofr.mission.condition import parse_condition, ConditionSyntaxError
from mtofr.mission.serialization import (
    KNOWLEDGE_TYPES_BY_NAME, KNOWLEDGE_TYPE_NAMES, SCALAR_CASTERS,
    is_compound_knowledge_type, constructor_fields, save_mission_graph, load_mission_graph,
)
from mtofr.mission.validation import find_binding_problems, verify_mission_structure, MissionStructuralError
from mtofr.viz.dashboard import GRAPH_PLOT_BACKGROUND   # the draft preview matches the dashboard's live graph panel
from mtofr.viz.mission_graph_view import MissionGraphViewer
from mtofr.environments.anywhere.platforms.interface.mission_editor import graph_draft


#========================================#
# Config
#========================================#

# How often the Graph tab's Live preview re-renders while that mode is selected;
# a live peek is only useful if it keeps up with the sim.
LIVE_PREVIEW_REFRESH_MS = 500

# How often the Live Control tab's Knowledge table re-renders from the target
# platform's actual current values.
LIVE_KNOWLEDGE_REFRESH_MS = 1000

# Caps memory use for the undo history; unlikely to matter for a hand-edited
# mission graph, but an unbounded stack is needless for a session that could
# run for a long time.
UNDO_HISTORY_LIMIT = 50

AT_BOTTOM_FRACTION = 0.999   # text scroll position counted as "at the bottom", so output keeps following
DEFAULT_KNOWLEDGE_TYPE_NAME = "float"
START_NODE_MARKER = " *"   # appended to the start node's label in the Nodes table
MISSION_GRAPH_FILE_EXTENSION = ".json"
MISSION_GRAPH_FILE_TYPES = [("Mission graph JSON", "*" + MISSION_GRAPH_FILE_EXTENSION)]


# Layout (px unless noted)
WINDOW_GEOMETRY = "1500x850"
WINDOW_MIN_SIZE = (1200, 700)
PAD_TINY = 2
PAD_SMALL = 4
PAD_MEDIUM = 6
PAD_LARGE = 8
PAD_SECTION = 10
PAD_GROUP = 16   # gap between groups of top-bar buttons
PLATFORM_DROPDOWN_WIDTH = 14   # characters
LIVE_CONTROL_WRAP_LENGTH = 900
PREVIEW_FIGURE_SIZE = (6, 6)   # inches
WIDE_PANE_WEIGHT = 2
NARROW_PANE_WEIGHT = 1


# Tables: (column_id, heading, width) per column; the last column stretches
LIVE_KNOWLEDGE_COLUMNS = (("key", "Key", 160), ("type", "Type", 70), ("value", "Value", 260))
CAPABILITY_COLUMNS = (("capability", "Capability", 90), ("inputs", "Inputs", 150), ("outputs", "Outputs", 150))
EDGE_COLUMNS = (("from", "From", 70), ("to", "To", 70), ("condition", "Condition", 260))
KNOWLEDGE_COLUMNS = (("key", "Key", 110), ("type", "Type", 60), ("value", "Value", 160))
NODE_COLUMN_WIDTH = 110
NODE_CAPABILITY_COUNT_COLUMN_WIDTH = 70
LIVE_KNOWLEDGE_TREE_ROWS = 20
SHORT_TREE_ROWS = 6
TALL_TREE_ROWS = 14
CONSOLE_ROWS = 6


# Dialogs (characters)
TEXT_INPUT_WIDTH = 30
FIELD_ENTRY_WIDTH = 20
CONDITION_ENTRY_WIDTH = 50







#========================================#
# Mission Editor Window
#========================================#

class MissionEditorWindow(tk.Toplevel):
    """One window: a target-platform picker, load/new/load-file/save-file/
    undo/redo/validate/push controls, a default "Live Control" tab (the target
    platform's live Knowledge, editable directly), an "Editor" tab (resizable
    node/capability request/edge/knowledge tables), a "Graph" tab (a read-only Draft/Live
    preview toggle over MissionGraphViewer -- the seed of what will become a
    graphical editor), and a Console panel logging every action's outcome.
    `own_platform_id` is the interface platform's own id -- the writer_platform_id
    a push (or a live Knowledge write) goes through as."""

    def __init__(self, root, world, own_platform_id: str):
        """Opens on a blank draft, targeting the first platform, with the live Knowledge refresh running."""
        super().__init__(root)
        self.title("Mission Editor")
        self.geometry(WINDOW_GEOMETRY)
        self.minsize(*WINDOW_MIN_SIZE)

        self.world = world
        self.own_platform_id = own_platform_id
        self.draft = graph_draft.blank_graph()
        self.draft_source_platform_id = None   # platform_id the draft was loaded from, or None (new/from-file)
        self.selected_node_id = None
        self.selected_request_name = None
        self.selected_live_knowledge_key = None
        self.undo_stack = []   # past drafts, most recent last
        self.redo_stack = []   # drafts undone away from, most recent last
        self._undo_group_open = False       # True while the assistant is mid-turn: all its edits share one undo entry
        self._undo_group_recorded = False   # whether the open group has already pushed its entry
        self.assistant_window = None
        self.mission_graph_viewer = MissionGraphViewer()
        self._live_preview_refresh_job = None      # self.after() id, cancelled explicitly in close()
        self._live_knowledge_refresh_job = None    # self.after() id, cancelled explicitly in close()

        self.target_platform_id = tk.StringVar()
        self.preview_mode = tk.StringVar(value="draft")
        self._build_layout()
        self._update_undo_redo_buttons()
        self._refresh_all()
        self._refresh_live_knowledge_tree()

        # Toplevel-level bindings fire regardless of which child widget currently
        # has focus (Tk falls through a focused widget's own bindtags to its
        # toplevel's), and are inert while a modal dialog holds the input grab.
        self.bind("<Control-z>", lambda event: self._on_undo())
        self.bind("<Control-y>", lambda event: self._on_redo())
        self.bind("<Control-Shift-Key-Z>", lambda event: self._on_redo())

        self._schedule_live_knowledge_refresh()

    #===============# Layout #===============#

    def _build_layout(self) -> None:
        """Builds the top bar, the three tabs, and the Console."""
        self._build_top_bar()

        self.notebook = notebook = ttk.Notebook(self)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=PAD_MEDIUM, pady=PAD_MEDIUM)

        # Live Control is added (and thus selected) first -- it's the everyday
        # tab for steering an already-running mission via its existing edges,
        # without authoring a new one; Editor/Graph are for that less common task.
        live_control_tab = ttk.Frame(notebook)
        editor_tab = ttk.Frame(notebook)
        graph_tab = ttk.Frame(notebook)
        notebook.add(live_control_tab, text="Live Control")
        notebook.add(editor_tab, text="Editor")
        notebook.add(graph_tab, text="Graph")

        self._build_live_control_tab(live_control_tab)
        self._build_editor_tab(editor_tab)
        self._build_preview_panel(graph_tab)
        self._build_console_panel()

    def _build_top_bar(self) -> None:
        """Builds the target-platform dropdown and the draft/undo/validate/push/assistant buttons."""
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=PAD_MEDIUM, pady=PAD_MEDIUM)

        ttk.Label(top, text="Target platform:").pack(side=tk.LEFT, padx=(0, PAD_SMALL))
        platform_ids = list(self.world.platforms.keys())
        self.platform_dropdown = ttk.Combobox(top, values=platform_ids, textvariable=self.target_platform_id,
                                               state="readonly", width=PLATFORM_DROPDOWN_WIDTH)
        if platform_ids:
            self.target_platform_id.set(platform_ids[0])
        self.platform_dropdown.pack(side=tk.LEFT, padx=PAD_SMALL)
        self.platform_dropdown.bind("<<ComboboxSelected>>", lambda event: self._on_target_platform_changed())

        ttk.Button(top, text="Load Live", command=self._on_load_live).pack(side=tk.LEFT, padx=PAD_SMALL)
        ttk.Button(top, text="New Blank", command=self._on_new_blank).pack(side=tk.LEFT, padx=PAD_SMALL)
        ttk.Button(top, text="Load File...", command=self._on_load_file).pack(side=tk.LEFT, padx=PAD_SMALL)
        ttk.Button(top, text="Save File...", command=self._on_save_file).pack(side=tk.LEFT, padx=PAD_SMALL)

        self.undo_button = ttk.Button(top, text="↶ Undo", command=self._on_undo)
        self.undo_button.pack(side=tk.LEFT, padx=(PAD_GROUP, PAD_SMALL))
        self.redo_button = ttk.Button(top, text="↷ Redo", command=self._on_redo)
        self.redo_button.pack(side=tk.LEFT, padx=PAD_SMALL)

        ttk.Button(top, text="Validate", command=self._on_validate).pack(side=tk.LEFT, padx=(PAD_GROUP, PAD_SMALL))
        ttk.Button(top, text="Push to Platform", command=self._on_push).pack(side=tk.LEFT, padx=PAD_SMALL)
        ttk.Button(top, text="Assistant...", command=self._on_open_assistant).pack(side=tk.LEFT,
                                                                                   padx=(PAD_GROUP, PAD_SMALL))

    def _build_live_control_tab(self, parent) -> None:
        """The default tab: the *target* platform's already-running Knowledge --
        not the draft -- shown live and directly editable. Since a mission
        graph's own edges already branch on Knowledge values (e.g. a location
        or a boolean flag), changing one of those values here can steer an
        already-running mission without authoring a new graph at all."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=PAD_MEDIUM, pady=PAD_MEDIUM)

        ttk.Label(
            frame, anchor="w", justify="left", wraplength=LIVE_CONTROL_WRAP_LENGTH,
            text="Live Knowledge for the target platform above -- double-click (or Edit Value) to change a "
                 "value directly on the running platform, using its mission's existing edges, without "
                 "authoring a new mission graph.",
        ).pack(side=tk.TOP, anchor="w", pady=(0, PAD_MEDIUM))

        self.live_knowledge_tree = _build_table(frame, LIVE_KNOWLEDGE_COLUMNS, LIVE_KNOWLEDGE_TREE_ROWS)
        self.live_knowledge_tree.bind("<Double-1>", lambda event: self._on_edit_live_knowledge_value())
        self.live_knowledge_tree.bind("<<TreeviewSelect>>", lambda event: self._on_live_knowledge_selected())

        buttons = ttk.Frame(frame)
        buttons.pack(side=tk.TOP, fill=tk.X, pady=(PAD_SMALL, 0))
        _add_buttons(buttons, (("Edit Value...", self._on_edit_live_knowledge_value),
                               ("Refresh", self._refresh_live_knowledge_tree)))

    def _build_editor_tab(self, parent) -> None:
        """Nodes+Capabilities / Edges / Knowledge as three resizable panes (a
        ttk.PanedWindow, dragged via the sash between them) rather than fixed
        grid columns, so content that doesn't fit its default width can be seen."""
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        nodes_pane = ttk.Frame(paned)
        edges_pane = ttk.Frame(paned)
        knowledge_pane = ttk.Frame(paned)
        paned.add(nodes_pane, weight=WIDE_PANE_WEIGHT)
        paned.add(edges_pane, weight=WIDE_PANE_WEIGHT)
        paned.add(knowledge_pane, weight=NARROW_PANE_WEIGHT)

        self._build_nodes_panel(nodes_pane)
        self._build_edges_panel(edges_pane)
        self._build_knowledge_panel(knowledge_pane)

    def _build_nodes_panel(self, parent) -> None:
        """Builds the Nodes table and the selected node's Capabilities table, each with its buttons."""
        # Nodes and Capabilities are each other's own resizable pane (vertical
        # sash) rather than both packed into one fixed-height LabelFrame.
        paned = ttk.PanedWindow(parent, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        nodes_frame = ttk.LabelFrame(paned, text="Nodes")
        capabilities_frame = ttk.LabelFrame(paned, text="Capabilities on selected node")
        paned.add(nodes_frame, weight=NARROW_PANE_WEIGHT)
        paned.add(capabilities_frame, weight=NARROW_PANE_WEIGHT)


        # Nodes
        self.nodes_tree = ttk.Treeview(nodes_frame, columns=("capabilities",), show="tree headings",
                                       height=SHORT_TREE_ROWS)
        self.nodes_tree.heading("#0", text="Node")
        self.nodes_tree.heading("capabilities", text="Capabilities")
        self.nodes_tree.column("#0", width=NODE_COLUMN_WIDTH, stretch=False)
        self.nodes_tree.column("capabilities", width=NODE_CAPABILITY_COUNT_COLUMN_WIDTH, stretch=True)
        self.nodes_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.nodes_tree.bind("<<TreeviewSelect>>", lambda event: self._on_node_selected())
        self.nodes_tree.bind("<Double-1>", lambda event: self._on_rename_node())

        node_buttons = ttk.Frame(nodes_frame)
        node_buttons.pack(side=tk.TOP, fill=tk.X)
        _add_buttons(node_buttons, (("Add", self._on_add_node), ("Rename", self._on_rename_node),
                                    ("Remove", self._on_remove_node), ("Set Start", self._on_set_start_node)))


        # Capabilities
        self.capabilities_tree = _build_table(capabilities_frame, CAPABILITY_COLUMNS, SHORT_TREE_ROWS)
        self.capabilities_tree.bind("<<TreeviewSelect>>", lambda event: self._on_capability_request_selected())
        self.capabilities_tree.bind("<Double-1>", lambda event: self._on_edit_capability())

        capability_buttons = ttk.Frame(capabilities_frame)
        capability_buttons.pack(side=tk.TOP, fill=tk.X)
        _add_buttons(capability_buttons, (("Add", self._on_add_capability), ("Edit", self._on_edit_capability),
                                          ("Remove", self._on_remove_capability)))

    def _build_edges_panel(self, parent) -> None:
        """Builds the Edges table and its buttons."""
        frame = ttk.LabelFrame(parent, text="Edges")
        frame.pack(fill=tk.BOTH, expand=True)

        self.edges_tree = _build_table(frame, EDGE_COLUMNS, TALL_TREE_ROWS)
        self.edges_tree.bind("<Double-1>", lambda event: self._on_edit_edge())

        edge_buttons = ttk.Frame(frame)
        edge_buttons.pack(side=tk.TOP, fill=tk.X)
        _add_buttons(edge_buttons, (("Add", self._on_add_edge), ("Edit", self._on_edit_edge),
                                    ("Remove", self._on_remove_edge)))

    def _build_knowledge_panel(self, parent) -> None:
        """Builds the draft's Knowledge table (Key, Type, Value) and its buttons."""
        frame = ttk.LabelFrame(parent, text="Knowledge")
        frame.pack(fill=tk.BOTH, expand=True)

        self.knowledge_tree = _build_table(frame, KNOWLEDGE_COLUMNS, TALL_TREE_ROWS)
        self.knowledge_tree.bind("<Double-1>", lambda event: self._on_edit_knowledge_key())

        knowledge_buttons = ttk.Frame(frame)
        knowledge_buttons.pack(side=tk.TOP, fill=tk.X)
        _add_buttons(knowledge_buttons, (("Add", self._on_add_knowledge_key), ("Edit", self._on_edit_knowledge_key),
                                         ("Remove", self._on_remove_knowledge_key)))

    def _build_preview_panel(self, parent) -> None:
        """Builds the Graph tab: the Draft/Live toggle and the preview canvas."""
        frame = ttk.LabelFrame(parent, text="Preview")
        frame.pack(fill=tk.BOTH, expand=True)

        mode_bar = ttk.Frame(frame)
        mode_bar.pack(side=tk.TOP, fill=tk.X, padx=PAD_SMALL, pady=PAD_SMALL)
        ttk.Radiobutton(mode_bar, text="Draft", variable=self.preview_mode, value="draft",
                         command=self._on_preview_mode_changed).pack(side=tk.LEFT, padx=PAD_SMALL)
        ttk.Radiobutton(mode_bar, text="Live (read-only)", variable=self.preview_mode, value="live",
                         command=self._on_preview_mode_changed).pack(side=tk.LEFT, padx=PAD_SMALL)
        self.preview_mode_note = ttk.Label(mode_bar, text="", anchor="w")
        self.preview_mode_note.pack(side=tk.LEFT, padx=PAD_SECTION)

        self.preview_fig, self.preview_ax = plt.subplots(figsize=PREVIEW_FIGURE_SIZE)
        self.preview_fig.patch.set_facecolor(GRAPH_PLOT_BACKGROUND)
        self.preview_canvas = FigureCanvasTkAgg(self.preview_fig, master=frame)
        self.preview_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _build_console_panel(self) -> None:
        """A persistent, scrollable log of every action's outcome, so Validate/Push/
        Load/Save results can't be missed or pushed off-screen at a small window size."""
        frame = ttk.LabelFrame(self, text="Console")
        frame.pack(side=tk.BOTTOM, fill=tk.X, padx=PAD_MEDIUM, pady=(0, PAD_MEDIUM))

        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        self.console_text = tk.Text(text_frame, height=CONSOLE_ROWS, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.console_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)





    #===============# Draft Mutation Actions #===============#

    def _set_draft(self, new_draft: dict) -> None:
        """The single choke point every draft mutation (including Load Live/New
        Blank/Load File, treated as ordinary undoable actions) goes through.
        Every mutation helper in graph_draft.py returns a brand-new top-level
        dict rather than mutating in place, so recording the *old* self.draft
        object here -- no copying needed -- is enough for a full undo history;
        a fresh action always invalidates whatever was available to redo."""
        if not (self._undo_group_open and self._undo_group_recorded):
            self.undo_stack.append(self.draft)
            del self.undo_stack[:-UNDO_HISTORY_LIMIT]
        self._undo_group_recorded = self._undo_group_open
        self.redo_stack.clear()
        self._apply_draft(new_draft)
        self._update_undo_redo_buttons()

    def apply_draft_edit(self, new_draft: dict) -> None:
        """Public entry point for non-GUI editors (the assistant) into the same _set_draft() choke point."""
        self._set_draft(new_draft)

    def begin_undo_group(self) -> None:
        """Until end_undo_group(), every draft mutation shares one undo entry (one Ctrl+Z for the whole group)."""
        self._undo_group_open = True
        self._undo_group_recorded = False

    def end_undo_group(self) -> None:
        """Closes the undo group begin_undo_group() opened."""
        self._undo_group_open = False
        self._undo_group_recorded = False

    def _on_open_assistant(self) -> None:
        """Opens the LLM assistant window, or raises it if already open."""
        if self.assistant_window is not None and self.assistant_window.winfo_exists():
            self.assistant_window.lift()
            return
        # NOTE: lazy import keeps the editor free of the assistant's imports until used
        from mtofr.environments.anywhere.platforms.interface.mission_editor.assistant_window import AssistantWindow
        self.assistant_window = AssistantWindow(self)

    def _apply_draft(self, new_draft: dict) -> None:
        """Swaps in `new_draft` and refreshes every view, without touching the undo history."""
        self.draft = new_draft
        self._refresh_all()

    def _on_undo(self) -> None:
        """Restores the previous draft, if any."""
        if not self.undo_stack:
            self._log("Nothing to undo.")
            return
        self.redo_stack.append(self.draft)
        self._apply_draft(self.undo_stack.pop())
        self._update_undo_redo_buttons()
        self._log("Undid last change.")

    def _on_redo(self) -> None:
        """Re-applies the last undone draft, if any."""
        if not self.redo_stack:
            self._log("Nothing to redo.")
            return
        self.undo_stack.append(self.draft)
        self._apply_draft(self.redo_stack.pop())
        self._update_undo_redo_buttons()
        self._log("Redid change.")

    def _update_undo_redo_buttons(self) -> None:
        """Enables Undo/Redo only when there's something to undo/redo."""
        self.undo_button.config(state="normal" if self.undo_stack else "disabled")
        self.redo_button.config(state="normal" if self.redo_stack else "disabled")

    def _log(self, message: str) -> None:
        """Appends a line to the Console, following the output only if the user hasn't scrolled up."""
        at_bottom = self.console_text.yview()[1] >= AT_BOTTOM_FRACTION
        self.console_text.configure(state="normal")
        self.console_text.insert(tk.END, message + "\n")
        if at_bottom:
            self.console_text.see(tk.END)
        self.console_text.configure(state="disabled")

    def _start_new_draft(self, new_draft: dict, source_platform_id: str | None) -> None:
        """Replaces the whole draft (an undoable action), clearing the selection and recording where it came from."""
        self.selected_node_id = None
        self.selected_request_name = None
        self.draft_source_platform_id = source_platform_id
        self._set_draft(new_draft)

    def _on_load_live(self) -> None:
        """Loads a copy of the target platform's running mission graph as the draft."""
        target_id = self.target_platform_id.get()
        backseater = self._backseater_of(target_id)
        if backseater is None:
            self._log("Load Live failed: no target platform selected.")
            return
        self._start_new_draft(graph_draft.load_draft(backseater.mission_graph), source_platform_id=target_id)
        self._log(f"Loaded live mission graph from '{target_id}'.")

    def _on_new_blank(self) -> None:
        """Starts a blank draft."""
        self._start_new_draft(graph_draft.blank_graph(), source_platform_id=None)
        self._log("Started a new blank draft.")

    def _on_load_file(self) -> None:
        """Loads a draft from a mission-graph JSON file."""
        file_path = filedialog.askopenfilename(parent=self, filetypes=MISSION_GRAPH_FILE_TYPES)
        if not file_path:
            return
        try:
            self._start_new_draft(load_mission_graph(file_path), source_platform_id=None)
            self._log(f"Loaded draft from {file_path}.")
        except Exception as error:
            self._log(f"Load failed: {error}")
            messagebox.showerror("Load failed", str(error), parent=self)

    def _on_save_file(self) -> None:
        """Saves the draft to a mission-graph JSON file."""
        file_path = filedialog.asksaveasfilename(parent=self, defaultextension=MISSION_GRAPH_FILE_EXTENSION,
                                                   filetypes=MISSION_GRAPH_FILE_TYPES)
        if not file_path:
            return
        try:
            save_mission_graph(self.draft, file_path)
            self._log(f"Saved draft to {file_path}.")
        except Exception as error:
            self._log(f"Save failed: {error}")
            messagebox.showerror("Save failed", str(error), parent=self)

    def _on_validate(self) -> None:
        """Checks the draft's structure and that the target platform could bind it (the same checks a push enforces)."""
        try:
            verify_mission_structure(self.draft)
        except MissionStructuralError as error:
            self._log(f"Validation failed: {error}")
            messagebox.showerror("Invalid mission graph", str(error), parent=self)
            return
        target_id = self.target_platform_id.get()
        backseater = self._backseater_of(target_id)
        problems = find_binding_problems(self.draft, backseater.capabilities() if backseater is not None else None)
        if problems:
            self._log(f"Validation failed for '{target_id}':")
            for problem in problems:
                self._log(f"  - {problem}")
            messagebox.showerror("Cannot bind on target platform", "\n".join(problems), parent=self)
            return
        self._log(f"Draft is structurally valid and binds on '{target_id}'." if backseater is not None
                  else "Draft is structurally valid (no target platform selected to check bindings against).")

    def _on_push(self) -> None:
        """Writes the draft to the target platform through its privilege-gated write_mission()."""
        target_id = self.target_platform_id.get()
        backseater = self._backseater_of(target_id)
        if backseater is None:
            self._log("Push failed: no target platform selected.")
            return
        try:
            backseater.write_mission(self.draft, writer_platform_id=self.own_platform_id)
        except (PermissionError, ValueError, MissionStructuralError) as error:
            self._log(f"Push failed: {error}")
            messagebox.showerror("Push failed", str(error), parent=self)
            return
        if self.draft_source_platform_id is not None and self.draft_source_platform_id != target_id:
            # NOTE: doesn't block the push (reusing a draft across platforms may be
            # intentional), just makes the mismatch visible, since pushing an
            # unmodified draft to the wrong target is exactly what silently
            # duplicated a mission across two platforms once before.
            self._log(f"Warning: pushed a draft loaded from '{self.draft_source_platform_id}' to a different platform '{target_id}'.")
        self._log(f"Pushed draft to '{target_id}'.")





    #===============# Node Actions #===============#

    def _on_add_node(self) -> None:
        """Prompts for a node id, adds it, and selects it."""
        node_id = _TextInputDialog(self, "Add Node", "Node id:").result
        if not node_id:
            return
        try:
            self._set_draft(graph_draft.add_node(self.draft, node_id))
            # Auto-select the new node, so it's immediately ready for "Add
            # Capability" without an extra click just to select what you just made.
            self.selected_node_id = node_id
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Add node failed", str(error), parent=self)

    def _on_rename_node(self) -> None:
        """Prompts for a new id for the selected node."""
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
        """Removes the selected node and every edge touching it."""
        if self.selected_node_id is None:
            return
        removed_node_id = self.selected_node_id
        self.selected_node_id = None
        self.selected_request_name = None
        self._set_draft(graph_draft.remove_node(self.draft, removed_node_id))

    def _on_set_start_node(self) -> None:
        """Makes the selected node the start node."""
        if self.selected_node_id is None:
            return
        try:
            self._set_draft(graph_draft.set_start_node(self.draft, self.selected_node_id))
        except ValueError as error:
            messagebox.showerror("Set start failed", str(error), parent=self)

    def _on_node_selected(self) -> None:
        """Tracks the selected node and shows its capability requests."""
        selection = self.nodes_tree.selection()
        self.selected_node_id = selection[0] if selection else None
        self.selected_request_name = None
        self._refresh_capabilities_tree()

    def _on_capability_request_selected(self) -> None:
        """Tracks the selected capability request."""
        selection = self.capabilities_tree.selection()
        self.selected_request_name = selection[0] if selection else None





    #===============# Capability Request Actions #===============#

    def _on_add_capability(self) -> None:
        """Opens the capability request dialog for the selected node and adds the result."""
        if self.selected_node_id is None:
            messagebox.showinfo("Add capability", "Select a node first.", parent=self)
            return
        capability_registry = self._target_capability_registry()
        if capability_registry is None:
            messagebox.showinfo("Add capability", "Select a target platform first.", parent=self)
            return
        result = _CapabilityRequestDialog(self, capability_registry, sorted(self.draft["knowledge"])).result
        if result is None:
            return
        name, capability, inputs, outputs = result
        try:
            self._set_draft(graph_draft.add_capability(self.draft, self.selected_node_id, name, capability, inputs, outputs))
            self.selected_request_name = name
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Add capability failed", str(error), parent=self)

    def _on_edit_capability(self) -> None:
        """Opens the capability request dialog pre-filled with the selected capability request and applies the result."""
        if self.selected_node_id is None or self.selected_request_name is None:
            messagebox.showinfo("Edit capability", "Select a capability first.", parent=self)
            return
        capability_registry = self._target_capability_registry()
        if capability_registry is None:
            messagebox.showinfo("Edit capability", "Select a target platform first.", parent=self)
            return
        old_name = self.selected_request_name
        capability_request = self.draft["nodes"][self.selected_node_id]["capabilities"][old_name]
        existing = (old_name, capability_request["capability"],
                    capability_request.get("inputs", {}), capability_request.get("outputs", {}))
        result = _CapabilityRequestDialog(self, capability_registry, sorted(self.draft["knowledge"]), existing=existing).result
        if result is None:
            return
        new_name, capability, inputs, outputs = result
        try:
            self._set_draft(graph_draft.edit_capability(
                self.draft, self.selected_node_id, old_name, new_name, capability, inputs, outputs
            ))
            self.selected_request_name = new_name
            self._refresh_all()
        except ValueError as error:
            messagebox.showerror("Edit capability failed", str(error), parent=self)

    def _on_remove_capability(self) -> None:
        """Removes the selected capability request."""
        if self.selected_node_id is None or self.selected_request_name is None:
            return
        self._set_draft(graph_draft.remove_capability(self.draft, self.selected_node_id, self.selected_request_name))
        self.selected_request_name = None

    def _backseater_of(self, platform_id: str):
        """The named platform's Backseater, or None if no such platform exists (e.g. none selected)."""
        platform = self.world.platforms.get(platform_id)
        return platform.backseater if platform is not None else None

    def _target_capability_registry(self):
        """The target platform's CapabilityRegistry, or None if none is selected."""
        backseater = self._backseater_of(self.target_platform_id.get())
        return backseater.capabilities() if backseater is not None else None

    def _on_target_platform_changed(self) -> None:
        """Refreshes the views that show the target platform."""
        self._refresh_preview()
        self._refresh_live_knowledge_tree()





    #===============# Live Control Tab #===============#

    def _refresh_live_knowledge_tree(self) -> None:
        """Re-reads the target platform's live Knowledge into the table, keeping the selection."""
        # delete()+insert() (Treeview has no in-place row-value update) clears
        # the current selection every time; restore it afterward, same as the
        # Editor tab's tables, but doubly important here since this refresh fires
        # on its own every second, not just after an edit you made yourself.
        self.live_knowledge_tree.delete(*self.live_knowledge_tree.get_children())
        backseater = self._backseater_of(self.target_platform_id.get())
        if backseater is None:
            self.selected_live_knowledge_key = None
            return
        knowledge = backseater.knowledge_database
        for key, value in knowledge.all().items():
            declared_type = knowledge.type_of(key)
            type_name = KNOWLEDGE_TYPE_NAMES.get(declared_type, getattr(declared_type, "__name__", "?"))
            self.live_knowledge_tree.insert("", tk.END, iid=key, values=(key, type_name, repr(value)))
        if self.selected_live_knowledge_key not in knowledge.all():
            self.selected_live_knowledge_key = None
        elif self.selected_live_knowledge_key in self.live_knowledge_tree.get_children():
            self.live_knowledge_tree.selection_set(self.selected_live_knowledge_key)

    def _on_live_knowledge_selected(self) -> None:
        """Tracks the selected live Knowledge key."""
        selection = self.live_knowledge_tree.selection()
        self.selected_live_knowledge_key = selection[0] if selection else None

    def _on_edit_live_knowledge_value(self) -> None:
        """Prompts for a new value for the selected key and sets it directly on the running platform."""
        target_id = self.target_platform_id.get()
        backseater = self._backseater_of(target_id)
        if backseater is None:
            self._log("Edit live value failed: no target platform selected.")
            return
        if self.selected_live_knowledge_key is None:
            return
        key = self.selected_live_knowledge_key
        knowledge = backseater.knowledge_database
        entry_type = knowledge.type_of(key)
        new_value = _LiveValueDialog(self, key, entry_type, knowledge.get(key)).result
        if new_value is None:
            return
        try:
            knowledge.set(key, new_value, origin_platform_id=self.own_platform_id)
        except ValueError as error:
            self._log(f"Edit live value failed: {error}")
            messagebox.showerror("Edit live value failed", str(error), parent=self)
            return
        self._log(f"Set '{key}' = {new_value!r} live on '{target_id}'.")
        self._refresh_live_knowledge_tree()

    def _schedule_live_knowledge_refresh(self) -> None:
        """Keeps the Live Control tab's table showing the target platform's
        actual current values -- e.g. a running move_to capability request's `arrived`
        flag flips on its own -- rather than only whatever it read once at
        window-open or after your last edit."""
        if not self.winfo_exists():
            return
        self._refresh_live_knowledge_tree()
        self._live_knowledge_refresh_job = self.after(LIVE_KNOWLEDGE_REFRESH_MS, self._schedule_live_knowledge_refresh)





    #===============# Edge Actions #===============#

    def _on_add_edge(self) -> None:
        """Opens the edge dialog and adds the result."""
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
        """Opens the edge dialog pre-filled with the selected edge and applies the result."""
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
        """Removes the selected edge."""
        selection = self.edges_tree.selection()
        if not selection:
            return
        source_id, index = self._edge_rows[selection[0]]
        self._set_draft(graph_draft.remove_edge(self.draft, source_id, index))





    #===============# Knowledge Actions #===============#

    def _on_add_knowledge_key(self) -> None:
        """Opens the knowledge dialog and declares the result."""
        result = _KnowledgeDialog(self).result
        if result is None:
            return
        key, entry_type, value = result
        try:
            self._set_draft(graph_draft.add_knowledge_key(self.draft, key, entry_type, value))
        except ValueError as error:
            messagebox.showerror("Add knowledge key failed", str(error), parent=self)

    def _on_edit_knowledge_key(self) -> None:
        """Opens the knowledge dialog pre-filled with the selected key, cascading a rename before the type/value edit."""
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
                # Cascades the rename to every capability request binding/edge condition
                # that references old_key, rather than leaving them dangling.
                draft = graph_draft.rename_knowledge_key(draft, old_key, new_key)
            draft = graph_draft.edit_knowledge_key(draft, new_key, entry_type, value)
            self._set_draft(draft)
        except ValueError as error:
            messagebox.showerror("Edit knowledge key failed", str(error), parent=self)

    def _on_remove_knowledge_key(self) -> None:
        """Removes the selected key's declaration."""
        selection = self.knowledge_tree.selection()
        if not selection:
            return
        self._set_draft(graph_draft.remove_knowledge_key(self.draft, selection[0]))





    #===============# Graph Tab Preview Mode #===============#

    def _on_preview_mode_changed(self) -> None:
        """Re-renders the preview, and starts the periodic refresh in Live mode."""
        self._refresh_preview()
        if self.preview_mode.get() == "live":
            self._schedule_live_preview_refresh()

    def _schedule_live_preview_refresh(self) -> None:
        """Keeps the Graph tab's Live preview up to date with the sim while that
        mode is selected -- this window is otherwise only refreshed in reaction
        to a user action, never on a per-tick basis like MissionDashboard."""
        if not self.winfo_exists() or self.preview_mode.get() != "live":
            return
        self._refresh_preview()
        self._live_preview_refresh_job = self.after(LIVE_PREVIEW_REFRESH_MS, self._schedule_live_preview_refresh)





    #===============# Refresh #===============#

    def _refresh_all(self) -> None:
        """Re-renders every draft view."""
        self._refresh_nodes_tree()
        self._refresh_capabilities_tree()
        self._refresh_edges_tree()
        self._refresh_knowledge_tree()
        self._refresh_preview()

    def _refresh_nodes_tree(self) -> None:
        """Re-renders the Nodes table (start node marked), keeping the selection."""
        self.nodes_tree.delete(*self.nodes_tree.get_children())
        for node_id, node in self.draft["nodes"].items():
            label = f"{node_id}{START_NODE_MARKER}" if node_id == self.draft.get("start") else node_id
            self.nodes_tree.insert("", tk.END, iid=node_id, text=label, values=(len(node["capabilities"]),))
        if self.selected_node_id not in self.draft["nodes"]:
            self.selected_node_id = None
        elif self.selected_node_id in self.nodes_tree.get_children():
            self.nodes_tree.selection_set(self.selected_node_id)

    def _refresh_capabilities_tree(self) -> None:
        """Re-renders the selected node's Capabilities table, keeping the selection."""
        self.capabilities_tree.delete(*self.capabilities_tree.get_children())
        if self.selected_node_id is None or self.selected_node_id not in self.draft["nodes"]:
            self.selected_request_name = None
            return
        capability_requests = self.draft["nodes"][self.selected_node_id]["capabilities"]
        for name, capability_request in capability_requests.items():
            self.capabilities_tree.insert("", tk.END, iid=name, values=(
                capability_request["capability"],
                ", ".join(f"{field}={key}" for field, key in capability_request.get("inputs", {}).items()),
                ", ".join(f"{field}={key}" for field, key in capability_request.get("outputs", {}).items()),
            ))
        if self.selected_request_name not in capability_requests:
            self.selected_request_name = None
        elif self.selected_request_name in self.capabilities_tree.get_children():
            self.capabilities_tree.selection_set(self.selected_request_name)

    def _refresh_edges_tree(self) -> None:
        """Re-renders the Edges table, recording which (source, index) each row is."""
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
        """Re-renders the draft's Knowledge table."""
        self.knowledge_tree.delete(*self.knowledge_tree.get_children())
        for key, declaration in self.draft["knowledge"].items():
            type_name = KNOWLEDGE_TYPE_NAMES.get(declaration["type"], declaration["type"].__name__)
            self.knowledge_tree.insert("", tk.END, iid=key, values=(key, type_name, repr(declaration["value"])))

    def _refresh_preview(self) -> None:
        """Re-renders the Graph tab: the draft, or (Live mode) the target platform's running graph."""
        self.preview_ax.clear()
        self.preview_ax.set_facecolor(GRAPH_PLOT_BACKGROUND)
        if self.preview_mode.get() == "live":
            target_id = self.target_platform_id.get()
            backseater = self._backseater_of(target_id)
            if backseater is None:
                self.preview_mode_note.config(text="No target platform selected.")
            else:
                status = backseater.status()
                self.mission_graph_viewer.render(
                    self.preview_ax, backseater.mission_graph, status["active_node_id"],
                    request_statuses=status["capabilities"], overall_status=status["overall_status"],
                )
                self.preview_mode_note.config(text=f"Live view of '{target_id}' -- read-only.")
        else:
            self.mission_graph_viewer.render(self.preview_ax, self.draft, active_node_id=None)
            self.preview_mode_note.config(text="Editing draft.")
        self.preview_canvas.draw_idle()





    #===============# Lifecycle #===============#

    def close(self) -> None:
        """Called by MissionEditorFrontseater when show_interface stops (or at
        shutdown) -- destroys this Toplevel. Tolerant of the window already being
        gone (e.g. the underlying Tk root was destroyed first during teardown).
        Cancels both periodic self.after() refresh loops first -- otherwise Tk
        logs "invalid command name" errors when a pending one fires after this
        widget no longer exists -- then flushes pending idle-draw callbacks and
        closes the preview figure before destroying the widgets they target,
        mirroring MissionDashboard._on_close (which logs the same class of error
        for idle_draw callbacks if that flush is skipped)."""
        try:
            if self.assistant_window is not None and self.assistant_window.winfo_exists():
                self.assistant_window.close()
            if self._live_preview_refresh_job is not None:
                self.after_cancel(self._live_preview_refresh_job)
            if self._live_knowledge_refresh_job is not None:
                self.after_cancel(self._live_knowledge_refresh_job)
            self.update_idletasks()
            plt.close(self.preview_fig)
            self.destroy()
        except tk.TclError:
            pass







#========================================#
# Widget Helpers
#========================================#

def _build_table(parent, columns: tuple, height: int) -> ttk.Treeview:
    """Builds and packs a headings-only Treeview from (column_id, heading, width)
    triples; only the last column stretches with the window."""
    tree = ttk.Treeview(parent, columns=[column_id for column_id, _, _ in columns], show="headings", height=height)
    stretch_column_id = columns[-1][0]
    for column_id, heading, width in columns:
        tree.heading(column_id, text=heading)
        tree.column(column_id, width=width, stretch=(column_id == stretch_column_id))
    tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    return tree


def _add_buttons(parent, buttons: tuple) -> None:
    """Packs one small button per (text, command) pair, left to right."""
    for text, command in buttons:
        ttk.Button(parent, text=text, command=command).pack(side=tk.LEFT, padx=PAD_TINY, pady=PAD_TINY)


def _center_over_parent(dialog, parent) -> None:
    """Positions `dialog` centered over `parent`'s current window, and raises it
    above every other window (`-topmost`) without seizing keyboard focus or
    forcing the OS to also raise/focus the rest of this app's windows."""
    # NOTE: transient() is deliberately not used by any dialog below, since it
    # visibly pulled every one of this app's windows to the front together
    # whenever a dialog appeared.
    dialog.update_idletasks()
    parent_x, parent_y = parent.winfo_rootx(), parent.winfo_rooty()
    parent_width, parent_height = parent.winfo_width(), parent.winfo_height()
    dialog_width, dialog_height = dialog.winfo_width(), dialog.winfo_height()
    x = parent_x + max((parent_width - dialog_width) // 2, 0)
    y = parent_y + max((parent_height - dialog_height) // 2, 0)
    dialog.geometry(f"+{x}+{y}")
    dialog.attributes("-topmost", True)


def _show_modal(dialog, parent) -> None:
    """Centers `dialog` over `parent`, grabs input, and blocks until it closes."""
    _center_over_parent(dialog, parent)
    dialog.grab_set()
    dialog.wait_window(dialog)


def _add_dialog_buttons(dialog, row: int, confirm_text: str, on_confirm) -> None:
    """Adds the confirm + Cancel button row spanning both grid columns at `row`."""
    buttons = ttk.Frame(dialog)
    buttons.grid(row=row, column=0, columnspan=2, pady=PAD_MEDIUM)
    ttk.Button(buttons, text=confirm_text, command=on_confirm).pack(side=tk.LEFT, padx=PAD_SMALL)
    ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=PAD_SMALL)


def _build_value_fields(parent_frame, entry_type: type, initial_value=None) -> dict:
    """Builds one labeled Entry per constructor field of `entry_type` (or a
    single "Value" field for a plain scalar type) inside `parent_frame`, via
    constructor_fields() introspection -- shared by _KnowledgeDialog (declaring/
    editing a key within a draft) and _LiveValueDialog (editing an already-
    declared key's value on a live platform), so both stay in sync automatically
    if a new KnowledgeEntry subclass is registered. Returns field_name -> StringVar."""
    if is_compound_knowledge_type(entry_type):
        fields = [(field_name, f"{field_name} ({getattr(annotation, '__name__', 'str')}):",
                   str(getattr(initial_value, field_name, "")) if initial_value is not None else "")
                  for field_name, annotation in constructor_fields(entry_type)]
    else:
        fields = [("value", "Value:", str(initial_value) if initial_value is not None else "")]

    field_vars = {}
    for row, (field_name, label, initial_text) in enumerate(fields):
        ttk.Label(parent_frame, text=label).grid(row=row, column=0, sticky="w", padx=PAD_SMALL, pady=PAD_TINY)
        variable = tk.StringVar(value=initial_text)
        ttk.Entry(parent_frame, textvariable=variable, width=FIELD_ENTRY_WIDTH).grid(
            row=row, column=1, sticky="ew", padx=PAD_SMALL, pady=PAD_TINY
        )
        field_vars[field_name] = variable
    return field_vars


def _read_value_fields(entry_type: type, field_vars: dict):
    """Inverse of _build_value_fields(): casts each field's text back into a
    value of `entry_type`, raising ValueError on bad input."""
    if is_compound_knowledge_type(entry_type):
        field_values = {}
        for field_name, annotation in constructor_fields(entry_type):
            caster = SCALAR_CASTERS.get(annotation, str)
            field_values[field_name] = caster(field_vars[field_name].get())
        return entry_type(**field_values)
    caster = SCALAR_CASTERS.get(entry_type, str)
    return caster(field_vars["value"].get())







#========================================#
# Dialogs
#========================================#

class _TextInputDialog(tk.Toplevel):
    """A single-line text-entry modal (Add Node / Rename Node), replacing
    tkinter.simpledialog.askstring so every dialog in this window is centered the
    same reliable way."""
    def __init__(self, parent, title: str, prompt: str, initial_value: str = ""):
        """Shows the dialog and blocks until it closes; the answer is in `result`."""
        super().__init__(parent)
        self.title(title)
        self.result = None

        ttk.Label(self, text=prompt).grid(row=0, column=0, sticky="w", padx=PAD_MEDIUM, pady=(PAD_MEDIUM, PAD_TINY))
        self.value_var = tk.StringVar(value=initial_value)
        entry = ttk.Entry(self, textvariable=self.value_var, width=TEXT_INPUT_WIDTH)
        entry.grid(row=1, column=0, padx=PAD_MEDIUM, pady=(0, PAD_MEDIUM))
        entry.focus_set()
        entry.bind("<Return>", lambda event: self._on_confirm())

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, pady=(0, PAD_MEDIUM))
        ttk.Button(buttons, text="OK", command=self._on_confirm).pack(side=tk.LEFT, padx=PAD_SMALL)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=PAD_SMALL)

        _show_modal(self, parent)

    def _on_confirm(self) -> None:
        """Keeps the trimmed text (None if empty) and closes."""
        self.result = self.value_var.get().strip() or None
        self.destroy()


class _CapabilityRequestDialog(tk.Toplevel):
    """Modal dialog for adding or editing a capability request on the selected node: a
    name, a capability dropdown (sourced from the target platform's own
    capabilities()), and one Knowledge-key-binding combobox per declared input/
    output field -- bindings are chosen from the draft's already-declared
    knowledge keys, mirroring the mission graph's own declare-before-use
    discipline. `existing`, when given, pre-fills every field for editing."""
    def __init__(self, parent, capability_registry, known_knowledge_keys: list, existing: tuple = None):
        """Shows the dialog and blocks until it closes; the answer is in `result`."""
        super().__init__(parent)
        self.title("Edit Capability" if existing else "Add Capability")
        self.result = None
        self._capability_registry = capability_registry
        self._known_knowledge_keys = known_knowledge_keys
        self._binding_vars = {}   # (kind, field_name) -> StringVar

        ttk.Label(self, text="Name:").grid(row=0, column=0, sticky="w", padx=PAD_MEDIUM, pady=PAD_SMALL)
        self.name_var = tk.StringVar(value=existing[0] if existing else "")
        ttk.Entry(self, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL)

        ttk.Label(self, text="Capability:").grid(row=1, column=0, sticky="w", padx=PAD_MEDIUM, pady=PAD_SMALL)
        self.capability_var = tk.StringVar(value=existing[1] if existing else "")
        capability_dropdown = ttk.Combobox(self, textvariable=self.capability_var, state="readonly",
                                            values=sorted(capability_registry.all()))
        capability_dropdown.grid(row=1, column=1, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL)
        capability_dropdown.bind("<<ComboboxSelected>>", lambda event: self._rebuild_binding_fields())

        self.bindings_frame = ttk.Frame(self)
        self.bindings_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=PAD_MEDIUM, pady=PAD_SMALL)

        _add_dialog_buttons(self, 3, "Save" if existing else "Add", self._on_confirm)

        self.columnconfigure(1, weight=1)
        if self.capability_var.get():
            self._rebuild_binding_fields(existing[2] if existing else None, existing[3] if existing else None)

        _show_modal(self, parent)

    def _rebuild_binding_fields(self, initial_inputs: dict = None, initial_outputs: dict = None) -> None:
        """Rebuilds one key-binding combobox per input/output field of the chosen capability."""
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
                    row=row, column=0, sticky="w", padx=PAD_SMALL, pady=PAD_TINY
                )
                variable = tk.StringVar(value=initial.get(spec.name, ""))
                ttk.Combobox(self.bindings_frame, textvariable=variable, values=self._known_knowledge_keys,
                             width=FIELD_ENTRY_WIDTH).grid(row=row, column=1, sticky="ew", padx=PAD_SMALL, pady=PAD_TINY)
                self._binding_vars[(kind, spec.name)] = variable
                row += 1

    def _on_confirm(self) -> None:
        """Keeps (name, capability, inputs, outputs), skipping unbound fields, and closes."""
        name = self.name_var.get().strip()
        capability = self.capability_var.get()
        if not name or not capability:
            messagebox.showerror("Capability", "Name and capability are required.", parent=self)
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
    accepted. `existing`, when given, pre-fills every field for editing."""
    # NOTE: exposing the real token format directly, rather than building a
    # structural condition builder, is a deliberate project decision.
    def __init__(self, parent, node_ids: list, existing: tuple = None):
        """Shows the dialog and blocks until it closes; the answer is in `result`."""
        super().__init__(parent)
        self.title("Edit Edge" if existing else "Add Edge")
        self.result = None

        ttk.Label(self, text="From:").grid(row=0, column=0, sticky="w", padx=PAD_MEDIUM, pady=PAD_SMALL)
        self.from_var = tk.StringVar(value=existing[0] if existing else node_ids[0])
        ttk.Combobox(self, textvariable=self.from_var, state="readonly", values=node_ids).grid(
            row=0, column=1, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL
        )

        ttk.Label(self, text="To:").grid(row=1, column=0, sticky="w", padx=PAD_MEDIUM, pady=PAD_SMALL)
        self.to_var = tk.StringVar(value=existing[1] if existing else node_ids[0])
        ttk.Combobox(self, textvariable=self.to_var, state="readonly", values=node_ids).grid(
            row=1, column=1, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL
        )

        ttk.Label(self, text='Condition tokens (Python literal, e.g. ["ugv1/arrived", "==", True]):').grid(
            row=2, column=0, columnspan=2, sticky="w", padx=PAD_MEDIUM, pady=(PAD_LARGE, 0)
        )
        self.condition_var = tk.StringVar(value=repr(existing[2]) if existing else "[]")
        ttk.Entry(self, textvariable=self.condition_var, width=CONDITION_ENTRY_WIDTH).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL
        )

        _add_dialog_buttons(self, 4, "Save" if existing else "Add", self._on_confirm)

        self.columnconfigure(1, weight=1)
        _show_modal(self, parent)

    def _on_confirm(self) -> None:
        """Keeps (from, to, condition) if the condition parses, else shows the error."""
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
    """Modal dialog for declaring or editing a Knowledge key: name, type (from the
    serialization module's type registry, the same set the editor can round-trip
    to/from a saved file), and one labeled field per constructor parameter of the
    chosen type -- generic via constructor_fields() introspection rather than a
    hardcoded per-type form, so a future KnowledgeEntry subclass needs only a
    registry entry to become editable here. `existing`, when given, pre-fills every
    field for editing, including the key itself -- the caller
    (MissionEditorWindow._on_edit_knowledge_key) is responsible for cascading a
    changed key through graph_draft.rename_knowledge_key() before applying the
    type/value change, so every capability request binding/edge condition referencing the
    old key follows the rename instead of being left dangling."""
    def __init__(self, parent, existing: tuple = None):
        """Shows the dialog and blocks until it closes; the answer is in `result`."""
        super().__init__(parent)
        self.title("Edit Knowledge Key" if existing else "Add Knowledge Key")
        self.result = None
        self._editing = existing is not None
        self._field_vars = {}   # field_name -> StringVar

        ttk.Label(self, text="Key:").grid(row=0, column=0, sticky="w", padx=PAD_MEDIUM, pady=PAD_SMALL)
        self.key_var = tk.StringVar(value=existing[0] if existing else "")
        ttk.Entry(self, textvariable=self.key_var).grid(row=0, column=1, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL)

        ttk.Label(self, text="Type:").grid(row=1, column=0, sticky="w", padx=PAD_MEDIUM, pady=PAD_SMALL)
        initial_type_name = KNOWLEDGE_TYPE_NAMES[existing[1]] if existing else DEFAULT_KNOWLEDGE_TYPE_NAME
        self.type_var = tk.StringVar(value=initial_type_name)
        type_dropdown = ttk.Combobox(self, textvariable=self.type_var, state="readonly",
                                      values=sorted(KNOWLEDGE_TYPES_BY_NAME))
        type_dropdown.grid(row=1, column=1, sticky="ew", padx=PAD_MEDIUM, pady=PAD_SMALL)
        type_dropdown.bind("<<ComboboxSelected>>", lambda event: self._rebuild_value_fields())

        self.fields_frame = ttk.Frame(self)
        self.fields_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=PAD_MEDIUM, pady=PAD_SMALL)

        _add_dialog_buttons(self, 3, "Save" if self._editing else "Add", self._on_confirm)

        self.columnconfigure(1, weight=1)
        self._rebuild_value_fields(existing[2] if existing else None)

        _show_modal(self, parent)

    def _rebuild_value_fields(self, initial_value=None) -> None:
        """Rebuilds the value fields for the chosen type."""
        for widget in self.fields_frame.winfo_children():
            widget.destroy()
        entry_type = KNOWLEDGE_TYPES_BY_NAME[self.type_var.get()]
        self._field_vars = _build_value_fields(self.fields_frame, entry_type, initial_value)

    def _on_confirm(self) -> None:
        """Keeps (key, type, value) if the value parses, else shows the error."""
        key = self.key_var.get().strip()
        entry_type = KNOWLEDGE_TYPES_BY_NAME[self.type_var.get()]
        if not key:
            messagebox.showerror("Knowledge key", "Key is required.", parent=self)
            return
        try:
            value = _read_value_fields(entry_type, self._field_vars)
        except ValueError as error:
            messagebox.showerror("Knowledge key", f"Invalid value: {error}", parent=self)
            return
        self.result = (key, entry_type, value)
        self.destroy()


class _LiveValueDialog(tk.Toplevel):
    """Modal dialog for editing a single already-declared Knowledge key's value
    directly on a live (running) platform, from the Live Control tab -- unlike
    _KnowledgeDialog (which declares/edits a key within a draft graph), the key
    and its type are both fixed here; only the value can change, and confirming
    applies immediately (there is no separate staged/pushed draft for Knowledge
    values, since a Knowledge write is not privilege-gated the way a Mission
    write is)."""
    def __init__(self, parent, key: str, entry_type: type, current_value):
        """Shows the dialog and blocks until it closes; the answer is in `result`."""
        super().__init__(parent)
        self.title(f"Edit Live Value: {key}")
        self.result = None
        self._entry_type = entry_type

        type_name = KNOWLEDGE_TYPE_NAMES.get(entry_type, getattr(entry_type, "__name__", "?"))
        ttk.Label(self, text=f"Key: {key}    Type: {type_name}").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=PAD_MEDIUM, pady=(PAD_MEDIUM, PAD_TINY)
        )

        self.fields_frame = ttk.Frame(self)
        self.fields_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=PAD_MEDIUM, pady=PAD_SMALL)
        self._field_vars = _build_value_fields(self.fields_frame, entry_type, current_value)

        _add_dialog_buttons(self, 2, "Save", self._on_confirm)

        self.columnconfigure(1, weight=1)
        _show_modal(self, parent)

    def _on_confirm(self) -> None:
        """Keeps the new value if it parses, else shows the error."""
        try:
            self.result = _read_value_fields(self._entry_type, self._field_vars)
        except ValueError as error:
            messagebox.showerror("Live value", f"Invalid value: {error}", parent=self)
            return
        self.destroy()
