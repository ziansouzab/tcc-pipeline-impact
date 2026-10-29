from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import yaml

from pipeline_impact.analyzer import compare, snapshot
from pipeline_impact.cli import main
from pipeline_impact.conditions import UnsupportedCondition, evaluate
from pipeline_impact.model import InputError, load, parse
from pipeline_impact.reporting import markdown


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = {"github.event_name": "push", "github.ref": "refs/heads/main"}


def workflow(jobs):
    configuration = {
        "on": ["push", "pull_request"],
        "jobs": jobs,
    }
    yaml_text = yaml.safe_dump(configuration, sort_keys=False)
    return parse(yaml_text)


def simple(needs=None, **extra):
    data = {
        "runs-on": "ubuntu-latest",
        "steps": [{"run": "echo ok"}],
    }
    for key, value in extra.items():
        data[key] = value

    if needs is not None:
        data["needs"] = needs

    return data


def artifact(upload=True, name="app", **params):
    if upload:
        action_name = "upload"
    else:
        action_name = "download"

    action_parameters = {"name": name}
    for key, value in params.items():
        action_parameters[key] = value

    return {
        "uses": f"actions/{action_name}-artifact@v4",
        "with": action_parameters,
    }


def collect_rules(records):
    rules = set()
    for record in records:
        rules.add(record["rule"])
    return rules


def collect_kinds(findings):
    kinds = set()
    for current_finding in findings:
        kinds.add(current_finding["kind"])
    return kinds


class DevelopmentCorpusTests(unittest.TestCase):
    def test_predefined_expected_properties(self):
        catalog_path = ROOT / "cases/catalog.json"
        catalog_text = catalog_path.read_text(encoding="utf-8")
        catalog = json.loads(catalog_text)

        for case in catalog:
            with self.subTest(case=case["id"]):
                folder = ROOT / "cases" / case["id"]
                before_workflow = load(folder / "before.yml")
                after_workflow = load(folder / "after.yml")
                result = compare(before_workflow, after_workflow)
                expected = case["expected"]

                changes = collect_rules(result["changes"])
                all_rules = collect_rules(result["after"]["findings"])

                expected_changes = set(expected["change_rules"])
                expected_after_rules = set(expected["after_rules"])
                forbidden_rules = set(expected["absent_warning_rules"])

                self.assertTrue(expected_changes.issubset(changes))
                self.assertTrue(expected_after_rules.issubset(all_rules))
                self.assertFalse(forbidden_rules.intersection(all_rules))
                self.assertNotIn("introduced_rules", expected)

                if not expected["change_rules"]:
                    self.assertEqual([], result["changes"])

                if expected["unordered_pairs"] is not None:
                    actual_pairs = result["after"]["structurally_unordered_pairs"]
                    self.assertEqual(expected["unordered_pairs"], actual_pairs)

                self.assertFalse(case["github_execution_verified"])


class ModelTests(unittest.TestCase):
    def test_on_is_preserved_and_false_remains_boolean(self):
        yaml_text = (
            "on: push\n"
            "jobs:\n"
            "  on:\n"
            "    runs-on: ubuntu-latest\n"
            "    if: false\n"
            "    steps: []\n"
        )
        model = parse(yaml_text)
        self.assertEqual("push", model.raw["on"])
        self.assertEqual("false", model.jobs["on"]["if"])

    def test_duplicate_keys_are_rejected(self):
        yaml_text = "on: push\njobs:\n  a: {steps: []}\n  a: {steps: []}\n"
        with self.assertRaisesRegex(InputError, "duplicada"):
            parse(yaml_text)

    def test_missing_job_is_rejected(self):
        with self.assertRaisesRegex(InputError, "inexistente"):
            workflow({"b": simple("missing")})

    def test_cycle_is_rejected(self):
        with self.assertRaisesRegex(InputError, "Ciclo"):
            workflow({"a": simple("b"), "b": simple("a")})

    def test_case_insensitive_dependencies(self):
        model = workflow({"Build": simple(), "verify": simple("build")})
        self.assertEqual({"Build"}, model.ancestors("verify"))

    def test_duplicate_case_insensitive_ids_are_rejected(self):
        with self.assertRaisesRegex(InputError, "maiúsculas"):
            workflow({"a": simple(), "A": simple()})

    def test_order_of_needs_has_no_semantic_change(self):
        old = workflow({
            "a": simple(),
            "b": simple(),
            "c": simple(["a", "b"]),
        })
        new = workflow({
            "a": simple(),
            "b": simple(),
            "c": simple(["b", "a"]),
        })
        report = compare(old, new)
        self.assertEqual([], report["changes"])


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


class AnalysisTests(unittest.TestCase):
    def test_unmodeled_fields_are_visible(self):
        old = workflow({"a": simple()})
        new_job = simple()
        new_job["runs-on"] = "windows-latest"
        new = workflow({"a": new_job})

        report = compare(old, new)
        rules = collect_rules(report["changes"])
        self.assertIn("UNMODELED_JOB_CHANGE", rules)

    def test_concurrency_disables_parallel_suggestions(self):
        model = workflow({
            "a": simple(),
            "b": simple("a", concurrency="deployment"),
        })
        result = snapshot(model)
        kinds = collect_kinds(result["findings"])
        self.assertTrue(model.limitations)
        self.assertNotIn("opportunity", kinds)

    def test_parallel_steps_not_treated_as_linear(self):
        background_upload = artifact()
        background_upload["background"] = True
        model = workflow({
            "a": simple(steps=[background_upload, artifact(False)]),
        })
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertTrue(result["limitations"])
        self.assertNotIn("R03_ARTIFACT_CONDITION", rules)

    def test_removed_dependency_affects_descendant_even_when_its_needs_stay(self):
        old = workflow({
            "a": simple(),
            "b": simple("a"),
            "c": simple("b"),
        })
        new = workflow({
            "a": simple(),
            "b": simple(),
            "c": simple("b"),
        })
        report = compare(old, new)
        target_change = None

        for change in report["changes"]:
            if change["rule"] == "R01_REACHABILITY_CHANGE":
                if change["job"] == "c":
                    target_change = change
                    break

        self.assertIsNotNone(target_change)
        self.assertEqual(["a", "b"], target_change["before"])
        self.assertEqual(["b"], target_change["after"])

    def test_corrected_workflow_has_warning_only_in_before_snapshot(self):
        broken = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple(steps=[artifact(False)]),
        })
        fixed = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple("build", steps=[artifact(False)]),
        })
        fixed_report = compare(broken, fixed)
        before_rules = collect_rules(fixed_report["before"]["findings"])
        after_rules = collect_rules(fixed_report["after"]["findings"])
        self.assertIn("R02_ARTIFACT_ORDER", before_rules)
        self.assertNotIn("R02_ARTIFACT_ORDER", after_rules)
        self.assertNotIn("resolved_findings", fixed_report)

    def test_same_workflow_keeps_warnings_in_both_snapshots(self):
        broken = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple(steps=[artifact(False)]),
        })
        report = compare(broken, broken)
        before_rules = collect_rules(report["before"]["findings"])
        after_rules = collect_rules(report["after"]["findings"])
        self.assertIn("R02_ARTIFACT_ORDER", before_rules)
        self.assertIn("R02_ARTIFACT_ORDER", after_rules)
        self.assertEqual([], report["changes"])

    def test_comparison_has_no_finding_lifecycle_categories(self):
        broken = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple(steps=[artifact(False)]),
        })
        report = compare(broken, broken)
        self.assertEqual("0.2", report["schema_version"])
        self.assertNotIn("resolved_findings", report)

        for side in ("before", "after"):
            for current_finding in report[side]["findings"]:
                self.assertNotIn("lifecycle", current_finding)

        for category in ("introduced", "existing", "resolved"):
            self.assertNotIn(category, report["summary"])

        markdown_text = markdown(report)
        self.assertIn("R02_ARTIFACT_ORDER", markdown_text)
        self.assertNotIn("Achados que deixaram de ocorrer no modelo", markdown_text)
        self.assertNotIn("· introduced", markdown_text)
        self.assertNotIn("· existing", markdown_text)
        self.assertNotIn("· resolved", markdown_text)

    def test_inserted_step_preserves_diagnostics_without_claiming_lifecycle(self):
        before_workflow = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple(steps=[artifact(False)]),
        })
        after_workflow = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple(steps=[{"run": "echo Preparando download"}, artifact(False)]),
        })
        report = compare(before_workflow, after_workflow)
        before_warnings = []
        after_warnings = []

        for current_finding in report["before"]["findings"]:
            if current_finding["rule"] == "R02_ARTIFACT_ORDER":
                before_warnings.append(current_finding)

        for current_finding in report["after"]["findings"]:
            if current_finding["rule"] == "R02_ARTIFACT_ORDER":
                after_warnings.append(current_finding)

        self.assertEqual(1, len(before_warnings))
        self.assertEqual(1, len(after_warnings))
        self.assertEqual(1, before_warnings[0]["evidence"]["consumer_step"])
        self.assertEqual(2, after_warnings[0]["evidence"]["consumer_step"])
        self.assertNotIn("resolved_findings", report)

        for side in ("before", "after"):
            for current_finding in report[side]["findings"]:
                self.assertNotIn("lifecycle", current_finding)

    def test_download_before_upload_in_same_job(self):
        model = workflow({"a": simple(steps=[artifact(False), artifact()])})
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertIn("R02_ARTIFACT_ORDER", rules)

    def test_download_after_upload_in_same_job(self):
        model = workflow({"a": simple(steps=[artifact(), artifact(False)])})
        result = snapshot(model)
        self.assertFalse(result["findings"])

    def test_indirect_data_relation_blocks_parallel_suggestion(self):
        model = workflow({
            "build": simple(steps=[artifact()]),
            "bridge": simple("build"),
            "verify": simple("bridge", steps=[artifact(False)]),
        })
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertNotIn("R05_PARALLEL_REVIEW", rules)

    def test_outputs_block_suggestion(self):
        consumer_step = {"run": "echo ${{ needs.build.outputs.version }}"}
        model = workflow({
            "build": simple(outputs={"version": "1"}),
            "verify": simple("build", steps=[consumer_step]),
        })
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertNotIn("R05_PARALLEL_REVIEW", rules)

    def test_redundant_edge_not_recommended_for_parallelism(self):
        model = workflow({
            "a": simple(),
            "b": simple("a"),
            "c": simple(["a", "b"]),
        })
        result = snapshot(model)
        suggested_edges = []

        for current_finding in result["findings"]:
            if current_finding["kind"] == "opportunity":
                suggested_edges.append(current_finding["evidence"]["edge"])

        self.assertNotIn(["a", "c"], suggested_edges)

    def test_dynamic_artifact_is_indeterminate(self):
        model = workflow({
            "a": simple(steps=[artifact(name="${{ matrix.name }}")]),
            "b": simple("a"),
        })
        result = snapshot(model)
        kinds = collect_kinds(result["findings"])
        self.assertTrue(result["limitations"])
        self.assertNotIn("opportunity", kinds)

    def test_unknown_condition_does_not_become_missing_artifact(self):
        producer = artifact()
        producer["if"] = "inputs.make_artifact"
        model = workflow({
            "a": simple(steps=[producer]),
            "b": simple("a", steps=[artifact(False)]),
        })
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertTrue(result["limitations"])
        self.assertNotIn("R03_ARTIFACT_CONDITION", rules)

    def test_multiple_producers_one_active_is_enough_in_model(self):
        skipped = artifact()
        skipped["if"] = False
        model = workflow({
            "a": simple(steps=[skipped, artifact()]),
            "b": simple("a", steps=[artifact(False)]),
        })
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertNotIn("R03_ARTIFACT_CONDITION", rules)

    def test_reusable_job_and_matrix_marked_unresolved(self):
        model = workflow({
            "a": {"uses": "./.github/workflows/build.yml"},
            "b": simple("a"),
        })
        result = snapshot(model)
        kinds = collect_kinds(result["findings"])
        self.assertTrue(result["limitations"])
        self.assertNotIn("opportunity", kinds)

    def test_filtered_events_do_not_create_context_warning(self):
        producer = artifact()
        producer["if"] = "github.ref == 'refs/heads/main'"
        model = workflow({
            "a": simple(steps=[producer]),
            "b": simple("a", steps=[artifact(False)]),
        })
        model.raw["on"] = {"push": {"branches": ["main"]}}
        result = snapshot(model)
        rules = collect_rules(result["findings"])
        self.assertEqual([], result["contexts_checked"])
        self.assertNotIn("R03_ARTIFACT_CONDITION", rules)

    def test_future_history_is_not_silently_used(self):
        before_workflow = workflow({"a": simple()})
        after_workflow = workflow({"a": simple()})
        result = compare(before_workflow, after_workflow)
        has_history_limitation = False

        for assumption in result["assumptions"]:
            if "Sem histórico" in assumption:
                has_history_limitation = True
                break

        self.assertTrue(has_history_limitation)
        report_text = json.dumps(result)
        self.assertNotIn("estimated_savings", report_text)


class CliTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)

    def test_reports_and_exit_codes(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", str(folder / "before.yml"),
                    "--after", str(folder / "after.yml"),
                    "--output", output,
                ]
                self.assertEqual(0, main(args))

                failure_args = args.copy()
                failure_args.append("--fail-on-warning")
                self.assertEqual(1, main(failure_args))

                json_path = Path(output) / "report.json"
                json_text = json_path.read_text(encoding="utf-8")
                report = json.loads(json_text)

                markdown_path = Path(output) / "report.md"
                markdown_text = markdown_path.read_text(encoding="utf-8")
                self.assertIn("```mermaid", markdown_text)
                self.assertIn("R02_ARTIFACT_ORDER", markdown_text)
                self.assertEqual("0.2", report["schema_version"])

    def test_fail_on_warning_checks_after_when_workflow_is_unchanged(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"
        warning_workflow = str(folder / "after.yml")

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", warning_workflow,
                    "--after", warning_workflow,
                    "--output", output,
                ]
                self.assertEqual(0, main(args))

                failure_args = args.copy()
                failure_args.append("--fail-on-warning")
                self.assertEqual(1, main(failure_args))

    def test_fail_on_warning_ignores_warnings_only_in_before(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", str(folder / "after.yml"),
                    "--after", str(folder / "before.yml"),
                    "--output", output,
                    "--fail-on-warning",
                ]
                self.assertEqual(0, main(args))

                report_path = Path(output) / "report.json"
                report_text = report_path.read_text(encoding="utf-8")
                report = json.loads(report_text)
                before_kinds = collect_kinds(report["before"]["findings"])
                after_kinds = collect_kinds(report["after"]["findings"])
                self.assertIn("warning", before_kinds)
                self.assertNotIn("warning", after_kinds)

    def test_fail_on_warning_does_not_fail_for_opportunities(self):
        folder = ROOT / "cases/09-revisar-paralelismo"

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", str(folder / "before.yml"),
                    "--after", str(folder / "after.yml"),
                    "--output", output,
                    "--fail-on-warning",
                ]
                self.assertEqual(0, main(args))

                report_path = Path(output) / "report.json"
                report_text = report_path.read_text(encoding="utf-8")
                report = json.loads(report_text)
                after_kinds = collect_kinds(report["after"]["findings"])
                self.assertIn("opportunity", after_kinds)
                self.assertNotIn("warning", after_kinds)

    def test_old_warning_flag_is_rejected(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"
        args = [
            "--before", str(folder / "before.yml"),
            "--after", str(folder / "after.yml"),
            "--fail-on-new-warning",
        ]

        with redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as raised:
                main(args)

        self.assertEqual(2, raised.exception.code)
        self.assertIn("--fail-on-new-warning", error.getvalue())

    def test_bad_input_returns_two_without_traceback(self):
        with redirect_stderr(io.StringIO()) as error:
            args = ["--before", "missing.yml", "--after", "missing.yml"]
            self.assertEqual(2, main(args))
            args.append("--fail-on-warning")
            self.assertEqual(2, main(args))
            self.assertNotIn("Traceback", error.getvalue())

    def test_report_does_not_dump_run_secrets(self):
        old = workflow({"a": simple()})
        new = workflow({
            "a": simple(steps=[{"run": "echo PRIVATE_EXAMPLE"}]),
        })
        report = compare(old, new)
        report_text = json.dumps(report)
        markdown_text = markdown(report)
        self.assertNotIn("PRIVATE_EXAMPLE", report_text)
        self.assertIn("STEP_CHANGE", markdown_text)


if __name__ == "__main__":
    unittest.main()
