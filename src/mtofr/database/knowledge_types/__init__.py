"""The Knowledge type library: KnowledgeEntry (base.py) plus one file per entry type.
Every module in this package is imported here, so a new type is just a new file: its
KnowledgeEntry subclass registers itself in KNOWLEDGE_TYPES_BY_NAME on import."""
import importlib
import pkgutil

from mtofr.database.knowledge_types.base import KNOWLEDGE_TYPE_NAMES, KNOWLEDGE_TYPES_BY_NAME, KnowledgeEntry
from mtofr.database.knowledge_types.location import Location
from mtofr.database.knowledge_types.pose import Pose


for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
