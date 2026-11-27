import json
import unittest

from pipeline_impact.analyzer import compare
from pipeline_impact.model import load
from tests.helpers import CONTEXT_FIXTURES, ROOT, collect_rules


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
                result = compare(before_workflow, after_workflow, CONTEXT_FIXTURES)
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
                elif expected_changes == {"UNMODELED_WORKFLOW_CHANGE"}:
                    self.assertEqual(1, len(result["changes"]))
                    self.assertEqual("name", result["changes"][0]["field"])

                if expected["unordered_pairs"] is not None:
                    actual_pairs = result["after"]["structurally_unordered_pairs"]
                    self.assertEqual(expected["unordered_pairs"], actual_pairs)

                self.assertFalse(case["github_execution_verified"])


if __name__ == "__main__":
    unittest.main()
