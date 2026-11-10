from __future__ import annotations

import html
import json


def diagram(model: dict) -> str:
    node_ids = {}
    for index, job in enumerate(model["jobs"]):
        node_ids[job] = f"n{index}"

    lines = ["flowchart LR"]

    for job in model["jobs"]:
        node_id = node_ids[job]
        label = html.escape(job)
        lines.append(f'  {node_id}["{label}"]')

    for source, target in model["edges"]:
        source_id = node_ids[source]
        target_id = node_ids[target]
        lines.append(f"  {source_id} --> {target_id}")

    return "\n".join(lines)


def safe_cell(value) -> str:
    text = str(value)
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.replace("|", "&#124;")
    text = html.escape(text, quote=False)
    text = text.replace("&amp;#124;", "&#124;")
    return text


def comparison_lines(report: dict) -> list[str]:
    before_diagram = diagram(report["before"])
    after_diagram = diagram(report["after"])

    lines = [
        "# Análise de impacto da pipeline",
        "",
        f"Protótipo {report['tool_version']} — resultado estático, sujeito às premissas abaixo.",
        "",
        f"Mudanças identificadas: **{len(report['changes'])}**.",
        "",
        "## Grafos de dependências",
        "",
        "### Antes",
        "",
        "```mermaid",
        before_diagram,
        "```",
        "",
        "### Depois",
        "",
        "```mermaid",
        after_diagram,
        "```",
        "",
        "## Mudanças",
        "",
        "| Regra | Job | Evidência | Etapas posteriores afetadas |",
        "|---|---|---|---|",
    ]

    for change in report["changes"]:
        if "before" in change:
            evidence = f"{change['before']} → {change['after']}"
        elif "field" in change:
            evidence = change["field"]
        elif "change" in change:
            evidence = change["change"]
        else:
            evidence = "eventos"

        affected_jobs = ", ".join(change["affected_jobs"])
        if not affected_jobs:
            affected_jobs = "—"

        cell_values = [
            change["rule"],
            change.get("job", "workflow"),
            evidence,
            affected_jobs,
        ]
        safe_values = []
        for cell_value in cell_values:
            safe_values.append(safe_cell(cell_value))

        table_row = "| " + " | ".join(safe_values) + " |"
        lines.append(table_row)

    if not report["changes"]:
        lines.append("| — | — | Nenhuma mudança nas propriedades acompanhadas | — |")

    return lines


def audit_lines(report: dict) -> list[str]:
    analysis = report["analysis"]
    workflow_diagram = diagram(analysis)
    source = safe_cell(analysis["source"])
    warnings = report["summary"].get("warning", 0)
    opportunities = report["summary"].get("opportunity", 0)

    lines = [
        "# Auditoria da pipeline",
        "",
        f"Protótipo {report['tool_version']} — resultado estático, sujeito às premissas abaixo.",
        "",
        f"Arquivo: {source}.",
        "",
        f"Alertas: **{warnings}**. Oportunidades de revisão: **{opportunities}**.",
        "",
        "## Grafo de dependências",
        "",
        "```mermaid",
        workflow_diagram,
        "```",
    ]
    return lines


def finding_lines(findings: list[dict]) -> list[str]:
    lines = []

    if not findings:
        lines.append(
            "Nenhum achado pelas regras implementadas. Isso não comprova ausência de problemas."
        )

    for current_finding in findings:
        rule = current_finding["rule"]
        kind = current_finding["kind"]
        job_names = ", ".join(current_finding["jobs"])
        safe_job_names = safe_cell(job_names)
        reason = safe_cell(current_finding["evidence"]["reason"])

        lines.extend([
            f"### {rule} · {kind}",
            "",
            f"Jobs: {safe_job_names}.",
            "",
            reason,
            "",
        ])

        if current_finding["artifact"]:
            artifact_name = safe_cell(current_finding["artifact"])
            lines.extend([f"Artefato: {artifact_name}.", ""])

        if current_finding["context"]:
            context_text = json.dumps(
                current_finding["context"],
                ensure_ascii=False,
            )
            safe_context = safe_cell(context_text)
            lines.extend([f"Contexto: {safe_context}.", ""])

        details = {}
        for key, value in current_finding["evidence"].items():
            if key != "reason":
                details[key] = value

        details_text = json.dumps(details, ensure_ascii=False)
        safe_details = safe_cell(details_text)
        lines.extend([f"Evidência: {safe_details}.", ""])

        if current_finding["suggestion"]:
            suggestion_text = safe_cell(current_finding["suggestion"])
            lines.extend([suggestion_text, ""])

    return lines


def unordered_pair_lines(analysis: dict) -> list[str]:
    unordered_pairs = analysis["structurally_unordered_pairs"]
    lines = [
        "",
        "## Pares sem ordem imposta por needs",
        "",
        safe_cell(unordered_pairs),
        "",
        "Não equivale a paralelismo observado nem a economia potencial.",
    ]
    return lines


def assumption_lines(report: dict, snapshots: list[tuple[str, dict]]) -> list[str]:
    lines = ["", "## Premissas e limites", ""]

    for assumption in report["assumptions"]:
        lines.append(f"- {safe_cell(assumption)}")

    for label, analysis in snapshots:
        for limitation in analysis["limitations"]:
            lines.append(f"- {label}: {safe_cell(limitation)}")

    return lines


def markdown(report: dict) -> str:
    mode = report.get("mode", "compare")

    if mode == "audit":
        analysis = report["analysis"]
        lines = audit_lines(report)
        findings_title = "## Alertas e oportunidades do workflow"
        snapshots = [("Workflow", analysis)]
    else:
        analysis = report["after"]
        lines = comparison_lines(report)
        findings_title = "## Alertas e oportunidades da versão modificada"
        snapshots = [
            ("Antes", report["before"]),
            ("Depois", report["after"]),
        ]

    lines.extend(["", findings_title, ""])
    lines.extend(finding_lines(analysis["findings"]))
    lines.extend(unordered_pair_lines(analysis))
    lines.extend(assumption_lines(report, snapshots))

    rendered_text = "\n".join(lines)
    return rendered_text + "\n"
