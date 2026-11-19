"""Defines knowledge-based edge conditions: a small typed expression tree, parsed from a
pre-tokenized list, and evaluated against a Knowledge store without eval() or string parsing
of literals. The mission graph author supplies real Python values (True/None/1.0/...) already
interspersed with string tokens for keys/operators/keywords/parens."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


#========================================#
# Config
#========================================#

COMPARISON_OPERATORS = {
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
}
IS_TOKEN = "is"
# Every token that may directly follow a knowledge key; the grammar never places one
# anywhere else after a key, which is what lets an editor find key tokens by position.
KEY_FOLLOWER_TOKENS = frozenset(COMPARISON_OPERATORS) | {IS_TOKEN}
_RESERVED_TOKENS = ("(", ")", "and", "or", "not", IS_TOKEN)   # never valid as a knowledge key







#========================================#
# Condition Tree
#========================================#

class ConditionNode(ABC):
    """One node of a parsed condition expression."""
    @abstractmethod
    def evaluate(self, knowledge) -> bool:
        """Evaluates this node against the current Knowledge store."""

    @abstractmethod
    def keys(self) -> set[str]:
        """Every Knowledge key referenced anywhere in this node's subtree. The
        structural-verify gate on a Mission write uses this to check every edge
        condition's keys are declared in the new graph's own "knowledge" section."""


@dataclass(frozen=True)
class Comparison(ConditionNode):
    """key <op> value, e.g. "ugv1/battery" > 0.9."""
    key: str
    operator: str
    value: object

    def evaluate(self, knowledge) -> bool:
        """Applies the operator to the key's current value and the literal."""
        return COMPARISON_OPERATORS[self.operator](knowledge.get(self.key), self.value)

    def keys(self) -> set[str]:
        """The one key this comparison reads."""
        return {self.key}


@dataclass(frozen=True)
class IsNone(ConditionNode):
    """key is [not] None."""
    key: str
    negated: bool = False

    def evaluate(self, knowledge) -> bool:
        """True if the key's value is None (or is not None, when negated)."""
        result = knowledge.get(self.key) is None
        return not result if self.negated else result

    def keys(self) -> set[str]:
        """The one key this check reads."""
        return {self.key}


@dataclass(frozen=True)
class And(ConditionNode):
    """True when every operand is true."""
    operands: tuple[ConditionNode, ...]

    def evaluate(self, knowledge) -> bool:
        """Short-circuit conjunction of the operands."""
        return all(operand.evaluate(knowledge) for operand in self.operands)

    def keys(self) -> set[str]:
        """Union of every operand's keys."""
        return set().union(*(operand.keys() for operand in self.operands))


@dataclass(frozen=True)
class Or(ConditionNode):
    """True when any operand is true."""
    operands: tuple[ConditionNode, ...]

    def evaluate(self, knowledge) -> bool:
        """Short-circuit disjunction of the operands."""
        return any(operand.evaluate(knowledge) for operand in self.operands)

    def keys(self) -> set[str]:
        """Union of every operand's keys."""
        return set().union(*(operand.keys() for operand in self.operands))


@dataclass(frozen=True)
class Not(ConditionNode):
    """Negates its one operand."""
    operand: ConditionNode

    def evaluate(self, knowledge) -> bool:
        """The operand's result, inverted."""
        return not self.operand.evaluate(knowledge)

    def keys(self) -> set[str]:
        """The operand's keys."""
        return self.operand.keys()







#========================================#
# Parser
#========================================#

class ConditionSyntaxError(ValueError):
    """Raised when a condition token list is malformed."""


_END_OF_TOKENS = object()   # distinct from a literal None token in the list


class _Parser:
    """Recursive-descent parser over a pre-tokenized condition list.
    Grammar (highest to lowest precedence): atom > not_expr > and_expr > or_expr."""
    def __init__(self, tokens: list):
        """Starts at the first of `tokens`."""
        self._tokens = tokens
        self._position = 0

    def parse(self) -> ConditionNode:
        """Parses the whole token list; raises if any tokens are left over."""
        node = self._parse_or()
        if self._position != len(self._tokens):
            raise ConditionSyntaxError(f"Unexpected trailing token: {self._peek()!r}")
        return node

    def _peek(self):
        """The next token without consuming it, or _END_OF_TOKENS."""
        return self._tokens[self._position] if self._position < len(self._tokens) else _END_OF_TOKENS

    def _advance(self):
        """Consumes and returns the next token; raises at the end of the list."""
        token = self._peek()
        if token is _END_OF_TOKENS:
            raise ConditionSyntaxError("Unexpected end of condition tokens")
        self._position += 1
        return token

    def _parse_or(self) -> ConditionNode:
        """or_expr := and_expr ("or" and_expr)*"""
        operands = [self._parse_and()]
        while self._peek() == "or":
            self._advance()
            operands.append(self._parse_and())
        return operands[0] if len(operands) == 1 else Or(tuple(operands))

    def _parse_and(self) -> ConditionNode:
        """and_expr := not_expr ("and" not_expr)*"""
        operands = [self._parse_not()]
        while self._peek() == "and":
            self._advance()
            operands.append(self._parse_not())
        return operands[0] if len(operands) == 1 else And(tuple(operands))

    def _parse_not(self) -> ConditionNode:
        """not_expr := "not" not_expr | atom"""
        if self._peek() == "not":
            self._advance()
            return Not(self._parse_not())
        return self._parse_atom()

    def _parse_atom(self) -> ConditionNode:
        """atom := "(" or_expr ")" | comparison"""
        if self._peek() == "(":
            self._advance()
            node = self._parse_or()
            if self._advance() != ")":
                raise ConditionSyntaxError("Expected closing ')'")
            return node
        return self._parse_comparison_or_is()

    def _parse_comparison_or_is(self) -> ConditionNode:
        """comparison := key operator value | key "is" ["not"] None"""
        key = self._advance()
        if not isinstance(key, str) or key in _RESERVED_TOKENS:
            raise ConditionSyntaxError(f"Expected a knowledge key, got {key!r}")

        operator = self._advance()
        if operator in COMPARISON_OPERATORS:
            value = self._advance()
            return Comparison(key, operator, value)

        if operator == IS_TOKEN:
            negated = False
            if self._peek() == "not":
                self._advance()
                negated = True
            if self._advance() is not None:
                raise ConditionSyntaxError("Expected None after 'is [not]'")
            return IsNone(key, negated=negated)

        raise ConditionSyntaxError(f"Expected a comparison operator or 'is', got {operator!r}")


def parse_condition(tokens: list) -> ConditionNode:
    """Parses a pre-tokenized condition list into a ConditionNode tree.
    Raises ConditionSyntaxError on malformed input."""
    if not tokens:
        raise ConditionSyntaxError("Condition token list is empty")
    return _Parser(tokens).parse()
