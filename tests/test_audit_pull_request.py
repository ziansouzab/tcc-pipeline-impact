import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT


class PullRequestAuditTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / ".tmp"
        temporary_root.mkdir(exist_ok=True)
        temporary_directory = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.output = self.root / "output"
        self.summary_file = self.root / "summary.md"
        self.github_output = self.root / "github-output.txt"
        self.script = ROOT / "scripts/audit_pull_request.py"
        self.environment = os.environ.copy()
        self.environment.pop("PIPELINE_IMPACT_GITHUB_EVENT", None)
        self.environment.pop("GITHUB_EVENT_PATH", None)
        self.environment.pop("GITHUB_REPOSITORY", None)
        self.environment["GITHUB_OUTPUT"] = str(self.github_output)
        self.environment["GITHUB_STEP_SUMMARY"] = str(self.summary_file)
        self.git("init", "--quiet", "--initial-branch=base")
        self.workflows = self.repository / ".github/workflows"
        self.workflows.mkdir(parents=True)
        case = ROOT / "cases/03-artefato-sem-ordem"
        self.before = (case / "before.yml").read_bytes()
        self.after = (case / "after.yml").read_bytes()

    def git(self, *arguments):
        command = [
            "git",
            "-c", "user.name=Teste Pipeline Impact",
            "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false",
            "-c", "core.autocrlf=false",
        ]
        command.extend(arguments)
        completed = subprocess.run(
            command,
            cwd=self.repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return completed.stdout.strip()

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)
        return self.git("rev-parse", "HEAD")

    def execute(self, subcommand, *arguments):
        command = [sys.executable, str(self.script), subcommand, "--directory", str(self.output)]
        command.extend(arguments)
        return subprocess.run(
            command,
            cwd=self.repository,
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def prepare(self, base, head):
        return self.execute("prepare", "--base", base, "--head", head)

    def read_summary(self):
        return self.summary_file.read_text(encoding="utf-8")

    def test_prepare_selects_changes_across_pr_and_reads_exact_blobs(self):
        main_workflow = self.workflows / "ci.yml"
        main_workflow.write_bytes(self.before)
        unchanged = self.workflows / "keep.yml"
        unchanged.write_bytes(self.before)
        renamed = self.workflows / "rename.yml"
        renamed.write_bytes(self.before)
        merge_base = self.commit("Versão comum")

        (self.workflows / "base-only.yml").write_bytes(self.before)
        base_workflow = self.before.replace(b"Experimento de pipeline", b"Workflow na base", 1)
        self.assertNotEqual(self.before, base_workflow)
        main_workflow.write_bytes(base_workflow)
        base = self.commit("Mudança independente na base")
        self.git("switch", "--quiet", "-c", "topic", merge_base)
        main_workflow.write_bytes(self.after)
        self.commit("Modifica o workflow antes do último commit")

        renamed.rename(self.workflows / "renamed.yaml")
        (self.workflows / "ci.yaml").write_bytes(self.before)
        (self.workflows / "notes.txt").write_text("Texto", encoding="utf-8")
        nested = self.workflows / "examples"
        nested.mkdir()
        (nested / "example.yml").write_bytes(self.before)
        head = self.commit("Adiciona outro workflow e renomeia o terceiro")
        self.git("switch", "--quiet", "base")

        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())
        self.assertEqual("has_workflows=true\n", self.github_output.read_text(encoding="utf-8"))
        plan = json.loads((self.output / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(base, plan["base"])
        self.assertEqual(merge_base, plan["merge_base"])
        self.assertEqual(head, plan["head"])
        expected_changes = [
            {"status": "A", "path": ".github/workflows/ci.yaml"},
            {"status": "M", "path": ".github/workflows/ci.yml"},
            {"status": "D", "path": ".github/workflows/rename.yml"},
            {"status": "A", "path": ".github/workflows/renamed.yaml"},
        ]
        self.assertEqual(expected_changes, plan["changes"])
        self.assertEqual(self.before, (self.output / "inputs/001.yml").read_bytes())
        self.assertEqual(self.after, (self.output / "inputs/002.yml").read_bytes())
        self.assertEqual(self.before, (self.output / "inputs/002-before.yml").read_bytes())
        self.assertFalse((self.output / "inputs/001-before.yml").exists())
        self.assertFalse((self.output / "inputs/003.yml").exists())
        self.assertFalse((self.output / "inputs/003-before.yml").exists())
        self.assertEqual(self.before, (self.output / "inputs/004.yml").read_bytes())
        self.assertFalse((self.output / "inputs/004-before.yml").exists())
        self.assertIn("Exclusão registrada", self.read_summary())

        result = self.execute("audit")
        self.assertEqual(0, result.returncode, self.read_summary())
        reports = self.output / "reports"
        expected_modes = {"001": "audit", "002": "compare", "004": "audit"}
        for report_id, mode in expected_modes.items():
            report_directory = reports / report_id
            self.assertTrue((report_directory / "report.md").is_file())
            report = json.loads((report_directory / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(mode, report["mode"])
        self.assertFalse((reports / "003").exists())
        self.assertIn(f"Antes ` {merge_base} `. Depois ` {head} `.", self.read_summary())
        self.assertIn("002/report.md", self.read_summary())
        self.assertIn("002/report.json", self.read_summary())

    def test_application_change_does_not_enable_audit(self):
        (self.workflows / "ci.yml").write_bytes(self.before)
        base = self.commit("Workflow com dependência")
        (self.repository / "app.txt").write_text("Aplicação", encoding="utf-8")
        head = self.commit("Altera apenas a aplicação")

        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())
        self.assertEqual("has_workflows=false\n", self.github_output.read_text(encoding="utf-8"))
        self.assertIn("Análise dispensada", self.read_summary())

    def test_deleted_workflow_is_recorded_without_enabling_audit(self):
        main_workflow = self.workflows / "ci.yml"
        main_workflow.write_bytes(self.before)
        base = self.commit("Workflow com dependência")
        main_workflow.unlink()
        head = self.commit("Exclui workflow")

        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())
        self.assertEqual("has_workflows=false\n", self.github_output.read_text(encoding="utf-8"))
        self.assertIn("Exclusão registrada", self.read_summary())
        self.assertIn(".github/workflows/ci.yml", self.read_summary())

    def test_audit_preserves_successful_reports_when_another_file_fails(self):
        (self.workflows / "ci.yml").write_bytes(self.before)
        base = self.commit("Workflow com dependência")
        (self.workflows / "broken.yml").write_bytes(b"\xff")
        (self.workflows / "ci.yml").write_bytes(self.after)
        head = self.commit("Adiciona workflow ilegível e retira a dependência")
        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())

        result = self.execute("audit")
        self.assertEqual(1, result.returncode, self.read_summary())
        reports = self.output / "reports"
        self.assertFalse((reports / "001").exists())
        report_text = (reports / "002/report.json").read_text(encoding="utf-8")
        report = json.loads(report_text)
        self.assertEqual("compare", report["mode"])
        self.assertEqual(2, report["summary"]["changes"])
        self.assertEqual([], report["before"]["findings"])
        finding = report["after"]["findings"][0]
        self.assertEqual("R02_ARTIFACT_ORDER", finding["rule"])
        self.assertEqual({"job": "verify", "step": 2}, finding["location"])
        self.assertTrue((reports / "002/report.md").is_file())
        self.assertIn("Erro de auditoria", self.read_summary())
        self.assertIn(".github/workflows/broken.yml", self.read_summary())
        self.assertIn("**1** alerta", self.read_summary())
        self.assertIn(head, self.read_summary())

    def test_comparison_uses_the_same_github_pull_request_context_for_both_revisions(self):
        workflow = self.workflows / "ci.yml"
        workflow.write_bytes(self.before)
        base = self.commit("Workflow com dependência")
        normalized_workflow = self.after.replace(b"\r\n", b"\n")
        unfiltered_events = b"'on':\n- push\n- pull_request\n"
        filtered_events = b"'on':\n  pull_request:\n    branches: [release-2026]\n"
        self.assertIn(unfiltered_events, normalized_workflow)
        workflow.write_bytes(normalized_workflow.replace(unfiltered_events, filtered_events, 1))
        head = self.commit("Remove a dependência e filtra a branch do PR")
        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())

        self.environment["PIPELINE_IMPACT_GITHUB_EVENT"] = "true"
        self.environment["GITHUB_EVENT_NAME"] = "pull_request"
        self.environment["GITHUB_REF"] = "refs/pull/42/merge"
        self.environment["GITHUB_BASE_REF"] = "release-2026"
        self.environment["GITHUB_HEAD_REF"] = "feature/atualiza-ci"
        self.environment["GITHUB_REPOSITORY"] = "lab/pipeline-impact"
        event_path = self.root / "event.json"
        event = {
            "pull_request": {
                "head": {"repo": {"full_name": "lab/pipeline-impact"}},
                "body": "PRIVATE_EXAMPLE",
            }
        }
        event_path.write_text(json.dumps(event), encoding="utf-8")
        self.environment["GITHUB_EVENT_PATH"] = str(event_path)
        result = self.execute("audit")
        self.assertEqual(0, result.returncode, self.read_summary())

        expected_context = {
            "github.event_name": "pull_request",
            "github.ref": "refs/pull/42/merge",
            "github.base_ref": "release-2026",
            "github.head_ref": "feature/atualiza-ci",
            "github.repository": "lab/pipeline-impact",
            "github.event.pull_request.head.repo.full_name": "lab/pipeline-impact",
        }
        expected_contexts = [expected_context]
        context_text = (self.output / "contexts.json").read_text(encoding="utf-8")
        self.assertEqual(expected_contexts, json.loads(context_text))
        reports = self.output / "reports"
        self.assertFalse((reports / "contexts.json").exists())
        self.assertFalse((reports / "001/contexts.json").exists())
        report_text = (reports / "001/report.json").read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE_EXAMPLE", report_text)
        report = json.loads(report_text)
        self.assertEqual("compare", report["mode"])
        self.assertEqual(expected_contexts, report["before"]["contexts_checked"])
        self.assertEqual(expected_contexts, report["after"]["contexts_checked"])
        self.assertIn("Evento recebido do GitHub ` pull_request `", self.read_summary())
        self.assertIn("Branch de destino ` release-2026 `", self.read_summary())
        self.assertIn("execução hipotética", self.read_summary())

    def test_audit_reports_missing_github_pull_request_base_ref(self):
        workflow = self.workflows / "ci.yml"
        workflow.write_bytes(self.before)
        base = self.commit("Workflow com dependência")
        workflow.write_bytes(self.after)
        head = self.commit("Remove a dependência")
        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())

        self.environment["PIPELINE_IMPACT_GITHUB_EVENT"] = "true"
        self.environment["GITHUB_EVENT_NAME"] = "pull_request"
        self.environment["GITHUB_REF"] = "refs/pull/42/merge"
        self.environment.pop("GITHUB_BASE_REF", None)
        result = self.execute("audit")
        self.assertEqual(1, result.returncode, self.read_summary())
        self.assertIn("GITHUB_BASE_REF é obrigatório", self.read_summary())
        self.assertFalse((self.output / "contexts.json").exists())
        self.assertFalse((self.output / "reports").exists())

    def test_warning_does_not_fail_the_audit_and_disappears_after_restoring_order(self):
        workflow = self.workflows / "ci.yml"
        workflow.write_bytes(self.before)
        base = self.commit("Workflow com dependência")
        workflow.write_bytes(self.after)
        head = self.commit("Remove a dependência")
        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())

        result = self.execute("audit")
        self.assertEqual(0, result.returncode, self.read_summary())
        self.assertIn("**1** alerta", self.read_summary())

        restored = self.before.replace(b"Experimento de pipeline", b"Experimento revisado", 1)
        workflow.write_bytes(restored)
        head = self.commit("Restaura a dependência e altera o nome do workflow")
        self.output = self.root / "restored-output"
        result = self.prepare(base, head)
        self.assertEqual(0, result.returncode, self.read_summary())
        result = self.execute("audit")
        self.assertEqual(0, result.returncode, self.read_summary())
        report_text = (self.output / "reports/001/report.json").read_text(encoding="utf-8")
        report = json.loads(report_text)
        self.assertEqual("compare", report["mode"])
        self.assertEqual([], report["after"]["findings"])
        self.assertIn("**0** alerta", self.read_summary())
