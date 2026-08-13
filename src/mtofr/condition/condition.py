"""Defines knowledge-based edge conditions: a small typed expression tree, parsed from a
pre-tokenized list, and evaluated against a Knowledge store without eval() or string parsing
of literals — the mission graph author supplies real Python values (True/None/1.0/...) already
interspersed with string tokens for keys/operators/keywords/parens."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

_COMPARISON_OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


#==========# Condition tree #==========#

class ConditionNode(ABC):
    """One node of a parsed condition expression."""
    @abstractmethod
    def evaluate(self, knowledge) -> bool:
        """Evaluates this node against the current Knowledge store."""


@dataclass(frozen=True)
class Comparison(ConditionNode):
    """key <op> value, e.g. "ugv1/battery" > 0.9."""
    key: str
    operator: str
    value: object

    def evaluate(self, knowledge) -> bool:
        return _COMPARISON_OPERATORS[self.operator](knowledge.get(self.key), self.value)


@dataclass(frozen=True)
class IsNone(ConditionNode):
    """key is [not] None."""
    key: str
    negated: bool = False

    def evaluate(self, knowledge) -> bool:
        result = knowledge.get(self.key) is None
        return not result if self.negated else result


@dataclass(frozen=True)
class And(ConditionNode):
    operands: tuple[ConditionNode, ...]

    def evaluate(self, knowledge) -> bool:
        return all(operand.evaluate(knowledge) for operand in self.operands)


@dataclass(frozen=True)
class Or(ConditionNode):
    operands: tuple[ConditionNode, ...]

    def evaluate(self, knowledge) -> bool:
        return any(operand.evaluate(knowledge) for operand in self.operands)


@dataclass(frozen=True)
class Not(ConditionNode):
    operand: ConditionNode

    def evaluate(self, knowledge) -> bool:
        return not self.operand.evaluate(knowledge)


#==========# Parser #==========#

class ConditionSyntaxError(ValueError):
    """Raised when a condition token list is malformed."""


_END_OF_TOKENS = object()   # distinct from a literal None token in the list


class _Parser:
    """Recursive-descent parser over a pre-tokenized condition list.
    Grammar (highest to lowest precedence): atom > not_expr > and_expr > or_expr."""
    def __init__(self, tokens: list):
        self._tokens = tokens
        self._position = 0

    def parse(self) -> ConditionNode:
        node = self._parse_or()
        if self._position != len(self._tokens):
            raise ConditionSyntaxError(f"Unexpected trailing token: {self._peek()!r}")
        return node

    def _peek(self):
        return self._tokens[self._position] if self._position < len(self._tokens) else _END_OF_TOKENS

    def _advance(self):
        token = self._peek()
        if token is _END_OF_TOKENS:
            raise ConditionSyntaxError("Unexpected end of condition tokens")
        self._position += 1
        return token

    def _parse_or(self) -> ConditionNode:
        operands = [self._parse_and()]
        while self._peek() == "or":
            self._advance()
            operands.append(self._parse_and())
        return operands[0] if len(operands) == 1 else Or(tuple(operands))

    def _parse_and(self) -> ConditionNode:
        operands = [self._parse_not()]
        while self._peek() == "and":
            self._advance()
            operands.append(self._parse_not())
        return operands[0] if len(operands) == 1 else And(tuple(operands))

    def _parse_not(self) -> ConditionNode:
        if self._peek() == "not":
            self._advance()
            return Not(self._parse_not())
        return self._parse_atom()

    def _parse_atom(self) -> ConditionNode:
        if self._peek() == "(":
            self._advance()
            node = self._parse_or()
            if self._advance() != ")":
                raise ConditionSyntaxError("Expected closing ')'")
            return node
        return self._parse_comparison_or_is()

    def _parse_comparison_or_is(self) -> ConditionNode:
        key = self._advance()
        if not isinstance(key, str) or key in ("(", ")", "and", "or", "not", "is"):
            raise ConditionSyntaxError(f"Expected a knowledge key, got {key!r}")

        operator = self._advance()
        if operator in _COMPARISON_OPERATORS:
            value = self._advance()
            return Comparison(key, operator, value)

        if operator == "is":
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
