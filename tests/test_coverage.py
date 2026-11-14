import unittest

from pipeline_impact.analyzer import snapshot
from tests.helpers import CONTEXT, CONTEXT_FIXTURES, artifact, simple, workflow


def coverage_for(result, analysis):
    for record in result["coverage"]:
        if record["analysis"] == analysis:
            return record

    raise AssertionError(f"Cobertura ausente para {analysis}.")


def details_for(coverage, result):
    details = []
    for detail in coverage["details"]:
        if detail["result"] == result:
            details.append(detail)
    return details


def findings_for(result, rule):
    findings = []
    for finding in result["findings"]:
        if finding["rule"] == rule:
            findings.append(finding)
    return findings


class CoverageTests(unittest.TestCase):
    def test_artifact_order_is_not_applicable_without_recognized_consumers(self):
        result = snapshot(workflow({"lint": simple()}))
        coverage = coverage_for(result, "R02_ARTIFACT_ORDER")

        self.assertEqual("not_applicable", coverage["status"])
        self.assertTrue(coverage["scope"])
        self.assertTrue(coverage["reasons"])

    def test_artifact_recognition_reports_supported_steps_and_exclusions(self):
        model = workflow({
            "build": simple(steps=[
                {"uses": "actions/checkout@v4"},
                artifact(),
                artifact(name="${{ matrix.name }}"),
            ]),
            "verify": simple("build", steps=[artifact(False)]),
        })

        result = snapshot(model)
        coverage = coverage_for(result, "artifact_recognition")
        uploads = details_for(coverage, "recognized_upload")
        downloads = details_for(coverage, "recognized_download")
        unsupported = details_for(coverage, "unsupported_selector")
        boundaries = details_for(coverage, "unrecognized_action")

        self.assertEqual(1, len(uploads))
        self.assertEqual({"job": "build", "step": 2}, uploads[0]["location"])
        self.assertEqual(1, len(downloads))
        self.assertEqual({"job": "verify", "step": 1}, downloads[0]["location"])
        self.assertEqual(1, len(unsupported))
        self.assertEqual({"job": "build", "step": 3}, unsupported[0]["location"])
        self.assertEqual(1, len(boundaries))
        self.assertEqual({"job": "build", "step": 1}, boundaries[0]["location"])

    def test_event_filters_select_compatible_context(self):
        model = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple("build", steps=[artifact(False)]),
        })
        model.raw["on"] = {"push": {"branches": ["main"]}}

        result = snapshot(model, CONTEXT_FIXTURES)
        coverage = coverage_for(result, "R03_ARTIFACT_CONDITION")

        self.assertEqual("executed", coverage["status"])
        self.assertTrue(coverage["reasons"])
        self.assertEqual([CONTEXT], result["contexts_checked"])
        conditions = coverage_for(result, "condition_evaluation")
        self.assertEqual(2, len(details_for(conditions, "context_excluded")))
        self.assertEqual([], findings_for(result, "R03_ARTIFACT_CONDITION"))

    def test_unknown_producer_condition_records_location_and_context(self):
        upload = artifact()
        upload["if"] = "inputs.make_artifact"
        model = workflow({
            "build": simple(steps=[upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })

        result = snapshot(model, CONTEXT_FIXTURES)
        coverage = coverage_for(result, "R03_ARTIFACT_CONDITION")
        conditions = coverage_for(result, "condition_evaluation")
        examined = details_for(conditions, "context_examined")
        indeterminate = details_for(conditions, "runtime_value")
        examined_contexts = []
        for detail in examined:
            examined_contexts.append(detail["context"])

        self.assertEqual("partial", coverage["status"])
        self.assertTrue(coverage["reasons"])
        self.assertEqual(result["contexts_checked"], examined_contexts)
        self.assertTrue(indeterminate)

        for detail in indeterminate:
            self.assertEqual({"job": "build", "step": 1, "field": "if"}, detail["location"])
            self.assertIn(detail["context"], examined_contexts)

        self.assertEqual([], findings_for(result, "R03_ARTIFACT_CONDITION"))

    def test_unrelated_runtime_value_does_not_change_artifact_rule_coverage(self):
        dependent_step = {
            "if": "steps.prepare.outputs.ready == 'true'",
            "run": "echo test",
        }
        model = workflow({
            "build": simple(steps=[artifact()]),
            "verify": simple("build", steps=[artifact(False), dependent_step]),
        })

        result = snapshot(model, [CONTEXT])
        artifact_coverage = coverage_for(result, "R03_ARTIFACT_CONDITION")
        conditions = coverage_for(result, "condition_evaluation")

        self.assertEqual("executed", artifact_coverage["status"])
        self.assertEqual("partial", conditions["status"])
        self.assertEqual(
            {"job": "verify", "step": 2, "field": "if"},
            details_for(conditions, "runtime_value")[0]["location"],
        )

    def test_upload_without_consumer_does_not_apply_conditional_artifact_rule(self):
        upload = artifact(name="${{ vars.artifact }}")
        model = workflow({"build": simple(steps=[upload])})

        result = snapshot(model, [CONTEXT])
        coverage = coverage_for(result, "R03_ARTIFACT_CONDITION")

        self.assertEqual("not_applicable", coverage["status"])

    def test_existing_guards_explain_parallel_review_suspension(self):
        scenarios = [
            ("matrix", simple(strategy={"matrix": {"version": [1, 2]}}), "unresolved_job"),
            ("concurrency", simple(concurrency="deploy"), None),
            ("selector", simple(steps=[artifact(name="${{ matrix.name }}")]), "unsupported_selector"),
        ]

        for scenario, build, artifact_result in scenarios:
            with self.subTest(scenario=scenario):
                model = workflow({"build": build, "verify": simple("build")})
                result = snapshot(model)
                coverage = coverage_for(result, "R05_PARALLEL_REVIEW")

                self.assertEqual("suspended", coverage["status"])
                self.assertTrue(coverage["reasons"])
                self.assertEqual([], details_for(coverage, "review_suggested"))
                self.assertEqual([], findings_for(result, "R05_PARALLEL_REVIEW"))

                if artifact_result is not None:
                    recognition = coverage_for(result, "artifact_recognition")
                    self.assertTrue(details_for(recognition, artifact_result))

    def test_unknown_actions_are_boundaries_and_parallel_review_continues(self):
        model = workflow({
            "build": simple(steps=[{"uses": "actions/checkout@v4"}]),
            "verify": simple("build", steps=[{"uses": "actions/setup-python@v5"}]),
        })

        result = snapshot(model)
        recognition = coverage_for(result, "artifact_recognition")
        boundaries = details_for(recognition, "unrecognized_action")
        coverage = coverage_for(result, "R05_PARALLEL_REVIEW")
        recommendations = details_for(coverage, "review_suggested")
        findings = findings_for(result, "R05_PARALLEL_REVIEW")

        self.assertEqual(2, len(boundaries))
        self.assertEqual("executed", coverage["status"])
        self.assertEqual(1, len(recommendations))
        self.assertEqual(["build", "verify"], recommendations[0]["edge"])
        self.assertEqual(1, len(findings))
        self.assertEqual({"job": "verify", "field": "needs"}, findings[0]["location"])

    def test_parallel_review_reports_alternative_order_and_protected_data(self):
        redundant = workflow({
            "build": simple(),
            "bridge": simple("build"),
            "verify": simple(["build", "bridge"]),
        })
        redundant_result = snapshot(redundant)
        redundant_coverage = coverage_for(redundant_result, "R05_PARALLEL_REVIEW")
        preserved_order = details_for(redundant_coverage, "order_preserved")

        self.assertEqual(1, len(preserved_order))
        self.assertEqual(["build", "verify"], preserved_order[0]["edge"])

        protected = workflow({
            "build": simple(steps=[artifact()]),
            "bridge": simple("build"),
            "verify": simple("bridge", steps=[artifact(False)]),
        })
        protected_result = snapshot(protected)
        protected_coverage = coverage_for(protected_result, "R05_PARALLEL_REVIEW")
        protected_edges = details_for(protected_coverage, "data_relation_protected")
        edges = []
        for detail in protected_edges:
            edges.append(detail["edge"])
            self.assertTrue(detail["protected_relation"])

        self.assertIn(["build", "bridge"], edges)
        self.assertIn(["bridge", "verify"], edges)

    def test_unordered_artifact_location_identifies_consumer_among_producers(self):
        model = workflow({
            "z_producer": simple(steps=[artifact()]),
            "y_producer": simple(steps=[artifact()]),
            "a_consumer": simple(steps=[{"run": "echo prepare"}, artifact(False)]),
        })

        findings = findings_for(snapshot(model), "R02_ARTIFACT_ORDER")

        self.assertEqual(1, len(findings))
        self.assertEqual({"job": "a_consumer", "step": 2}, findings[0]["location"])
        self.assertEqual(["y_producer", "z_producer"], findings[0]["evidence"]["producer_jobs"])

    def test_conditional_artifact_location_identifies_consumer_among_producers(self):
        upload = artifact()
        upload["if"] = False
        second_upload = artifact()
        second_upload["if"] = False
        model = workflow({
            "z_producer": simple(steps=[upload]),
            "y_producer": simple(steps=[second_upload]),
            "a_consumer": simple(["y_producer", "z_producer"], steps=[{"run": "echo prepare"}, artifact(False)]),
        })

        findings = findings_for(snapshot(model, CONTEXT_FIXTURES), "R03_ARTIFACT_CONDITION")

        self.assertTrue(findings)
        for finding in findings:
            self.assertEqual({"job": "a_consumer", "step": 2}, finding["location"])
            self.assertEqual(2, len(finding["evidence"]["producer_steps"]))

    def test_same_job_artifact_locations_use_the_consumer_step(self):
        initial_step = {"run": "echo prepare"}
        skipped_upload = artifact()
        skipped_upload["if"] = False
        scenarios = [
            ("R02_ARTIFACT_ORDER", [initial_step, artifact(False), artifact()], 2),
            ("R03_ARTIFACT_CONDITION", [initial_step, skipped_upload, artifact(False)], 3),
        ]

        for rule, steps, consumer_step in scenarios:
            with self.subTest(rule=rule):
                model = workflow({"build": simple(steps=steps)})
                findings = findings_for(snapshot(model, CONTEXT_FIXTURES), rule)

                self.assertTrue(findings)
                for finding in findings:
                    self.assertEqual({"job": "build", "step": consumer_step}, finding["location"])


if __name__ == "__main__":
    unittest.main()
