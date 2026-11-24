"""Defines KnowledgeEntry, the ABC every richer object type stored in a KnowledgeDatabase
implements, and the name<->type registry every subclass joins automatically."""
from abc import ABC, abstractmethod


# Every declarable Knowledge type by name: the plain scalars, plus each concrete
# KnowledgeEntry subclass, added by KnowledgeEntry.__init_subclass__ as its module is imported.
KNOWLEDGE_TYPES_BY_NAME: dict[str, type] = {"bool": bool, "float": float, "int": int, "str": str}
KNOWLEDGE_TYPE_NAMES: dict[type, str] = {entry_type: name for name, entry_type in KNOWLEDGE_TYPES_BY_NAME.items()}


class KnowledgeEntry(ABC):
    """Base for typed knowledge entries. Platforms/systems are free to define their own entry
    types beyond the built-in ones — every entry type must self-describe in plaintext
    so a planner LLM or human can understand a custom type without reading its source, the
    same self-description contract Capability/ParamSpec use.

    A concrete subclass registers itself by class name, which makes it declarable, editable,
    and saveable.  Its __init__ takes only bool/float/int/str-annotated parameters, each
    stored as a same-named attribute (see mission.serialization.constructor_fields())."""

    def __init_subclass__(cls, **kwargs):
        """Registers a concrete subclass (one that implements describe()) under its class name."""
        super().__init_subclass__(**kwargs)
        # NOTE: checked on describe itself, since ABCMeta only computes __abstractmethods__
        # after this hook runs.
        if getattr(cls.describe, "__isabstractmethod__", False):
            return
        existing = KNOWLEDGE_TYPES_BY_NAME.get(cls.__name__)
        if existing is not None and existing is not cls:
            raise ValueError(f"Knowledge type name '{cls.__name__}' is already taken by {existing!r}")
        KNOWLEDGE_TYPES_BY_NAME[cls.__name__] = cls
        KNOWLEDGE_TYPE_NAMES[cls] = cls.__name__

    @classmethod
    @abstractmethod
    def describe(cls) -> str:
        """Plaintext description of what this entry type represents and its fields."""
