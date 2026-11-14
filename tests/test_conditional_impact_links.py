import unittest

from pipeline_impact.analyzer import compare
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown
from tests.helpers import CONTEXT, CONTEXT_FIXTURES, ROOT, artifact, simple, workflow
from tests.test_coverage import findings_for


ARTIFACT_CONDITION_RULE = "R03_ARTIFACT_CONDITION"
PULL_REQUEST = {"github.event_name": "pull_request", "github.ref": "refs/pull/1/merge"}


class ConditionalImpactLinkTests(unittest.TestCase):
    def test_links_upload_condition_only_in_contexts_where_the_upload_is_skipped(self):
        case_directory = ROOT / "cases/05-upload-condicional"
        before = load(case_directory / "before.yml")
        after = load(case_directory / "after.yml")

        report = compare(before, after, CONTEXT_FIXTURES)

        self.assertEqual([], findings_for(report["before"], ARTIFACT_CONDITION_RULE))
        findings = findings_for(report["after"], ARTIFACT_CONDITION_RULE)
        self.assertEqual(2, len(findings))
        findings_by_id = {}
        for finding in findings:
            findings_by_id[finding["id"]] = finding

        self.assertEqual(2, len(report["impact_links"]))
        linked_contexts = []
        for impact in report["impact_links"]:
            self.assertEqual("upload_condition_changed", impact["type"])
            self.assertIn(impact["finding_id"], findings_by_id)
            finding = findings_by_id[impact["finding_id"]]
            self.assertEqual(finding["location"], impact["location"])
            self.assertEqual({"job": "verify", "step": 2}, impact["location"])
            self.assertEqual(finding["context"], impact["context"])
            self.assertIsInstance(impact["evidence"], dict)
            self.assertTrue(impact["evidence"])
            evidence = impact["evidence"]
            self.assertEqual("app", evidence["artifact"])
            self.assertEqual("build", evidence["producer_job"])
            self.assertEqual(3, evidence["producer_step_before"])
            self.assertEqual(3, evidence["producer_step_after"])
            self.assertEqual("verify", evidence["consumer_job"])
            self.assertEqual(2, evidence["consumer_step_before"])
            self.assertEqual(2, evidence["consumer_step_after"])
            self.assertEqual("active", evidence["upload_state_before"])
            self.assertEqual("skipped", evidence["upload_state_after"])
            self.assertEqual("active", evidence["upload_state_with_restored_if"])

            self.assertGreaterEqual(impact["change_index"], 0)
            self.assertLess(impact["change_index"], len(report["changes"]))
            change = report["changes"][impact["change_index"]]
            self.assertEqual("STEP_CHANGE", change["rule"])
            self.assertEqual("build", change["job"])

            self.assertGreaterEqual(impact["step_change_index"], 0)
            self.assertLess(impact["step_change_index"], len(report["step_changes"]))
            step_change = report["step_changes"][impact["step_change_index"]]
            self.assertEqual("build", step_change["job"])
            self.assertEqual(3, step_change["after_step"])
            self.assertIn("if", step_change["fields"])
            linked_contexts.append(impact["context"])

        feature_push = {"github.event_name": "push", "github.ref": "refs/heads/feature"}
        self.assertCountEqual([feature_push, PULL_REQUEST], linked_contexts)
        self.assertNotIn(CONTEXT, linked_contexts)
        self.assertIn("**Mudança associada**", markdown(report))

    def test_does_not_infer_conditional_impact_without_a_context(self):
        case_directory = ROOT / "cases/05-upload-condicional"
        before = load(case_directory / "before.yml")
        after = load(case_directory / "after.yml")

        report = compare(before, after)

        self.assertEqual([], report["impact_links"])
        self.assertEqual([], findings_for(report["after"], ARTIFACT_CONDITION_RULE))

    def test_does_not_link_unresolved_previous_condition(self):
        before_upload = artifact()
        before_upload["if"] = "inputs.publish"
        after_upload = artifact()
        after_upload["if"] = False
        before = workflow({
            "build": simple(steps=[before_upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })
        after = workflow({
            "build": simple(steps=[after_upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })

        report = compare(before, after, [PULL_REQUEST])

        self.assertEqual([], findings_for(report["before"], ARTIFACT_CONDITION_RULE))
        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_CONDITION_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_when_the_previous_workflow_excludes_the_context(self):
        before_upload = artifact()
        after_upload = artifact()
        after_upload["if"] = False
        before = workflow({
            "build": simple(steps=[before_upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })
        before.raw["on"] = ["push"]
        after = workflow({
            "build": simple(steps=[after_upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })

        report = compare(before, after, [PULL_REQUEST])

        self.assertEqual([], findings_for(report["before"], ARTIFACT_CONDITION_RULE))
        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_CONDITION_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_when_upload_steps_have_ambiguous_identity(self):
        before_first_upload = artifact()
        before_first_upload["if"] = "github.event_name == 'pull_request'"
        before_second_upload = artifact()
        before_second_upload["if"] = "github.event_name == 'push'"
        after_first_upload = artifact()
        after_first_upload["if"] = False
        after_second_upload = artifact()
        after_second_upload["if"] = "github.ref == 'refs/heads/main'"
        before = workflow({
            "build": simple(steps=[before_first_upload, before_second_upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })
        after = workflow({
            "build": simple(steps=[after_first_upload, after_second_upload]),
            "verify": simple("build", steps=[artifact(False)]),
        })

        report = compare(before, after, [PULL_REQUEST])

        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_CONDITION_RULE)))
        self.assertEqual([], report["impact_links"])

    def test_does_not_link_when_restoring_upload_if_cannot_activate_its_job(self):
        before_upload = artifact()
        after_upload = artifact()
        after_upload["if"] = False
        after_producer = simple(steps=[after_upload])
        after_producer["if"] = False
        consumer = simple("build", steps=[artifact(False)])
        consumer["if"] = "always()"
        before = workflow({
            "build": simple(steps=[before_upload]),
            "verify": consumer,
        })
        after = workflow({
            "build": after_producer,
            "verify": consumer,
        })

        report = compare(before, after, [PULL_REQUEST])

        self.assertEqual([], findings_for(report["before"], ARTIFACT_CONDITION_RULE))
        self.assertEqual(1, len(findings_for(report["after"], ARTIFACT_CONDITION_RULE)))
        self.assertEqual([], report["impact_links"])


if __name__ == "__main__":
    unittest.main()
