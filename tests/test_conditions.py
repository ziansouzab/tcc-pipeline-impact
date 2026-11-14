import unittest

from pipeline_impact.conditions import UnsupportedCondition, evaluate, states
from tests.helpers import CONTEXT, simple, workflow


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

    def test_string_functions_use_two_text_arguments_and_ignore_case(self):
        expressions = (
            "startsWith(github.ref, 'REFS/HEADS/')",
            "endsWith(github.ref, 'MAIN')",
            "CONTAINS('It''s Monday', 'MONDAY')",
            "contains(('abc'), 'B') && !endsWith(github.ref, '/feature')",
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertIs(True, evaluate(expression, CONTEXT))

        self.assertIs(False, evaluate("contains(github.ref, 'develop')", CONTEXT))
        self.assertIs(False, evaluate("startsWith(github.ref, 'refs/')", CONTEXT, success=False))

    def test_string_functions_leave_unavailable_values_undetermined(self):
        context = {"github.base_ref": None}
        self.assertIsNone(evaluate("startsWith(github.base_ref, 'release/')", context))

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
            "contains(github.ref)",
            "contains(github.ref, 'main', 'extra')",
            "contains(github.ref, true)",
            "contains(fromJSON('[]'), 'main')",
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

    def test_self_audit_distinguishes_event_identity_from_step_execution(self):
        context = {
            "github.event_name": "pull_request",
            "github.repository": "owner/example",
            "github.event.pull_request.head.repo.full_name": "Owner/Example",
        }
        job_condition = "github.event.pull_request.head.repo.full_name == github.repository"
        output_condition = "steps.prepare.outputs.has_workflows == 'true'"
        outcome_condition = (
            "${{ !cancelled() && (steps.audit.outcome == 'success' || steps.audit.outcome == 'failure') }}"
        )
        steps = [
            {"uses": "actions/checkout@v4"},
            {"id": "prepare", "run": "prepare-workflows"},
            {"run": "install-analyzer", "if": output_condition},
            {"id": "audit", "run": "analyze-workflows", "if": output_condition},
            {"uses": "actions/upload-artifact@v4", "if": outcome_condition},
        ]
        job = simple(steps=steps)
        job["if"] = job_condition
        diagnostics = []
        job_states = {}
        model = workflow({"audit": job})
        step_states, limitations = states(
            model, context, job_states=job_states, diagnostics=diagnostics
        )
        self.assertEqual({"audit": True}, job_states)
        self.assertEqual(
            {
                ("audit", 0): True,
                ("audit", 1): True,
                ("audit", 2): None,
                ("audit", 3): None,
                ("audit", 4): None,
            },
            step_states,
        )
        self.assertEqual(3, len(limitations))
        self.assertEqual(3, len(diagnostics))
        self.assertEqual("runtime_value", diagnostics[0]["result"])
        self.assertEqual({"job": "audit", "step": 3, "field": "if"}, diagnostics[0]["location"])
        self.assertEqual(["steps.prepare.outputs.has_workflows"], diagnostics[0]["references"])
        self.assertEqual(["steps.audit.outcome"], diagnostics[2]["references"])

        context["github.event.pull_request.head.repo.full_name"] = "fork/example"
        diagnostics = []
        step_states, limitations = states(
            model, context, job_states=job_states, diagnostics=diagnostics
        )
        self.assertEqual({"audit": False}, job_states)
        self.assertEqual([False, False, False, False, False], list(step_states.values()))
        self.assertEqual([], limitations)
        self.assertEqual([], diagnostics)

    def test_unknown_condition_causes_do_not_copy_expression_literals(self):
        steps = [
            {"run": "echo a", "if": "github.ref == 'private literal'"},
            {"run": "echo b", "if": "startsWith(secrets.INTERNAL_NAME, 'private literal')"},
            {"run": "echo c", "if": "format('private literal', github.ref)"},
            {"run": "echo d", "if": "github.uncollected_value == 'private literal'"},
        ]
        diagnostics = []
        model = workflow({"review": simple(steps=steps)})
        step_states, limitations = states(model, CONTEXT | {"github.ref": None}, diagnostics=diagnostics)
        self.assertEqual([None, None, None, None], list(step_states.values()))
        self.assertEqual(
            ["missing_event_data", "runtime_value", "unsupported_expression", "unsupported_context"],
            [detail["result"] for detail in diagnostics],
        )
        self.assertEqual(["github.ref"], diagnostics[0]["references"])
        self.assertEqual(["secrets"], diagnostics[1]["references"])
        self.assertNotIn("private literal", str(diagnostics))
        self.assertNotIn("private literal", str(limitations))
        self.assertNotIn("INTERNAL_NAME", str(limitations))

    def test_logical_expression_with_unknown_operand_is_conservatively_undetermined(self):
        expression = "(inputs.publish || true) == true"
        model = workflow({"review": simple(steps=[{"run": "echo a", "if": expression}])})
        diagnostics = []
        step_states, limitations = states(model, CONTEXT, diagnostics=diagnostics)
        self.assertIsNone(step_states["review", 0])
        self.assertEqual(1, len(limitations))
        self.assertEqual("runtime_value", diagnostics[0]["result"])


if __name__ == "__main__":
    unittest.main()
