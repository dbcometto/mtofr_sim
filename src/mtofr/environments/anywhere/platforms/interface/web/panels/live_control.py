"""Defines LiveControlPanel: the interface platform's view of the whole mesh's Knowledge,
with live edits published through its own Backseater (they reach peers by mesh sync)."""
from mtofr.environments.anywhere.platforms.interface.mission_editor.assistant_tools import as_knowledge_value
from mtofr.environments.anywhere.platforms.interface.web.config import BUILT_IN_PANEL_SCRIPT_DIRECTORY
from mtofr.environments.anywhere.platforms.interface.web.encoding import knowledge_type_fields, type_name
from mtofr.environments.anywhere.platforms.interface.web.panel import PanelContext, WebPanel, reply
from mtofr.mission.serialization import encode_value


class LiveControlPanel(WebPanel):
    """Every Knowledge key the interface platform holds (its own and every peer's, as
    synced), with its value, origin, age, and how long since the interface last synced with
    that origin; edits steer a running mission through its existing edges without authoring
    a new graph.

    Two kinds of row are *pending* (not yet processed), so the browser can show them apart:
    - a value this window queued that hasn't been applied yet (it applies at the interface's
      next tick, so it stays pending while the sim is paused);
    - a key some known mission declares that hasn't reached the interface yet (e.g. just
      after a push, until the Target adopts the mission and syncs back), shown with its
      declared default."""
    name = "live_control"
    title = "Live Control"
    script_path = BUILT_IN_PANEL_SCRIPT_DIRECTORY / "live_control.js"

    def __init__(self):
        """Nothing queued yet."""
        # key -> (encoded value, view.time when queued). Queued writes run at the start of the next
        # tick, just before that tick's view is captured, so a value is pending exactly while the
        # view is still the one it was queued against (applied or refused, a newer view settles it).
        self._pending_values = {}

    def state(self, context: PanelContext) -> dict:
        """One row per Knowledge key (plus pending ones), and every type's form fields."""
        view = context.view
        self._pending_values = {key: queued for key, queued in self._pending_values.items() if queued[1] == view.time}
        rows = {}
        for key, row in view.knowledge.items():
            encoded = encode_value(row.value)
            pending_value = self._pending_values[key][0] if key in self._pending_values else None
            rows[key] = {
                "key": key,
                "type": type_name(row.entry_type),
                "value": encoded if pending_value is None else pending_value,
                "origin": row.origin_platform_id,
                "age": None if row.timestamp is None or view.time is None else view.time - row.timestamp,   # s since written
                "synced_age": view.sync_age(row.origin_platform_id),   # s since the interface synced with the origin
                "pending": pending_value is not None,
            }
        for platform_id, mission_graph in view.missions.items():
            for key, declaration in mission_graph.get("knowledge", {}).items():
                if key not in rows:
                    rows[key] = {"key": key, "type": type_name(declaration["type"]), "value": encode_value(declaration["value"]),
                                 "origin": platform_id, "age": None, "synced_age": view.sync_age(platform_id), "pending": True}
        return {"rows": [rows[key] for key in sorted(rows)], "knowledge_types": knowledge_type_fields()}

    def commands(self) -> dict:
        """set_value only."""
        return {"set_value": self.set_value}

    def set_value(self, context: PanelContext, key: str, value) -> dict:
        """Queues publishing `value` (a scalar's text, or a field-text dict) to `key`, cast to the key's own type."""
        row = context.view.knowledge.get(key)
        if row is None:
            return reply(False, f"Knowledge key '{key}' is not known here yet.")
        try:
            new_value = as_knowledge_value(row.entry_type, value)
        except ValueError as error:
            return reply(False, f"Bad value for '{key}': {error}")

        def publish_value(backseater) -> str:
            """Publishes the new value through the interface's own Backseater."""
            backseater.publish("knowledge", key, new_value)
            return f"now {new_value!r}"

        self._pending_values[key] = (encode_value(new_value), context.view.time)
        context.submit(f"Set '{key}'", publish_value)
        return reply(True, f"Queued: set '{key}' to {new_value!r}.")
