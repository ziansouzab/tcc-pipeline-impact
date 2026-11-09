import json
import unittest

from pipeline_impact.analyzer import compare, snapshot
from tests.helpers import artifact, collect_kinds, collect_rules, simple, workflow


class AnalysisTests(unittest.TestCase):
    def test_unmodeled_fields_are_visible(self):
        old = workflow({"a": simple()})
        new_job = simple()
        new_job["runs-on"] = "windows-latest"
        new = workflow({"a": new_job})

        report = compare(old, new)
        rules = collect_rules(report["changes"])
        self.assertIn("UNMODELED_JOB_CHANGE", rules)


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
