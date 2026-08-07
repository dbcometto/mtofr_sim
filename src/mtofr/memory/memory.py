"""Defines memory"""

#==========# Main Memory Storage #==========#

class Memory:
    """Per-agent memory: typed store of known entities (locations, later agents, conditions, etc). 
    Each agent owns its own Memory instance."""

    def __init__(self):
        self._entries = {}   # id -> entry object

    def add(self, id: str, entry) -> None:
        self._entries[id] = entry

    def get(self, id: str):
        return self._entries[id]

    def all_of_type(self, cls) -> dict:
        return {id: e for id, e in self._entries.items() if isinstance(e, cls)}


#==========# Individual Memories #==========#

class Location:
    """A location memory (2D)"""
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __repr__(self):
        return f"Location(x={self.x}, y={self.y})"