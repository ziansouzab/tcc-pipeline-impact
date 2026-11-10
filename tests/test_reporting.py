import unittest

from pipeline_impact.analyzer import audit, compare
from pipeline_impact.model import load
from pipeline_impact.reporting import markdown
from tests.helpers import ROOT, artifact, simple, workflow


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
        self.assertIn("**Onde** job `verify`, step `2` (posição na lista).", report_text)
        self.assertIn("O download de `app` tem uploads reconhecidos nos jobs `build`.", report_text)
        self.assertIn("**Consequência possível**", report_text)
        self.assertIn("**Revisão sugerida**", report_text)
        self.assertIn("## Cobertura da análise", report_text)

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
        self.assertIn("### Cobertura antes", report_text)
        self.assertIn("### Cobertura depois", report_text)

    def test_header_uses_report_tool_version(self):
        workflow_path = ROOT / "cases/03-artefato-sem-ordem/before.yml"
        analysis = audit(load(workflow_path))
        analysis["tool_version"] = "9.8.7"

        report_text = markdown(analysis)

        self.assertIn("Protótipo 9.8.7", report_text)
        self.assertIn("Nenhum achado pelas regras implementadas", report_text)

    def test_conditional_artifact_explains_upload_location_and_context(self):
        workflow_path = ROOT / "cases/05-upload-condicional/after.yml"
        analysis = audit(load(workflow_path))

        report_text = markdown(analysis)

        self.assertIn("Consumo ativo com uploads anteriores desativados", report_text)
        self.assertIn("**Onde** job `verify`, step `2` (posição na lista).", report_text)
        self.assertIn("uploads anteriores reconhecidos ficam desativados em job `build`, step `3`", report_text)
        self.assertIn("**Contexto modelado**", report_text)
        self.assertIn("`github.event_name` = `pull_request`", report_text)

    def test_parallel_review_identifies_the_dependency(self):
        workflow_path = ROOT / "cases/09-revisar-paralelismo/after.yml"
        analysis = audit(load(workflow_path))

        report_text = markdown(analysis)

        self.assertIn("Dependência a revisar para possível paralelismo", report_text)
        self.assertIn("**Onde** job `verify`, campo `needs`.", report_text)
        self.assertIn("O job `verify` declara `lint` em `needs`.", report_text)
        self.assertIn("dependência `lint` → `verify`", report_text)

    def test_coverage_identifies_the_relation_protected_by_a_dependency(self):
        workflow_path = ROOT / "cases/10-dependencia-necessaria/after.yml"
        analysis = audit(load(workflow_path))

        report_text = markdown(analysis)

        self.assertIn("dependência `build` → `verify`", report_text)
        self.assertIn("relação protegida `build` → `verify`", report_text)

    def test_input_text_stays_literal_in_report(self):
        artifact_name = "app [rede](https://example.org) `<b>`"
        download_step = artifact(False, name=artifact_name)
        invalid_condition = "<script> [outro](https://example.org)"
        private_step = {"run": "echo PRIVATE_REPORT_COMMAND", "if": invalid_condition}
        workflow_model = workflow({"consumer": simple(steps=[download_step, private_step])})
        analysis = audit(workflow_model)

        report_text = markdown(analysis)

        self.assertIn(f"`` {artifact_name} ``", report_text)
        self.assertIn("&lt;script&gt; &#91;outro&#93;&#40;https&#58;//example.org&#41;", report_text)
        self.assertNotIn(invalid_condition, report_text)
        self.assertNotIn("PRIVATE_REPORT_COMMAND", report_text)

    def test_legacy_comparison_preserves_known_step_without_inferring_consumer_job(self):
        case_directory = ROOT / "cases/03-artefato-sem-ordem"
        before_workflow = load(case_directory / "before.yml")
        after_workflow = load(case_directory / "after.yml")
        analysis = compare(before_workflow, after_workflow)
        analysis["schema_version"] = "0.2"
        analysis["tool_version"] = "0.1.0"
        analysis.pop("mode")

        for side in ("before", "after"):
            analysis[side].pop("coverage")
            for finding in analysis[side]["findings"]:
                finding.pop("location")

        report_text = markdown(analysis)

        self.assertIn("**Jobs envolvidos** `build`, `verify`.", report_text)
        self.assertIn("O step consumidor ocupa a posição `2` na sua lista.", report_text)
        self.assertNotIn("**Onde**", report_text)
        self.assertNotIn("## Cobertura da análise", report_text)


if __name__ == "__main__":
    unittest.main()
