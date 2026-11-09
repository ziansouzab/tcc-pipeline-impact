import unittest

from pipeline_impact.conditions import UnsupportedCondition, evaluate
from tests.helpers import CONTEXT


class ConditionTests(unittest.TestCase):
    def test_generic_string_identifier_is_read_from_context(self):
        context = {"vars.environment": "staging"}
        result = evaluate("vars.environment == 'staging'", context)
        self.assertTrue(result)

    def test_generic_boolean_identifier_preserves_false(self):
        context = {"inputs.publish": False}
        result = evaluate("inputs.publish", context)
        self.assertFalse(result)

        context["inputs.publish"] = True
        result = evaluate("inputs.publish", context)
        self.assertTrue(result)

    def test_missing_identifier_is_unsupported(self):
        context = {}
        expressions = ["inputs.publish", "github.ref == 'refs/heads/main'"]

        for expression in expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(UnsupportedCondition):
                    evaluate(expression, context)

    def test_unknown_identifier_value_remains_indeterminate(self):
        context = {"inputs.publish": None}
        result = evaluate("inputs.publish", context)
        self.assertIsNone(result)

    def test_unsupported_context_value_is_rejected(self):
        unsupported_values = [1, [], {}]

        for value in unsupported_values:
            with self.subTest(value=value):
                context = {"inputs.value": value}
                with self.assertRaises(UnsupportedCondition):
                    evaluate("inputs.value == inputs.value", context)

    def test_context_does_not_override_literals_or_status_functions(self):
        context = {"true": False, "always": False}
        literal_result = evaluate("true", context)
        function_result = evaluate("always()", context, success=False)
        self.assertTrue(literal_result)
        self.assertTrue(function_result)

    def test_boolean_expression_and_wrapping(self):
        expression = "${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' }}"
        result = evaluate(expression, CONTEXT)
        self.assertTrue(result)

    def test_string_comparison_ignores_case(self):
        result = evaluate("github.event_name == 'PUSH'", CONTEXT)
        self.assertTrue(result)

    def test_disjunction_negation_parentheses(self):
        result = evaluate("!(github.event_name == 'pull_request') || false", CONTEXT)
        self.assertTrue(result)

    def test_implicit_success_and_status_override(self):
        result = evaluate("true", CONTEXT, success=False)
        self.assertFalse(result)

        result = evaluate("always()", CONTEXT, success=False)
        self.assertTrue(result)

        result = evaluate("success()", CONTEXT, success=None)
        self.assertIsNone(result)

    def test_unsupported_expressions_fail_closed(self):
        expressions = [
            "contains(github.ref, 'main')",
            "needs.build.result == 'success'",
            "'a'",
            "1 == 1",
            "true blah",
            "",
        ]
        for expression in expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(UnsupportedCondition):
                    evaluate(expression, CONTEXT)

    def test_no_python_code_execution(self):
        with self.assertRaises(UnsupportedCondition):
            evaluate("__import__('os').system('echo unsafe')", CONTEXT)

    def test_status_function_name_inside_literal_does_not_override_success(self):
        result = evaluate("github.ref != 'success()'", CONTEXT, success=False)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
