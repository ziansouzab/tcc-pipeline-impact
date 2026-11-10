import tomllib
import unittest
from unittest.mock import patch

from pipeline_impact import __version__
from pipeline_impact.analyzer import audit, compare, snapshot
from pipeline_impact.model import load
from tests.helpers import ROOT, collect_rules


class AuditTests(unittest.TestCase):
    def test_audit_uses_one_snapshot_and_has_no_comparison_fields(self):
        path = ROOT / "cases/03-artefato-sem-ordem/after.yml"
        workflow = load(path)

        with patch("pipeline_impact.analyzer.snapshot", wraps=snapshot) as tracked_snapshot:
            report = audit(workflow)

        tracked_snapshot.assert_called_once_with(workflow)
        self.assertEqual("audit", report["mode"])
        self.assertEqual("0.3", report["schema_version"])
        self.assertEqual({"warning": 1, "opportunity": 0}, report["summary"])
        self.assertEqual(str(path), report["analysis"]["source"])

        for field in ("before", "after", "changes"):
            self.assertNotIn(field, report)

    def test_audit_matches_the_individual_analysis_in_comparison(self):
        for case_id in (
            "03-artefato-sem-ordem",
            "05-upload-condicional",
            "06-consumo-protegido",
            "09-revisar-paralelismo",
        ):
            with self.subTest(case=case_id):
                folder = ROOT / "cases" / case_id
                before = load(folder / "before.yml")
                after = load(folder / "after.yml")

                audit_report = audit(after)
                comparison_report = compare(before, after)

                self.assertEqual(comparison_report["after"], audit_report["analysis"])

    def test_audit_preserves_artifact_and_condition_controls(self):
        cases = [
            ("03-artefato-sem-ordem", "before.yml", "R02_ARTIFACT_ORDER", False),
            ("03-artefato-sem-ordem", "after.yml", "R02_ARTIFACT_ORDER", True),
            ("05-upload-condicional", "after.yml", "R03_ARTIFACT_CONDITION", True),
            ("06-consumo-protegido", "after.yml", "R03_ARTIFACT_CONDITION", False),
        ]

        for case_id, filename, expected_rule, expected_presence in cases:
            with self.subTest(case=case_id, file=filename):
                workflow = load(ROOT / "cases" / case_id / filename)
                report = audit(workflow)
                rules = collect_rules(report["analysis"]["findings"])
                self.assertEqual(expected_presence, expected_rule in rules)

    def test_report_versions_match_package_metadata(self):
        project_path = ROOT / "pyproject.toml"
        metadata = tomllib.loads(project_path.read_text(encoding="utf-8"))
        workflow = load(ROOT / "cases/03-artefato-sem-ordem/before.yml")

        self.assertEqual("0.2.0", __version__)
        self.assertEqual(metadata["project"]["version"], __version__)
        self.assertEqual(__version__, audit(workflow)["tool_version"])
        self.assertEqual(__version__, compare(workflow, workflow)["tool_version"])


if __name__ == "__main__":
    unittest.main()
