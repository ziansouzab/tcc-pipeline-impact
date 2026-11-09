from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .analyzer import compare
from .model import InputError, load
from .reporting import markdown


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compara workflows locais sem executá-los.")
    parser.add_argument("--before", required=True, type=Path, help="Workflow anterior")
    parser.add_argument("--after", required=True, type=Path, help="Workflow modificado")
    parser.add_argument("--output", type=Path, default=Path("reports/latest"), help="Pasta dos relatórios")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Retornar 1 se houver alerta na versão modificada",
    )
    args = parser.parse_args(argv)

    try:
        sources = {args.before.resolve(), args.after.resolve()}

        for extension in ("md", "json"):
            report_path = args.output / f"report.{extension}"
            if report_path.resolve() in sources:
                raise InputError("O relatório não pode sobrescrever um workflow de entrada.")

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
    for finding in report["after"]["findings"]:
        if finding["kind"] == "warning":
            warnings.append(finding)

    print(f"Mudanças: {len(report['changes'])}; alertas atuais: {len(warnings)}.")
    print(f"Relatórios: {args.output.resolve()}")

    if args.fail_on_warning:
        if warnings:
            return 1

    return 0
