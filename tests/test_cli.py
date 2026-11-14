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
                self.assertEqual("0.6", report["schema_version"])
                self.assertEqual("compare", report["mode"])

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

    def test_audit_reports_only_current_workflow(self):
        workflow_path = ROOT / "cases/03-artefato-sem-ordem/after.yml"

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            arguments = [
                "audit", str(workflow_path),
                "--output", output,
            ]

            with redirect_stdout(io.StringIO()):
                exit_code = main(arguments)

            report_text = (Path(output) / "report.json").read_text(encoding="utf-8")
            report = json.loads(report_text)
            markdown_text = (Path(output) / "report.md").read_text(encoding="utf-8")

            self.assertEqual(0, exit_code)
            self.assertEqual("audit", report["mode"])
            self.assertEqual("0.6", report["schema_version"])
            self.assertEqual(["build", "verify"], report["analysis"]["jobs"])
            self.assertEqual(1, report["summary"]["warning"])
            self.assertNotIn("before", report)
            self.assertNotIn("after", report)
            self.assertNotIn("changes", report)
            self.assertEqual(1, markdown_text.count("```mermaid"))
            self.assertNotIn("## Mudanças", markdown_text)
            self.assertIn("R02_ARTIFACT_ORDER", markdown_text)

    def test_audit_before_workflow_has_no_artifact_warning(self):
        workflow_path = ROOT / "cases/03-artefato-sem-ordem/before.yml"

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            arguments = [
                "audit", str(workflow_path),
                "--output", output,
            ]

            with redirect_stdout(io.StringIO()):
                exit_code = main(arguments)

            report_text = (Path(output) / "report.json").read_text(encoding="utf-8")
            report = json.loads(report_text)

            self.assertEqual(0, exit_code)
            self.assertEqual(0, report["summary"]["warning"])
            self.assertEqual([], report["analysis"]["findings"])

    def test_audit_evaluates_only_explicit_contexts(self):
        workflow_path = ROOT / "cases/05-upload-condicional/after.yml"
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
            arguments = ["audit", str(workflow_path), "--output", output]
            report_path = Path(output) / "report.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(arguments))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual([], report["analysis"]["contexts_checked"])
            self.assertEqual(0, report["summary"]["warning"])

            arguments.extend(["--contexts", str(ROOT / "cases/contexts.json")])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, main(arguments))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(3, len(report["analysis"]["contexts_checked"]))
            self.assertGreater(report["summary"]["warning"], 0)

    def test_audit_warning_policy_ignores_opportunities(self):
        scenarios = [
            ("03-artefato-sem-ordem", 1, "warning"),
            ("09-revisar-paralelismo", 0, "opportunity"),
        ]

        for case_id, expected_exit, expected_kind in scenarios:
            with self.subTest(case=case_id):
                workflow_path = ROOT / "cases" / case_id / "after.yml"

                with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as output:
                    arguments = [
                        "audit", str(workflow_path),
                        "--output", output,
                        "--fail-on-warning",
                    ]

                    with redirect_stdout(io.StringIO()):
                        exit_code = main(arguments)

                    report_text = (Path(output) / "report.json").read_text(encoding="utf-8")
                    report = json.loads(report_text)
                    finding_kinds = collect_kinds(report["analysis"]["findings"])

                    self.assertEqual(expected_exit, exit_code)
                    self.assertIn(expected_kind, finding_kinds)

    def test_audit_rejects_ambiguous_and_missing_arguments(self):
        workflow_path = str(ROOT / "cases/03-artefato-sem-ordem/after.yml")
        invalid_arguments = [
            ["audit", workflow_path, "--before", workflow_path],
            ["audit", workflow_path, "--after", workflow_path],
            ["--before", workflow_path, "--after", workflow_path, "audit", workflow_path],
            ["audit"],
            [],
        ]

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        main(arguments)

                self.assertEqual(2, raised.exception.code)

    def test_help_describes_audit_and_comparison(self):
        with redirect_stdout(io.StringIO()) as comparison_help:
            with self.assertRaises(SystemExit) as comparison_exit:
                main(["--help"])

        self.assertEqual(0, comparison_exit.exception.code)
        self.assertIn("audit", comparison_help.getvalue())
        self.assertIn("--before", comparison_help.getvalue())
        self.assertIn("--after", comparison_help.getvalue())

        with redirect_stdout(io.StringIO()) as audit_help:
            with self.assertRaises(SystemExit) as audit_exit:
                main(["audit", "--help"])

        self.assertEqual(0, audit_exit.exception.code)
        self.assertIn("workflow", audit_help.getvalue())
        self.assertIn("--output", audit_help.getvalue())
        self.assertIn("--fail-on-warning", audit_help.getvalue())
        self.assertNotIn("--before", audit_help.getvalue())

    def test_audit_invalid_inputs_return_two_without_traceback(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary_folder:
            invalid_path = Path(temporary_folder) / "invalid-encoding.yml"
            invalid_path.write_bytes(b"on: push\njobs: \xff\n")
            missing_path = Path(temporary_folder) / "missing.yml"
            output_path = Path(temporary_folder) / "reports"
            invalid_paths = [missing_path, invalid_path]

            for workflow_path in invalid_paths:
                with self.subTest(workflow=workflow_path.name):
                    arguments = [
                        "audit", str(workflow_path),
                        "--output", str(output_path),
                    ]

                    with redirect_stderr(io.StringIO()) as error:
                        exit_code = main(arguments)

                    self.assertEqual(2, exit_code)
                    self.assertIn("Erro:", error.getvalue())
                    self.assertNotIn("Traceback", error.getvalue())
                    self.assertFalse(output_path.exists())

    def test_audit_cannot_overwrite_input_with_report(self):
        source_path = ROOT / "cases/03-artefato-sem-ordem/after.yml"
        source_bytes = source_path.read_bytes()

        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary_folder:
            workflow_path = Path(temporary_folder) / "report.md"
            workflow_path.write_bytes(source_bytes)
            arguments = [
                "audit", str(workflow_path),
                "--output", temporary_folder,
            ]

            with redirect_stderr(io.StringIO()) as error:
                exit_code = main(arguments)

            self.assertEqual(2, exit_code)
            self.assertIn("sobrescrever", error.getvalue())
            self.assertEqual(source_bytes, workflow_path.read_bytes())
            self.assertFalse((Path(temporary_folder) / "report.json").exists())

    def test_comparison_cannot_overwrite_either_input(self):
        source_path = ROOT / "cases/03-artefato-sem-ordem/after.yml"
        source_bytes = source_path.read_bytes()
        collisions = [
            ("--before", "report.md"),
            ("--after", "report.json"),
        ]

        for source_argument, filename in collisions:
            with self.subTest(argument=source_argument, filename=filename):
                with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as temporary_folder:
                    workflow_path = Path(temporary_folder) / filename
                    workflow_path.write_bytes(source_bytes)
                    before_path = source_path
                    after_path = source_path

                    if source_argument == "--before":
                        before_path = workflow_path
                    else:
                        after_path = workflow_path

                    arguments = [
                        "--before", str(before_path),
                        "--after", str(after_path),
                        "--output", temporary_folder,
                    ]

                    with redirect_stderr(io.StringIO()) as error:
                        exit_code = main(arguments)

                    self.assertEqual(2, exit_code)
                    self.assertIn("sobrescrever", error.getvalue())
                    self.assertEqual(source_bytes, workflow_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
