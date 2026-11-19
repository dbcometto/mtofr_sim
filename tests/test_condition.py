"""Tests for the condition tokenizer/parser/evaluator: mission-graph edge conditions
are a pre-tokenized boolean expression over Knowledge keys, parsed into a small typed
tree and evaluated without eval() or string parsing of literals."""
import unittest

from mtofr.mission.condition import parse_condition, ConditionSyntaxError, Comparison, IsNone, And, Or, Not
from mtofr.database import KnowledgeDatabase


class TestParseCondition(unittest.TestCase):
    def test_empty_token_list_raises(self):
        """An empty token list is a syntax error."""
        with self.assertRaises(ConditionSyntaxError):
            parse_condition([])

    def test_single_comparison_parses_to_a_comparison_node(self):
        """A key, operator, and literal parse to a single Comparison."""
        node = parse_condition(["ugv1/battery", ">", 0.9])
        self.assertEqual(node, Comparison("ugv1/battery", ">", 0.9))

    def test_is_none_parses_to_an_is_none_node(self):
        """`key is None` parses to a non-negated IsNone."""
        node = parse_condition(["ugv1/target", "is", None])
        self.assertEqual(node, IsNone("ugv1/target", negated=False))

    def test_is_not_none_parses_to_a_negated_is_none_node(self):
        """`key is not None` parses to a negated IsNone."""
        node = parse_condition(["ugv1/target", "is", "not", None])
        self.assertEqual(node, IsNone("ugv1/target", negated=True))

    def test_and_composes_two_comparisons(self):
        """`and` between two comparisons parses to an And of both."""
        node = parse_condition(["ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9])
        self.assertEqual(node, And((Comparison("ugv1/arrived", "==", True), Comparison("ugv1/battery", ">", 0.9))))

    def test_or_composes_two_comparisons(self):
        """`or` between two terms parses to an Or of both."""
        node = parse_condition(["ugv1/arrived", "==", True, "or", "ugv1/target", "is", "not", None])
        self.assertEqual(node, Or((Comparison("ugv1/arrived", "==", True), IsNone("ugv1/target", negated=True))))

    def test_not_negates_the_following_expression(self):
        """A leading `not` wraps the following comparison in Not."""
        node = parse_condition(["not", "ugv1/arrived", "==", True])
        self.assertEqual(node, Not(Comparison("ugv1/arrived", "==", True)))

    def test_parens_group_an_or_inside_an_and(self):
        """A parenthesized `and` group becomes one operand of the surrounding `or`."""
        tokens = ["(", "ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9, ")",
                  "or", "ugv1/target_found", "is", "not", None]
        node = parse_condition(tokens)
        expected = Or((
            And((Comparison("ugv1/arrived", "==", True), Comparison("ugv1/battery", ">", 0.9))),
            IsNone("ugv1/target_found", negated=True),
        ))
        self.assertEqual(node, expected)

    def test_and_binds_tighter_than_or_without_parens(self):
        """Without parens, `and` takes precedence over `or`."""
        # a or b and c == a or (b and c)
        node = parse_condition(["a", "==", 1, "or", "b", "==", 2, "and", "c", "==", 3])
        expected = Or((Comparison("a", "==", 1), And((Comparison("b", "==", 2), Comparison("c", "==", 3)))))
        self.assertEqual(node, expected)

    def test_trailing_garbage_raises(self):
        """Extra tokens after a complete expression are a syntax error."""
        with self.assertRaises(ConditionSyntaxError):
            parse_condition(["ugv1/arrived", "==", True, "extra"])

    def test_unclosed_paren_raises(self):
        """An opening paren with no matching close is a syntax error."""
        with self.assertRaises(ConditionSyntaxError):
            parse_condition(["(", "ugv1/arrived", "==", True])

    def test_missing_operator_raises(self):
        """A bare key with no operator is a syntax error."""
        with self.assertRaises(ConditionSyntaxError):
            parse_condition(["ugv1/arrived"])

    def test_is_without_a_trailing_none_raises(self):
        """`key is not` with nothing after it is a syntax error."""
        # regression: end-of-tokens must not be confused with a literal None token
        with self.assertRaises(ConditionSyntaxError):
            parse_condition(["ugv1/target", "is", "not"])

    def test_is_followed_by_a_non_none_value_raises(self):
        """`is` may only be followed by None (optionally after `not`)."""
        with self.assertRaises(ConditionSyntaxError):
            parse_condition(["ugv1/target", "is", "something_else"])


class TestEvaluate(unittest.TestCase):
    def setUp(self):
        """Declare an arrived bool, a battery float, and a None-valued target in Knowledge."""
        self.knowledge = KnowledgeDatabase()
        self.knowledge.declare("ugv1/arrived", bool, True)
        self.knowledge.declare("ugv1/battery", float, 0.95)
        self.knowledge.declare("ugv1/target", object, None)

    def test_eq(self):
        """`==` is true when the Knowledge value equals the literal."""
        self.assertTrue(parse_condition(["ugv1/arrived", "==", True]).evaluate(self.knowledge))

    def test_neq(self):
        """`!=` is true when the Knowledge value differs from the literal."""
        self.assertTrue(parse_condition(["ugv1/arrived", "!=", False]).evaluate(self.knowledge))

    def test_lt_gt_lte_gte(self):
        """The ordering operators compare the Knowledge value against the literal, inclusive for `<=`/`>=`."""
        self.assertTrue(parse_condition(["ugv1/battery", ">", 0.9]).evaluate(self.knowledge))
        self.assertFalse(parse_condition(["ugv1/battery", "<", 0.9]).evaluate(self.knowledge))
        self.assertTrue(parse_condition(["ugv1/battery", ">=", 0.95]).evaluate(self.knowledge))
        self.assertTrue(parse_condition(["ugv1/battery", "<=", 0.95]).evaluate(self.knowledge))

    def test_is_none_true_when_value_is_none(self):
        """`is None` is true for a None-valued key."""
        self.assertTrue(parse_condition(["ugv1/target", "is", None]).evaluate(self.knowledge))

    def test_is_not_none_false_when_value_is_none(self):
        """`is not None` is false for a None-valued key."""
        self.assertFalse(parse_condition(["ugv1/target", "is", "not", None]).evaluate(self.knowledge))

    def test_and_short_circuits_to_false(self):
        """`and` is false when either operand is false."""
        node = parse_condition(["ugv1/arrived", "==", True, "and", "ugv1/battery", "<", 0.5])
        self.assertFalse(node.evaluate(self.knowledge))

    def test_or_is_true_if_either_operand_is_true(self):
        """`or` is true when only one operand is true."""
        node = parse_condition(["ugv1/arrived", "==", False, "or", "ugv1/battery", ">", 0.5])
        self.assertTrue(node.evaluate(self.knowledge))

    def test_not_inverts_the_result(self):
        """`not` turns a false comparison true."""
        node = parse_condition(["not", "ugv1/arrived", "==", False])
        self.assertTrue(node.evaluate(self.knowledge))

    def test_parenthesized_composition_evaluates_correctly(self):
        """A parenthesized `and` inside an `or` evaluates true when the group is true."""
        tokens = ["(", "ugv1/arrived", "==", True, "and", "ugv1/battery", ">", 0.9, ")",
                  "or", "ugv1/target", "is", "not", None]
        self.assertTrue(parse_condition(tokens).evaluate(self.knowledge))


if __name__ == "__main__":
    unittest.main()
