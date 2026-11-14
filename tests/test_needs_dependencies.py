import json
import unittest

from pipeline_impact.analyzer import audit, compare, snapshot
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown
from tests.helpers import ROOT, collect_rules, simple, workflow
from tests.test_coverage import coverage_for, details_for, findings_for


DIRECT_NEEDS_RULE = "R06_NEEDS_DIRECT_DEPENDENCY"
PARALLEL_REVIEW_RULE = "R05_PARALLEL_REVIEW"


class NeedsDependencyTests(unittest.TestCase):
    def test_compare_reports_lost_output_access_when_precedence_is_preserved(self):
        consumer_step = {"run": "echo ${{ needs.build.outputs.version }}"}
        before_workflow = workflow({
            "build": simple(outputs={"version": "1"}),
            "bridge": simple("build"),
            "verify": simple(["build", "bridge"], steps=[consumer_step]),
        })
        after_workflow = workflow({
            "build": simple(outputs={"version": "1"}),
            "bridge": simple("build"),
            "verify": simple("bridge", steps=[consumer_step]),
        })

        report = compare(before_workflow, after_workflow)

        self.assertEqual({"bridge", "build"}, after_workflow.ancestors("verify"))
        self.assertEqual({"R01_DEPENDENCY_CHANGE"}, collect_rules(report["changes"]))
        self.assertEqual([], findings_for(report["before"], DIRECT_NEEDS_RULE))
        findings = findings_for(report["after"], DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual("warning", findings[0]["kind"])
        self.assertEqual({"job": "verify", "step": 1, "field": "run"}, findings[0]["location"])
        self.assertEqual("build", findings[0]["evidence"]["producer_job"])
        self.assertEqual("needs.build.outputs.version", findings[0]["evidence"]["reference"])
        self.assertTrue(findings[0]["evidence"]["reason"])
        self.assertEqual(1, report["summary"]["warning"])

    def test_direct_output_dependency_is_protected_even_with_an_alternative_path(self):
        consumer_step = {"run": "echo ${{ needs.build.outputs.version }}"}
        current_workflow = workflow({
            "build": simple(outputs={"version": "1"}),
            "bridge": simple("build"),
            "verify": simple(["build", "bridge"], steps=[consumer_step]),
        })

        result = snapshot(current_workflow)

        self.assertEqual([], findings_for(result, DIRECT_NEEDS_RULE))
        self.assertIn(["build", "verify"], result["data_relations"])
        review = coverage_for(result, PARALLEL_REVIEW_RULE)
        protections = details_for(review, "direct_needs_protected")
        self.assertEqual(1, len(protections))
        self.assertEqual(["build", "verify"], protections[0]["edge"])
        self.assertEqual(["build", "verify"], protections[0]["protected_relation"])

    def test_result_in_job_if_protects_the_direct_dependency(self):
        consumer = simple("build")
        consumer["if"] = "always() && needs.build.result == 'success'"
        current_workflow = workflow({"build": simple(), "verify": consumer})

        result = snapshot(current_workflow)

        self.assertEqual([], findings_for(result, DIRECT_NEEDS_RULE))
        self.assertEqual([], findings_for(result, PARALLEL_REVIEW_RULE))
        self.assertIn(["build", "verify"], result["data_relations"])
        review = coverage_for(result, PARALLEL_REVIEW_RULE)
        protections = details_for(review, "direct_needs_protected")
        self.assertEqual(1, len(protections))
        self.assertEqual(["build", "verify"], protections[0]["edge"])
        self.assertEqual(["build", "verify"], protections[0]["protected_relation"])

    def test_mixed_access_and_case_resolve_to_the_declared_dependency(self):
        consumer_step = {
            "run": "echo ${{ NeEdS['BUILD'].outputs['version'] }}",
        }
        current_workflow = workflow({
            "build": simple(outputs={"version": "1"}),
            "verify": simple("build", steps=[consumer_step]),
        })

        result = snapshot(current_workflow)

        self.assertEqual([], findings_for(result, DIRECT_NEEDS_RULE))
        self.assertEqual([], findings_for(result, PARALLEL_REVIEW_RULE))
        self.assertEqual([["build", "verify"]], result["data_relations"])
        coverage = coverage_for(result, DIRECT_NEEDS_RULE)
        declared = details_for(coverage, "direct_dependency_declared")
        self.assertEqual(1, len(declared))
        self.assertEqual({"job": "verify", "step": 1, "field": "run"}, declared[0]["location"])

    def test_fully_indexed_access_reports_the_missing_direct_dependency(self):
        consumer_step = {
            "run": "echo ${{ needs['build']['outputs']['version'] }}",
        }
        current_workflow = workflow({
            "build": simple(outputs={"version": "1"}),
            "verify": simple(steps=[consumer_step]),
        })

        result = snapshot(current_workflow)

        findings = findings_for(result, DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual("needs.build.outputs.version", findings[0]["evidence"]["reference"])
        coverage = coverage_for(result, DIRECT_NEEDS_RULE)
        missing = details_for(coverage, "missing_direct_dependency")
        self.assertEqual(1, len(missing))
        self.assertEqual({"job": "verify", "step": 1, "field": "run"}, missing[0]["location"])

    def test_result_in_step_if_reports_the_job_field_and_step_position(self):
        step = {"run": "echo verify", "if": "needs.build.result == 'success'"}
        current_workflow = workflow({
            "build": simple(),
            "verify": simple(steps=[{"run": "echo first"}, step]),
        })

        report = audit(current_workflow)

        findings = findings_for(report["analysis"], DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertEqual({"job": "verify", "step": 2, "field": "if"}, findings[0]["location"])
        self.assertEqual("needs.build.result", findings[0]["evidence"]["reference"])
        self.assertEqual("build", findings[0]["evidence"]["producer_job"])
        self.assertEqual(1, report["summary"]["warning"])

    def test_unknown_producer_and_self_reference_are_reported(self):
        consumer = simple(steps=[
            {"run": "echo ${{ needs.missing.outputs.version }}"},
            {"run": "echo ${{ needs.verify.result }}"},
        ])

        result = snapshot(workflow({"verify": consumer}))

        findings = findings_for(result, DIRECT_NEEDS_RULE)
        producer_jobs_by_step = {}
        for finding in findings:
            position = finding["location"]["step"]
            producer_jobs_by_step[position] = finding["evidence"]["producer_job"]
            self.assertEqual("warning", finding["kind"])
            self.assertEqual("verify", finding["location"]["job"])
        self.assertEqual(2, len(findings))
        self.assertEqual({1: "missing", 2: "verify"}, producer_jobs_by_step)

    def test_plain_text_and_quoted_expression_strings_do_not_create_relations(self):
        consumer = simple(steps=[
            {"run": "echo needs.missing.outputs.version"},
            {"run": 'echo "${{ format(\'needs.missing.result\') }}"'},
            {"run": 'echo "${{ format(\'don\'\'t read needs.missing.result\') }}"'},
            {"run": "echo ${{ env.needs.missing.result }}"},
            {"run": "echo ${{ needs.missing.result-extra }}"},
            {"run": "echo verify", "if": "'needs.missing.result' == 'needs.other.result'"},
        ])

        result = snapshot(workflow({"verify": consumer}))

        self.assertEqual([], findings_for(result, DIRECT_NEEDS_RULE))
        self.assertEqual([], result["data_relations"])

    def test_scans_multiple_expressions_without_treating_braces_inside_literals_as_a_boundary(self):
        consumer_step = {
            "run": "echo ${{ format('}}', needs.build.result) }} ${{ needs.pack.outputs.bundle }}",
        }
        current_workflow = workflow({
            "build": simple(),
            "pack": simple(outputs={"bundle": "1"}),
            "verify": simple(steps=[consumer_step]),
        })

        result = snapshot(current_workflow)

        references = []
        for finding in findings_for(result, DIRECT_NEEDS_RULE):
            references.append(finding["evidence"]["reference"])
        self.assertEqual(["needs.build.result", "needs.pack.outputs.bundle"], references)

    def test_suggestion_does_not_add_a_dependency_that_would_create_a_cycle(self):
        current_workflow = workflow({
            "build": simple(steps=[{"run": "echo ${{ needs.verify.result }}"}]),
            "verify": simple("build"),
        })

        result = snapshot(current_workflow)

        findings = findings_for(result, DIRECT_NEEDS_RULE)
        self.assertEqual(1, len(findings))
        self.assertIn("criaria uma dependência circular", findings[0]["suggestion"])

    def test_report_exposes_the_reference_without_copying_run_or_env_values(self):
        consumer = simple(steps=[
            {"run": "echo PRIVATE_COMMAND ${{ needs.build.outputs.version }}"},
            {
                "run": "echo verify",
                "env": {"BUILD_VALUE": "PRIVATE_ENV_VALUE ${{ needs.build.outputs.version }}"},
            },
        ])
        current_workflow = workflow({"build": simple(), "verify": consumer})

        report = audit(current_workflow)
        report_json = json.dumps(report)
        report_markdown = markdown(report)

        findings = findings_for(report["analysis"], DIRECT_NEEDS_RULE)
        locations = {}
        for finding in findings:
            location = finding["location"]
            locations[location["step"]] = location["field"]
        self.assertEqual({1: "run", 2: "env"}, locations)
        self.assertIn(DIRECT_NEEDS_RULE, report_markdown)
        self.assertIn("needs.build.outputs.version", report_markdown)
        self.assertIn("needs.build.outputs.version", report_json)
        for private_value in ("PRIVATE_COMMAND", "PRIVATE_ENV_VALUE"):
            self.assertNotIn(private_value, report_json)
            self.assertNotIn(private_value, report_markdown)

    def test_transitive_artifact_transfer_continues_to_be_valid(self):
        artifact_case = ROOT / "cases/04-precedencia-transitiva/after.yml"

        report = audit(load(artifact_case))

        rules = collect_rules(report["analysis"]["findings"])
        self.assertNotIn(DIRECT_NEEDS_RULE, rules)
        self.assertNotIn("R02_ARTIFACT_ORDER", rules)
        self.assertIn(["build", "verify"], report["analysis"]["data_relations"])
        self.assertEqual(0, report["summary"]["warning"])


if __name__ == "__main__":
    unittest.main()
