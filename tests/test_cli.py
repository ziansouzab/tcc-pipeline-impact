from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from pipeline_impact.analyzer import compare
from pipeline_impact.cli import main
from pipeline_impact.reporting import markdown
from tests.helpers import ROOT, collect_kinds, simple, workflow


class CliTests(unittest.TestCase):
    def setUp(self):
        (ROOT / ".tmp").mkdir(exist_ok=True)

    def test_reports_and_exit_codes(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", str(folder / "before.yml"),
                    "--after", str(folder / "after.yml"),
                    "--output", output,
                ]
                self.assertEqual(0, main(args))

                failure_args = args.copy()
                failure_args.append("--fail-on-warning")
                self.assertEqual(1, main(failure_args))

                json_path = Path(output) / "report.json"
                json_text = json_path.read_text(encoding="utf-8")
                report = json.loads(json_text)

                markdown_path = Path(output) / "report.md"
                markdown_text = markdown_path.read_text(encoding="utf-8")
                self.assertIn("```mermaid", markdown_text)
                self.assertIn("R02_ARTIFACT_ORDER", markdown_text)
                self.assertEqual("0.2", report["schema_version"])

    def test_fail_on_warning_checks_after_when_workflow_is_unchanged(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"
        warning_workflow = str(folder / "after.yml")

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", warning_workflow,
                    "--after", warning_workflow,
                    "--output", output,
                ]
                self.assertEqual(0, main(args))

                failure_args = args.copy()
                failure_args.append("--fail-on-warning")
                self.assertEqual(1, main(failure_args))

    def test_fail_on_warning_ignores_warnings_only_in_before(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", str(folder / "after.yml"),
                    "--after", str(folder / "before.yml"),
                    "--output", output,
                    "--fail-on-warning",
                ]
                self.assertEqual(0, main(args))

                report_path = Path(output) / "report.json"
                report_text = report_path.read_text(encoding="utf-8")
                report = json.loads(report_text)
                before_kinds = collect_kinds(report["before"]["findings"])
                after_kinds = collect_kinds(report["after"]["findings"])
                self.assertIn("warning", before_kinds)
                self.assertNotIn("warning", after_kinds)

    def test_fail_on_warning_does_not_fail_for_opportunities(self):
        folder = ROOT / "cases/09-revisar-paralelismo"

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            with redirect_stdout(io.StringIO()):
                args = [
                    "--before", str(folder / "before.yml"),
                    "--after", str(folder / "after.yml"),
                    "--output", output,
                    "--fail-on-warning",
                ]
                self.assertEqual(0, main(args))

                report_path = Path(output) / "report.json"
                report_text = report_path.read_text(encoding="utf-8")
                report = json.loads(report_text)
                after_kinds = collect_kinds(report["after"]["findings"])
                self.assertIn("opportunity", after_kinds)
                self.assertNotIn("warning", after_kinds)

    def test_old_warning_flag_is_rejected(self):
        folder = ROOT / "cases/03-artefato-sem-ordem"
        args = [
            "--before", str(folder / "before.yml"),
            "--after", str(folder / "after.yml"),
            "--fail-on-new-warning",
        ]

        with redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as raised:
                main(args)

        self.assertEqual(2, raised.exception.code)
        self.assertIn("--fail-on-new-warning", error.getvalue())

    def test_bad_input_returns_two_without_traceback(self):
        with redirect_stderr(io.StringIO()) as error:
            args = ["--before", "missing.yml", "--after", "missing.yml"]
            self.assertEqual(2, main(args))
            args.append("--fail-on-warning")
            self.assertEqual(2, main(args))
            self.assertNotIn("Traceback", error.getvalue())

    def test_invalid_utf8_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary_folder:
            workflow_path = Path(temporary_folder) / "invalid-encoding.yml"
            workflow_path.write_bytes(b"on: push\njobs: \xff\n")
            output_path = Path(temporary_folder) / "report"
            arguments = [
                "--before", str(workflow_path),
                "--after", str(workflow_path),
                "--output", str(output_path),
            ]

            with redirect_stderr(io.StringIO()) as error:
                exit_code = main(arguments)

            self.assertEqual(2, exit_code)
            self.assertIn("UTF-8", error.getvalue())
            self.assertNotIn("Traceback", error.getvalue())
            self.assertFalse(output_path.exists())

    def test_unsupported_yaml_returns_two_without_traceback(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary_folder:
            workflow_path = Path(temporary_folder) / "unsupported-value.yml"
            workflow_text = (
                "on: push\n"
                "jobs:\n"
                "  build:\n"
                "    env:\n"
                "      RELEASE_DATE: 2026-11-09\n"
                "    steps: []\n"
            )
            workflow_path.write_text(workflow_text, encoding="utf-8")
            output_path = Path(temporary_folder) / "report"
            arguments = [
                "--before", str(workflow_path),
                "--after", str(workflow_path),
                "--output", str(output_path),
            ]

            with redirect_stderr(io.StringIO()) as error:
                exit_code = main(arguments)

            self.assertEqual(2, exit_code)
            self.assertIn("valores YAML não suportados", error.getvalue())
            self.assertNotIn("Traceback", error.getvalue())
            self.assertFalse(output_path.exists())

    def test_report_does_not_dump_run_secrets(self):
        old = workflow({"a": simple()})
        new = workflow({
            "a": simple(steps=[{"run": "echo PRIVATE_EXAMPLE"}]),
        })
        report = compare(old, new)
        report_text = json.dumps(report)
        markdown_text = markdown(report)
        self.assertNotIn("PRIVATE_EXAMPLE", report_text)
        self.assertIn("STEP_CHANGE", markdown_text)


if __name__ == "__main__":
    unittest.main()
