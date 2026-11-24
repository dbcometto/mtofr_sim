"""The interface platform's web UI: a stdlib HTTP server (server.py) in front of a WebHost
(host.py) that owns a set of WebPanels (panel.py, panels/). Everything a panel reads comes
from an InterfaceView (view.py) of the interface's own Backseater databases, captured on
the sim thread each tick, and everything it writes is queued for that thread to publish
through the same Backseater, so the UI never touches World and carries over to hardware."""
