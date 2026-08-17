"""Defines the mission status visualization tool: a platform-agnostic dashboard
that wraps any Environment's EnvironmentViewer alongside capability-status,
mission-graph, and knowledge panels for whichever platform is selected."""
import tkinter as tk
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from mtofr.viz.mission_graph_view import MissionGraphViewer
from mtofr.viz.platform_overview_view import PlatformOverviewViewer

MISSION_OVERVIEW_ID = "Mission Overview"

#==========# Theme #==========#
BACKGROUND = "#3c3c3c"
PANEL_BACKGROUND = "#2b2b2b"
FOREGROUND = "#e0e0e0"
BORDER_COLOR = "#6e6e6e"
TOOLTIP_BACKGROUND = "#ffffe0"
PLOT_BACKGROUND = "white"   # the environment view keeps its original white background;
                             # only the surrounding ttk chrome uses the dark theme
GRAPH_PLOT_BACKGROUND = "#808080"   # mission graph gets a mid-gray background instead
PAUSED_BUTTON_BACKGROUND = "#8b3a3a"   # "pressed in" look while time is not passing
SCROLLBAR_THUMB = "#808080"

# Side panel container is a fixed size so switching between Capabilities/Knowledge
# (different column counts) never resizes the window.
SIDE_PANEL_WIDTH = 420
SIDE_PANEL_HEIGHT = 220

# Graph title bar is likewise a fixed size, so showing/hiding the edge-labels
# checkbox and back button when switching between Mission Overview and a single
# platform's mission graph never resizes the window either.
GRAPH_TITLE_WIDTH = 340
GRAPH_TITLE_HEIGHT = 30


class MissionDashboard:
    """Single Tkinter window: a platform dropdown, the environment-specific spatial
    view (every platform drawn, selected one highlighted, pannable/zoomable), a
    mission graph (active node highlighted, hover for details), and a combined
    capability-status/knowledge panel switchable via a selector. The dropdown's
    extra "Mission Overview" entry swaps the mission graph for a flat platform list
    (hover shows each platform's active primitives) and the knowledge panel for
    Relay's canonical cross-platform store, if a Relay is attached to the World.
    Also owns the sim's pause state. Knows nothing about any specific environment or
    platform type — it only calls World/Backseater/Knowledge/Relay's public query
    methods and delegates spatial rendering to whatever EnvironmentViewer it's given."""

    def __init__(self, world, environment_viewer, title: str = "MTOFR Mission Dashboard"):
        self.world = world
        self.environment_viewer = environment_viewer
        self.mission_graph_viewer = MissionGraphViewer()
        self.platform_overview_viewer = PlatformOverviewViewer()
        self._closed = False
        self._paused = False
        self._environment_view_initialized = False   # first render sets default limits;
                                                        # later ones preserve pan/zoom
        self._last_graph_hover_xy = (None, None)
        self._graph_tooltip = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_theme()

        entity_ids = list(world.backseaters.keys())
        self.selected_id = tk.StringVar(value=MISSION_OVERVIEW_ID)
        self.show_edge_labels = tk.BooleanVar(value=False)
        self.side_panel_choice = tk.StringVar(value="Knowledge")

        self._build_layout(entity_ids)
        self._refresh()

    #=====# Theme #=====#
    def _configure_theme(self) -> None:
        self.root.configure(background=BACKGROUND)
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BACKGROUND)
        style.configure("TLabel", background=BACKGROUND, foreground=FOREGROUND)
        style.configure("TCheckbutton", background=BACKGROUND, foreground=FOREGROUND)
        style.map("TCheckbutton", background=[("active", BACKGROUND)])

        style.configure("TButton", background=PANEL_BACKGROUND, foreground=FOREGROUND)
        style.map("TButton", background=[("active", BACKGROUND)])
        style.configure("Paused.TButton", background=PAUSED_BUTTON_BACKGROUND, foreground=FOREGROUND,
                         relief="sunken")
        style.map("Paused.TButton", background=[("active", PAUSED_BUTTON_BACKGROUND)])

        style.configure("TCombobox", fieldbackground=PANEL_BACKGROUND, background=PANEL_BACKGROUND,
                         foreground=FOREGROUND, arrowcolor=FOREGROUND,
                         selectbackground=PANEL_BACKGROUND, selectforeground=FOREGROUND)
        style.map("TCombobox",
                  fieldbackground=[("readonly", PANEL_BACKGROUND)],
                  foreground=[("readonly", FOREGROUND)],
                  selectbackground=[("readonly", PANEL_BACKGROUND)],
                  selectforeground=[("readonly", FOREGROUND)])
        # The dropdown list itself is a plain Tk Listbox, invisible to ttk styling —
        # without this it renders with default (white-on-white) colors.
        self.root.option_add("*TCombobox*Listbox.background", PANEL_BACKGROUND)
        self.root.option_add("*TCombobox*Listbox.foreground", FOREGROUND)
        self.root.option_add("*TCombobox*Listbox.selectBackground", BORDER_COLOR)
        self.root.option_add("*TCombobox*Listbox.selectForeground", FOREGROUND)

        style.configure("Treeview", background=PANEL_BACKGROUND, fieldbackground=PANEL_BACKGROUND,
                         foreground=FOREGROUND, bordercolor=BORDER_COLOR)
        style.configure("Treeview.Heading", background=BACKGROUND, foreground=FOREGROUND)
        style.map("Treeview", background=[("selected", "#5a5a5a")])

        style.configure("Vertical.TScrollbar", background=SCROLLBAR_THUMB, troughcolor=PANEL_BACKGROUND,
                         bordercolor=BORDER_COLOR, arrowcolor=FOREGROUND)
        style.map("Vertical.TScrollbar", background=[("active", FOREGROUND)])

        style.configure("TLabelframe", background=BACKGROUND, bordercolor=BORDER_COLOR)
        style.configure("TLabelframe.Label", background=BACKGROUND, foreground=FOREGROUND)

    #=====# Layout #=====#
    def _build_layout(self, entity_ids: list) -> None:
        top = ttk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=6)

        ttk.Label(top, text="Platform:").pack(side=tk.LEFT, padx=4)
        self.platform_dropdown = ttk.Combobox(top, values=entity_ids + [MISSION_OVERVIEW_ID],
                                               textvariable=self.selected_id, state="readonly")
        self.platform_dropdown.pack(side=tk.LEFT, padx=4)
        self.platform_dropdown.bind("<<ComboboxSelected>>", lambda event: self._refresh())

        self.pause_button = ttk.Button(top, text="⏸ Pause", command=self._toggle_pause)
        self.pause_button.pack(side=tk.LEFT, padx=10)

        body = ttk.Frame(self.root)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        self._build_environment_panel(body)
        self._build_side_panels(body)

    def _build_environment_panel(self, parent) -> None:
        environment_labelframe = ttk.LabelFrame(parent, text="Environment")
        environment_labelframe.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        self.environment_fig, self.environment_ax = plt.subplots(figsize=(5, 5))
        self.environment_fig.patch.set_facecolor(PLOT_BACKGROUND)
        self.environment_viewer.configure_ax(self.environment_ax)
        self.environment_canvas = FigureCanvasTkAgg(self.environment_fig, master=environment_labelframe)

        # NavigationToolbar2Tk provides pan (hand tool) and zoom (rectangle-select)
        # out of the box; it auto-packs itself at the bottom before the canvas below
        # claims the remaining space.
        toolbar = NavigationToolbar2Tk(self.environment_canvas, environment_labelframe)
        toolbar.update()
        self.environment_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _build_side_panels(self, parent) -> None:
        side = ttk.Frame(parent)
        side.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.graph_title = ttk.Frame(side, width=GRAPH_TITLE_WIDTH, height=GRAPH_TITLE_HEIGHT)
        self.graph_title.pack_propagate(False)   # fixed size: showing/hiding controls below must not resize anything
        ttk.Label(self.graph_title, text="Mission Overview").pack(side=tk.LEFT)
        # Only meaningful for a single selected platform's mission graph -- hidden
        # while the Mission Overview platform list is showing instead.
        self.edge_labels_checkbox = ttk.Checkbutton(
            self.graph_title, text="Show edge labels", variable=self.show_edge_labels, command=self._refresh
        )
        self.back_to_overview_button = ttk.Button(
            self.graph_title, text="⬅ Overview", command=self._deselect_platform
        )
        graph_labelframe = ttk.LabelFrame(side, labelwidget=self.graph_title)
        graph_labelframe.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.graph_fig, self.graph_ax = plt.subplots(figsize=(4, 3))
        self.graph_fig.patch.set_facecolor(GRAPH_PLOT_BACKGROUND)
        self.graph_canvas = FigureCanvasTkAgg(self.graph_fig, master=graph_labelframe)
        self.graph_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.graph_canvas.mpl_connect("motion_notify_event", self._on_graph_hover)
        self.graph_canvas.mpl_connect("button_press_event", self._on_graph_click)

        panel_title = ttk.Frame(side)
        ttk.Label(panel_title, text="Panel:").pack(side=tk.LEFT)
        selector = ttk.Combobox(panel_title, values=["Capabilities", "Knowledge"],
                                 textvariable=self.side_panel_choice, state="readonly", width=12)
        selector.pack(side=tk.LEFT, padx=6)
        selector.bind("<<ComboboxSelected>>", lambda event: self._show_selected_side_panel())
        panel_labelframe = ttk.LabelFrame(side, labelwidget=panel_title)
        panel_labelframe.pack(fill=tk.BOTH, expand=True)

        self.side_panel_container = ttk.Frame(panel_labelframe, width=SIDE_PANEL_WIDTH, height=SIDE_PANEL_HEIGHT)
        self.side_panel_container.pack(fill=tk.BOTH, expand=True)
        self.side_panel_container.pack_propagate(False)   # fixed size: swapping panels must not resize the window

        self.capabilities_frame, self.capability_tree = self._build_scrollable_tree(
            self.side_panel_container, columns=(("type", "Type"), ("status", "Status"), ("inputs", "Inputs"))
        )
        # Name/Type default narrower than Value so all three columns fit inside
        # SIDE_PANEL_WIDTH without needing to resize the window on startup.
        self.knowledge_frame, self.knowledge_tree = self._build_scrollable_tree(
            self.side_panel_container, columns=(("name", "Name"), ("type", "Type"), ("value", "Value")),
            widths={"name": 90, "type": 70, "value": 220},
        )
        self._show_selected_side_panel()

    @staticmethod
    def _build_scrollable_tree(parent, columns: tuple, widths: dict = None) -> tuple:
        """Builds a Treeview with an always-visible vertical scrollbar and
        mouse-wheel binding (so scrolling works on hover, without first clicking
        to focus)."""
        frame = ttk.Frame(parent)
        column_ids = [column_id for column_id, _ in columns]
        tree = ttk.Treeview(frame, columns=column_ids, show="headings", height=8)
        for column_id, heading in columns:
            tree.heading(column_id, text=heading)
            if widths and column_id in widths:
                tree.column(column_id, width=widths[column_id])

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)   # packed before the tree so it always claims its strip
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree.bind("<MouseWheel>", lambda event: tree.yview_scroll(int(-event.delta / 120), "units"))
        return frame, tree

    def _show_selected_side_panel(self) -> None:
        self.capabilities_frame.pack_forget()
        self.knowledge_frame.pack_forget()
        if self.side_panel_choice.get() == "Knowledge":
            self.knowledge_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.capabilities_frame.pack(fill=tk.BOTH, expand=True)

    #=====# Hover / click #=====#
    def _on_graph_hover(self, event) -> None:
        # event.x/event.y are display (pixel) coordinates, which stay correctly
        # matched to the (fixed-size, in points) node/edge markers across resizes,
        # pans, and zooms — unlike event.xdata/event.ydata, whose relationship to
        # on-screen pixels changes with the current view.
        self._last_graph_hover_xy = (event.x, event.y)
        self._apply_graph_hover()
        self.graph_canvas.draw_idle()

    def _on_graph_click(self, event) -> None:
        """Clicking a platform row in the Mission Overview list selects that
        platform, the same as picking it from the dropdown."""
        if self.selected_id.get() != MISSION_OVERVIEW_ID:
            return
        platform_id = self.platform_overview_viewer.find_platform_id_at(event.x, event.y)
        if platform_id is not None:
            self.selected_id.set(platform_id)
            self._refresh()

    def _deselect_platform(self) -> None:
        """Returns from a single platform's mission graph back to the Mission
        Overview platform list."""
        self.selected_id.set(MISSION_OVERVIEW_ID)
        self._refresh()

    def _apply_graph_hover(self) -> None:
        if self._graph_tooltip is None:
            return
        display_x, display_y = self._last_graph_hover_xy
        label = None
        if display_x is not None and display_y is not None:
            if self.selected_id.get() == MISSION_OVERVIEW_ID:
                label = self.platform_overview_viewer.find_platform_label_at(display_x, display_y)
            else:
                label = (self.mission_graph_viewer.find_node_label_at(display_x, display_y)
                         or self.mission_graph_viewer.find_edge_label_at(display_x, display_y))
        if not label:
            self._graph_tooltip.set_visible(False)
            return

        # Keep the tooltip fully on-screen: flip its offset toward the panel's
        # interior whenever the anchor point is near the right/top edge, instead of
        # always growing right/up and running off the canvas.
        canvas_width, canvas_height = self.graph_canvas.get_width_height()
        offset_x = 15 if display_x < canvas_width * 0.7 else -15
        offset_y = 15 if display_y < canvas_height * 0.7 else -15

        data_x, data_y = self.graph_ax.transData.inverted().transform((display_x, display_y))
        self._graph_tooltip.xy = (data_x, data_y)
        self._graph_tooltip.xyann = (offset_x, offset_y)
        self._graph_tooltip.set_ha("left" if offset_x > 0 else "right")
        self._graph_tooltip.set_va("bottom" if offset_y > 0 else "top")
        self._graph_tooltip.set_text(label)
        self._graph_tooltip.set_visible(True)

    #=====# Refresh #=====#
    def _refresh(self) -> None:
        self._refresh_environment_panel()
        self._update_graph_panel_controls()

        if self.selected_id.get() == MISSION_OVERVIEW_ID:
            self.capability_tree.delete(*self.capability_tree.get_children())
            self._refresh_platform_overview()
            self._refresh_knowledge_tree(self.world.relay)
            return

        backseater = self.world.backseaters.get(self.selected_id.get())
        if backseater is None:
            return

        status = backseater.status()
        self._refresh_capability_tree(backseater, status)
        self._refresh_mission_graph(backseater, status)
        self._refresh_knowledge_tree(backseater.knowledge)

    def _update_graph_panel_controls(self) -> None:
        """The edge-labels checkbox and "back to overview" button only make sense
        for a single selected platform's mission graph -- hidden while the
        Mission Overview platform list is showing instead."""
        if self.selected_id.get() == MISSION_OVERVIEW_ID:
            self.edge_labels_checkbox.pack_forget()
            self.back_to_overview_button.pack_forget()
        else:
            self.edge_labels_checkbox.pack(side=tk.LEFT, padx=10)
            self.back_to_overview_button.pack(side=tk.LEFT, padx=10)

    def _refresh_environment_panel(self) -> None:
        states = self.world.get_states()
        # Preserve any pan/zoom the user has applied via the toolbar: only the very
        # first render sets the viewer's default limits, since ax.clear() below
        # would otherwise reset them back to that default every tick.
        view_limits = (self.environment_ax.get_xlim(), self.environment_ax.get_ylim())

        self.environment_ax.clear()
        self.environment_ax.set_facecolor(PLOT_BACKGROUND)
        if self._environment_view_initialized:
            self.environment_ax.set_xlim(view_limits[0])
            self.environment_ax.set_ylim(view_limits[1])
            self.environment_ax.set_aspect("equal")
        else:
            self.environment_viewer.configure_ax(self.environment_ax)
            self._environment_view_initialized = True
        self.environment_viewer.render(self.environment_ax, states, selected_id=self.selected_id.get())
        self.environment_canvas.draw_idle()

    def _refresh_capability_tree(self, backseater, status: dict) -> None:
        self.capability_tree.delete(*self.capability_tree.get_children())
        for name, info in status["primitives"].items():
            inputs_text = ", ".join(
                f"{field_name}={backseater.knowledge.get(key)!r}"
                for field_name, key in info["inputs"].items()
            )
            self.capability_tree.insert(
                "", tk.END, iid=name, values=(info["capability"], info["status"], inputs_text)
            )

    def _refresh_mission_graph(self, backseater, status: dict) -> None:
        self.graph_ax.clear()
        self.graph_ax.set_facecolor(GRAPH_PLOT_BACKGROUND)
        self.mission_graph_viewer.render(
            self.graph_ax, backseater.mission_graph, status["active_node_id"],
            primitive_statuses=status["primitives"], show_edge_labels=self.show_edge_labels.get(),
        )
        self._graph_tooltip = self.graph_ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round", fc=TOOLTIP_BACKGROUND, ec="gray"), zorder=10, visible=False,
        )
        self._apply_graph_hover()
        self.graph_canvas.draw_idle()

    def _refresh_platform_overview(self) -> None:
        self.graph_ax.clear()
        self.graph_ax.set_facecolor(GRAPH_PLOT_BACKGROUND)
        self.platform_overview_viewer.render(self.graph_ax, self.world.backseaters)
        self._graph_tooltip = self.graph_ax.annotate(
            "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
            bbox=dict(boxstyle="round", fc=TOOLTIP_BACKGROUND, ec="gray"), zorder=10, visible=False,
        )
        self._apply_graph_hover()
        self.graph_canvas.draw_idle()

    def _refresh_knowledge_tree(self, knowledge_source) -> None:
        """`knowledge_source` is anything exposing `.all()` — a platform's own
        Knowledge, or the Relay's canonical cross-platform store."""
        self.knowledge_tree.delete(*self.knowledge_tree.get_children())
        if knowledge_source is None:
            return
        for entry_id, entry in knowledge_source.all().items():
            type_name = type(entry).__name__
            self.knowledge_tree.insert(
                "", tk.END, iid=entry_id, values=(entry_id, type_name, self._describe_entry_value(entry, type_name))
            )

    @staticmethod
    def _describe_entry_value(entry, type_name: str) -> str:
        """Strips the leading "TypeName(" / trailing ")" off entry's repr, so the
        Knowledge panel's Value column shows just the fields (the Type column
        already names the class)."""
        text = repr(entry)
        prefix, suffix = f"{type_name}(", ")"
        if text.startswith(prefix) and text.endswith(suffix):
            return text[len(prefix):-len(suffix)]
        return text

    #=====# Lifecycle #=====#
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.pause_button.config(text="▶ Play", style="Paused.TButton")
        else:
            self.pause_button.config(text="⏸ Pause", style="TButton")

    def is_paused(self) -> bool:
        return self._paused

    def update(self) -> None:
        """Refreshes every panel and pumps the Tk event loop. Call once per sim tick."""
        if self._closed:
            return
        self._refresh()
        self.root.update_idletasks()
        self.root.update()

    def is_open(self) -> bool:
        return not self._closed

    def _on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Flush pending idle-draw callbacks before tearing down the widgets they
        # target, otherwise Tk logs "invalid command name ...idle_draw" errors.
        self.root.update_idletasks()
        plt.close(self.environment_fig)
        plt.close(self.graph_fig)
        self.root.destroy()
