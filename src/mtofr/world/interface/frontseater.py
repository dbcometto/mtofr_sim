"""Defines the mission-editor "interface" platform's Frontseater."""
from typing import Callable, Optional

from mtofr.world.base import Frontseater, WorldState
from mtofr.world.interface.hardware import ConsoleHardware
from mtofr.capability.capability import Capability, CapabilityRegistry


class MissionEditorFrontseater(Frontseater):
    """Hosts the mission-editor GUI as a side effect of its one capability,
    show_interface, rather than modeling graph-editing itself as capabilities --
    editing is entirely user-driven, not part of the mission-graph/capability
    machinery any other platform uses (see mtofr.world.interface.mission_editor for the actual
    editing logic and mtofr.world.interface.mission_editor.window for the GUI it opens/closes).
    Never computes real controls; ConsoleHardware ignores them regardless."""

    def __init__(self, hardware: ConsoleHardware, debug: bool = False):
        self.hardware = hardware
        self.backseater = None   # set by Backseater's constructor
        self.debug = debug
        self._window = None
        self._window_factory: Optional[Callable[[], object]] = None

        self._capability_registry = CapabilityRegistry([
            Capability(
                ipl_type="show_interface",
                description="Opens the mission-editor window while active; closes it when stopped.",
            ),
        ])

    #==========# Window wiring #==========#

    def set_window_factory(self, window_factory: Callable[[], object]) -> None:
        """Supplies the callable that builds this platform's MissionEditorWindow --
        set post-construction (by main.py, after World/MissionDashboard exist),
        since the window needs a Tk root and a World reference, neither of which
        exist yet when this Frontseater itself is built."""
        self._window_factory = window_factory

    #==========# Capability discovery #==========#

    def capabilities(self) -> CapabilityRegistry:
        return self._capability_registry

    def default_mission_graph(self) -> dict:
        """Always active: a single node with no edges, running show_interface
        unconditionally -- the "interface platform" pattern from notes.md."""
        return {
            "knowledge": {},
            "nodes": {"operating": {"primitives": {
                "interface": {"capability": "show_interface", "inputs": {}, "outputs": {}},
            }}},
            "edges": {},
            "start": "operating",
        }

    #==========# Capability lifecycle #==========#

    def set_active_primitives(self, primitives: dict) -> None:
        """The one entry point Backseater calls -- diffs by whether "interface" is
        present, opening/closing the window rather than running anything per-tick."""
        showing = "interface" in primitives
        if showing and self._window is None:
            if self._window_factory is None:
                raise RuntimeError(
                    "MissionEditorFrontseater has no window_factory set -- call set_window_factory() first"
                )
            self._window = self._window_factory()
            if self.debug:
                print("[Frontseater] show_interface -> window opened")
        elif not showing and self._window is not None:
            self._window.close()
            self._window = None
            if self.debug:
                print("[Frontseater] show_interface -> window closed")

    #==========# Status introspection #==========#

    def describe_status(self) -> dict:
        if self._window is None:
            return {"overall": "idle", "primitives": {}}
        return {"overall": "showing interface", "primitives": {"interface": "open"}}

    #==========# Controls #==========#

    def compute_controls(self, state: WorldState) -> dict:
        return {}

    #==========# Lifecycle #==========#

    def shutdown(self) -> None:
        """No OS-level resource to tear down here (no worker process, unlike
        BicycleFrontseater) -- but main.py calls shutdown() on every Frontseater
        unconditionally at exit, so this must exist. Also closes the window if
        still open, since Tk widgets should be destroyed before interpreter exit."""
        if self._window is not None:
            self._window.close()
            self._window = None