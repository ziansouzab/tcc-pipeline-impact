import json
import unittest

import yaml

from pipeline_impact.analyzer import compare
from pipeline_impact.model import load, parse
from tests.helpers import ROOT, simple, workflow


def configured_workflow(events, **configuration):
    data = {"on": events, "jobs": {"ci": simple()}}
    data.update(configuration)
    return parse(yaml.safe_dump(data, sort_keys=False))


def explanation_for(records, field, job=None):
    for record in records:
        if record.get("job") != job:
            continue
        for detail in record["explanations"]:
            if detail["field"] == field:
                return detail
    raise AssertionError(f"Explicação ausente para o campo {field} no job {job}.")


def pull_request(base_ref="main", head_ref="feature/ajuste"):
    return {
        "github.event_name": "pull_request",
        "github.ref": "refs/pull/10/merge",
        "github.base_ref": base_ref,
        "github.head_ref": head_ref,
    }


class ChangeExplanationsTests(unittest.TestCase):
    def test_branch_filters_change_eligibility_in_the_same_contexts(self):
        before = configured_workflow({"pull_request": {"branches": ["main"]}})
        after = configured_workflow({"pull_request": {"branches": ["release"]}})
        main = pull_request("main")
        release = pull_request("release")
        unknown = pull_request()
        unknown.pop("github.base_ref")

        report = compare(before, after, [main, release, unknown])
        detail = explanation_for(report["changes"], "on")

        self.assertEqual("explained", detail["status"])
        self.assertEqual({"pull_request": {"branches": ["main"]}}, detail["before"])
        self.assertEqual({"pull_request": {"branches": ["release"]}}, detail["after"])
        self.assertEqual(
            [
                {"context": main, "before": "eligible", "after": "event_excluded"},
                {"context": release, "before": "event_excluded", "after": "eligible"},
                {"context": unknown, "before": "indeterminate", "after": "indeterminate"},
            ],
            detail["context_comparisons"],
        )

    def test_equivalent_event_syntax_preserves_eligibility(self):
        context = pull_request()
        before = configured_workflow("pull_request")
        after = configured_workflow(["pull_request"])

        report = compare(before, after, [context])
        detail = explanation_for(report["changes"], "on")

        self.assertEqual("explained", detail["status"])
        self.assertEqual(detail["before"], detail["after"])
        self.assertEqual(
            [{"context": context, "before": "eligible", "after": "eligible"}],
            detail["context_comparisons"],
        )

    def test_needs_distinguishes_loss_from_indirect_precedence(self):
        lost = ROOT / "cases/03-artefato-sem-ordem"
        preserved = ROOT / "cases/04-precedencia-transitiva"

        lost_report = compare(load(lost / "before.yml"), load(lost / "after.yml"))
        lost_detail = explanation_for(lost_report["changes"], "needs", "verify")
        self.assertIn("deixou de ser imposta", lost_detail["message"])
        self.assertEqual("artifact_order_lost", lost_report["impact_links"][0]["type"])
        self.assertEqual(lost_report["after"]["findings"][0]["id"], lost_report["impact_links"][0]["finding_id"])

        preserved_report = compare(load(preserved / "before.yml"), load(preserved / "after.yml"))
        preserved_detail = explanation_for(preserved_report["changes"], "needs", "verify")
        self.assertIn("dependência indireta por middle", preserved_detail["message"])
        self.assertEqual([], preserved_report["impact_links"])

    def test_job_and_step_conditions_explain_distinct_states_by_scenario(self):
        before_jobs = {
            "lint": simple(),
            "build": simple(steps=[{"id": "pack", "run": "make package"}]),
        }
        expression = "startsWith(github.head_ref, 'release/')"
        after_jobs = {
            "lint": simple(**{"if": expression}),
            "build": simple(steps=[{"id": "pack", "run": "make package", "if": expression}]),
        }
        feature = pull_request()
        release = pull_request(head_ref="release/v1")
        unknown = pull_request()
        unknown.pop("github.head_ref")

        report = compare(workflow(before_jobs), workflow(after_jobs), [feature, release, unknown])
        job_detail = explanation_for(report["changes"], "if", "lint")
        step_detail = explanation_for(report["step_changes"], "if", "build")
        expected = [
            {"context": feature, "before": "active", "after": "skipped"},
            {"context": release, "before": "active", "after": "active"},
            {"context": unknown, "before": "active", "after": "indeterminate"},
        ]

        self.assertEqual("explained", job_detail["status"])
        self.assertEqual(expected, job_detail["context_comparisons"])
        self.assertEqual("explained", step_detail["status"])
        self.assertEqual(expected, step_detail["context_comparisons"])

    def test_policy_timeout_and_runner_have_effects_specific_to_the_field(self):
        before = workflow({
            "quality": simple(steps=[{"id": "lint", "run": "echo PRIVATE_OLD", "timeout-minutes": 3}]),
        })
        after = workflow({
            "quality": simple(
                **{
                    "timeout-minutes": 20,
                    "runs-on": "${{ vars.PRIVATE_RUNNER }}",
                    "continue-on-error": True,
                    "steps": [{
                        "id": "lint",
                        "run": "echo PRIVATE_NEW",
                        "env": {"VALUE": "PRIVATE_VALUE"},
                        "continue-on-error": True,
                    }],
                },
            ),
        })

        report = compare(before, after)
        runner = explanation_for(report["changes"], "runs-on", "quality")
        job_timeout = explanation_for(report["changes"], "timeout-minutes", "quality")
        step_timeout = explanation_for(report["step_changes"], "timeout-minutes", "quality")
        job_policy = explanation_for(report["changes"], "continue-on-error", "quality")
        step_policy = explanation_for(report["step_changes"], "continue-on-error", "quality")

        self.assertEqual("indeterminate", runner["status"])
        self.assertEqual((None, 20), (job_timeout["before"], job_timeout["after"]))
        self.assertEqual((3, None), (step_timeout["before"], step_timeout["after"]))
        self.assertIn("workflow", job_policy["message"])
        self.assertIn("job", step_policy["message"])
        for field in ("run", "env"):
            detail = explanation_for(report["step_changes"], field, "quality")
            self.assertEqual("detected", detail["status"])
            self.assertNotIn("before", detail)
            self.assertNotIn("after", detail)
        self.assertNotIn("PRIVATE_", json.dumps(report))

    def test_concurrency_describes_policy_even_if_the_group_is_dynamic(self):
        group = "ci-${{ github.ref }}"
        before = configured_workflow("push", concurrency={"group": group, "cancel-in-progress": False})
        after = configured_workflow("push", concurrency={"group": group, "cancel-in-progress": True})

        report = compare(before, after)
        detail = explanation_for(report["changes"], "concurrency")

        self.assertEqual("explained", detail["status"])
        self.assertEqual({"cancel-in-progress": False}, detail["before"])
        self.assertEqual({"cancel-in-progress": True}, detail["after"])
        self.assertIn("mesmo grupo", detail["message"])
        self.assertIn("grupo efetivo", detail["message"])

    def test_ambiguous_matching_keeps_positions_without_asserting_a_step_change(self):
        before = workflow({"ci": simple(steps=[
            {"id": "lint", "run": "echo first"},
            {"id": "LINT", "run": "echo second"},
        ])})
        after = workflow({"ci": simple(steps=[{"id": "lint", "run": "echo new"}])})

        report = compare(before, after)

        self.assertEqual(3, len(report["step_changes"]))
        for change in report["step_changes"]:
            self.assertEqual("unmatched", change["change"])
            self.assertEqual("indeterminate", change["explanations"][0]["status"])
            self.assertNotEqual(change["before_step"] is None, change["after_step"] is None)


if __name__ == "__main__":
    unittest.main()
