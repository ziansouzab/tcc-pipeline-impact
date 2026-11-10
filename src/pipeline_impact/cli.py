from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .analyzer import audit, compare
from .model import InputError, load
from .reporting import markdown


def parse_arguments(argv):
    if argv is None:
        arguments = sys.argv[1:]
    else:
        arguments = list(argv)

    is_audit = False
    if arguments:
        if arguments[0] == "audit":
            is_audit = True

    if is_audit:
        parser = argparse.ArgumentParser(
            prog="pipeline-impact audit",
            description="Audita um workflow local sem executar seus comandos ou actions.",
        )
        parser.add_argument("workflow", type=Path, help="Workflow que será auditado")
        selected_arguments = arguments[1:]
        mode = "audit"
    else:
        parser = argparse.ArgumentParser(
            prog="pipeline-impact",
            description="Compara workflows locais sem executá-los.",
            epilog="Para auditar um único arquivo: pipeline-impact audit WORKFLOW. Consulte audit --help.",
        )
        parser.add_argument("--before", required=True, type=Path, help="Workflow anterior")
        parser.add_argument("--after", required=True, type=Path, help="Workflow modificado")
        selected_arguments = arguments
        mode = "compare"

    parser.add_argument("--output", type=Path, default=Path("reports/latest"), help="Pasta dos relatórios")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Retornar 1 se houver warning na configuração auditada ou na versão modificada",
    )
    args = parser.parse_args(selected_arguments)
    args.mode = mode
    return args


def main(argv=None) -> int:
    args = parse_arguments(argv)

    try:
        sources = set()
        if args.mode == "audit":
            sources.add(args.workflow.resolve())
        else:
            sources.add(args.before.resolve())
            sources.add(args.after.resolve())

        for extension in ("md", "json"):
            report_path = args.output / f"report.{extension}"
            if report_path.resolve() in sources:
                raise InputError("O relatório não pode sobrescrever um workflow de entrada.")

        if args.mode == "audit":
            current_workflow = load(args.workflow)
            report = audit(current_workflow)
        else:
            before_workflow = load(args.before)
            after_workflow = load(args.after)
            report = compare(before_workflow, after_workflow)

        rendered = markdown(report)

        args.output.mkdir(parents=True, exist_ok=True)
        json_path = args.output / "report.json"
        markdown_path = args.output / "report.md"
        json_text = json.dumps(report, ensure_ascii=False, indent=2)
        json_path.write_text(json_text + "\n", encoding="utf-8")
        markdown_path.write_text(rendered, encoding="utf-8")

    except (InputError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    warnings = []
    if args.mode == "audit":
        findings = report["analysis"]["findings"]
    else:
        findings = report["after"]["findings"]

    for finding in findings:
        if finding["kind"] == "warning":
            warnings.append(finding)

    if args.mode == "audit":
        print(f"Auditoria concluída; alertas atuais: {len(warnings)}.")
    else:
        print(f"Mudanças: {len(report['changes'])}; alertas atuais: {len(warnings)}.")
    print(f"Relatórios: {args.output.resolve()}")

    if args.fail_on_warning:
        if warnings:
            return 1

    return 0
