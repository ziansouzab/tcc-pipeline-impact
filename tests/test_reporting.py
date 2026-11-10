import unittest

from pipeline_impact.analyzer import audit, compare
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown
from tests.helpers import ROOT


class ReportingTests(unittest.TestCase):
    def test_audit_has_one_graph_and_no_comparison_sections(self):
        workflow_path = ROOT / "cases/03-artefato-sem-ordem/after.yml"
        analysis = audit(load(workflow_path))

        report_text = markdown(analysis)

        self.assertIn("# Auditoria da pipeline", report_text)
        self.assertIn(str(workflow_path), report_text)
        self.assertEqual(1, report_text.count("```mermaid"))
        self.assertNotIn("## Mudanças", report_text)
        self.assertNotIn("### Antes", report_text)
        self.assertNotIn("### Depois", report_text)
        self.assertIn("R02_ARTIFACT_ORDER", report_text)
        self.assertIn("Alertas: **1**", report_text)

    def test_comparison_retains_two_graphs_and_changes(self):
        case_directory = ROOT / "cases/03-artefato-sem-ordem"
        before_workflow = load(case_directory / "before.yml")
        after_workflow = load(case_directory / "after.yml")
        analysis = compare(before_workflow, after_workflow)

        report_text = markdown(analysis)

        self.assertIn("# Análise de impacto da pipeline", report_text)
        self.assertEqual(2, report_text.count("```mermaid"))
        self.assertIn("## Mudanças", report_text)
        self.assertIn("### Antes", report_text)
        self.assertIn("### Depois", report_text)
        self.assertIn("Mudanças identificadas: **2**", report_text)

    def test_header_uses_report_tool_version(self):
        workflow_path = ROOT / "cases/03-artefato-sem-ordem/before.yml"
        analysis = audit(load(workflow_path))
        analysis["tool_version"] = "9.8.7"

        report_text = markdown(analysis)

        self.assertIn("Protótipo 9.8.7", report_text)
        self.assertIn("Nenhum achado pelas regras implementadas", report_text)


if __name__ == "__main__":
    unittest.main()
