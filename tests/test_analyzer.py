import json
import unittest

from pipeline_impact.analyzer import compare, snapshot
from pipeline_impact.reporting import markdown
from tests.helpers import CONTEXT, CONTEXT_FIXTURES, artifact, collect_kinds, collect_rules, simple, workflow


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
        self.assertEqual("0.4", report["schema_version"])
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
        result = snapshot(model, [CONTEXT])
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
        result = snapshot(model, [CONTEXT])
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
        result = snapshot(model, CONTEXT_FIXTURES)
        rules = collect_rules(result["findings"])
        self.assertEqual([CONTEXT], result["contexts_checked"])
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


if __name__ == "__main__":
    unittest.main()
