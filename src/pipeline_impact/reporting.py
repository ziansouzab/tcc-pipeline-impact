from __future__ import annotations

import html


COVERAGE_NAMES = {
    "artifact_recognition": "Reconhecimento de artefatos",
    "R02_ARTIFACT_ORDER": "Precedência de artefatos",
    "R03_ARTIFACT_CONDITION": "Condições de artefatos",
    "R05_PARALLEL_REVIEW": "Revisão de paralelismo",
    "R06_NEEDS_DIRECT_DEPENDENCY": "Dependência direta para o contexto needs",
}
COVERAGE_STATES = {
    "executed": "Executada",
    "partial": "Parcial",
    "suspended": "Suspensa",
    "not_applicable": "Não aplicável",
}


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
    text = html.escape(text, quote=False)

    markdown_characters = ("#", "\\", "`", "*", "_", "[", "]", "(", ")", "~", "|", "!", "@")
    for character in markdown_characters:
        code_point = ord(character)
        text = text.replace(character, f"&#{code_point};")

    text = text.replace("://", "&#58;//")
    text = text.replace("www.", "www&#46;")
    return text


def inline_code(value) -> str:
    text = str(value)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    longest_run = 0
    current_run = 0

    for character in text:
        if character == "`":
            current_run += 1
            if current_run > longest_run:
                longest_run = current_run
        else:
            current_run = 0

    delimiter = "`" * (longest_run + 1)
    if text.startswith(("`", " ")) or text.endswith(("`", " ")):
        return f"{delimiter} {text} {delimiter}"

    return f"{delimiter}{text}{delimiter}"


def names_as_code(names: list[str]) -> str:
    labels = []
    for name in names:
        labels.append(inline_code(name))
    return ", ".join(labels)


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
            change.get("job", "workflow"),
            evidence,
            affected_jobs,
        ]
        rule_code = change["rule"].replace("|", "\\|")
        safe_values = [inline_code(rule_code)]
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
    source = inline_code(analysis["source"])
    warnings = report["summary"].get("warning", 0)
    opportunities = report["summary"].get("opportunity", 0)

    lines = [
        "# Auditoria da pipeline",
        "",
        f"Protótipo {report['tool_version']} — resultado estático, sujeito às premissas abaixo.",
        "",
        f"Arquivo {source}.",
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


def location_text(location: dict) -> str:
    description = f"job {inline_code(location['job'])}"
    if "step" in location:
        description += f", step {inline_code(location['step'])} (posição na lista)"
    if "field" in location:
        description += f", campo {inline_code(location['field'])}"
    return description


def context_text(context: dict) -> str:
    parts = []
    for key, value in context.items():
        key_text = inline_code(key)
        value_text = inline_code(value)
        parts.append(f"{key_text} = {value_text}")
    return ", ".join(parts)


def step_change_lines(step_changes: list[dict]) -> list[str]:
    if not step_changes:
        return []

    titles = {
        "added": "Step adicionado",
        "removed": "Step removido",
        "modified": "Step modificado",
        "reordered": "Ordem relativa alterada",
        "unmatched": "Correspondência indeterminada",
    }
    states = {
        "active": "ativo",
        "skipped": "pulado",
        "indeterminate": "indeterminado",
        "event_excluded": "evento excluído pelo workflow",
    }
    lines = ["", "## Alterações nos steps", ""]
    for change in step_changes:
        job = inline_code(change["job"])
        title = titles[change["change"]]
        lines.extend([f"### {title} no job {job}", ""])
        for side, label in (("before", "Antes"), ("after", "Depois")):
            position = change[f"{side}_step"]
            if position is None:
                continue
            name = change[f"{side}_name"]
            line = f"- {label} no step {position}"
            if name:
                line += f" ({inline_code(name)})"
            lines.append(line + ".")

        for field, values in change["fields"].items():
            before = inline_code(values["before"])
            after = inline_code(values["after"])
            lines.append(f"- {inline_code(field)} passou de {before} para {after}.")

        if change["other_fields"]:
            names = names_as_code(change["other_fields"])
            lines.append(f"- Outros campos alterados {names}.")

        policy = change["fields"].get("continue-on-error")
        if policy is not None:
            if policy["before"] is False and policy["after"] is True:
                lines.append("- Efeito possível. Se o step falhar, sua falha passa a ser tolerada na conclusão do job.")
            elif policy["before"] is True and policy["after"] is False:
                lines.append("- Efeito possível. Se o step falhar, sua falha pode voltar a reprovar o job.")
            else:
                lines.append("- A tolerância à falha depende do valor configurado na execução.")

        if change["change"] == "unmatched":
            lines.append("- O modelo não encontrou uma correspondência única entre as versões.")

        if "context_comparisons" in change:
            context_comparisons = change["context_comparisons"]
            if not context_comparisons:
                lines.append("- A avaliação condicional requer contextos de evento.")
            for comparison in context_comparisons:
                context = context_text(comparison["context"])
                before = states[comparison["before"]]
                after = states[comparison["after"]]
                lines.append(f"- Estado modelado no contexto {context} (**{before} → {after}**).")
        lines.append("")
    return lines


def impact_link_lines(report: dict) -> list[str]:
    links = report.get("impact_links", [])
    if not links:
        return []

    findings_by_id = {}
    for finding in report["after"]["findings"]:
        findings_by_id[finding["id"]] = finding

    lines = ["", "## Impactos explicados", ""]
    for link in links:
        finding = findings_by_id[link["finding_id"]]
        rule = inline_code(finding["rule"])
        location = location_text(link["location"])
        evidence = link["evidence"]
        if link["type"] == "upload_condition_changed":
            producer = inline_code(evidence["producer_job"])
            position = evidence["producer_step_after"]
            artifact = inline_code(evidence["artifact"])
            context = context_text(link["context"])
            lines.append(
                f"- {rule} em {location}. Alterar o `if` do upload de {artifact} "
                f"em {producer}, step {position}, fez o upload passar de ativo para pulado "
                f"no contexto {context}. Restaurar somente o `if` anterior "
                "reativa o upload no modelo e mantém o download ativo."
            )
            continue

        source, target = evidence["removed_edge"]
        source_text = inline_code(source)
        target_text = inline_code(target)
        if link["type"] == "artifact_order_lost":
            artifact = inline_code(evidence["artifact"])
            effect = (
                f"O download de {artifact} perdeu a precedência reconhecida. Restaurar "
                f"{source_text} em `needs` de {target_text} recupera a ordem no modelo."
            )
        else:
            reference = inline_code(evidence["reference"])
            effect = (
                f"Remover {source_text} do `needs` direto de {target_text} deixa "
                f"{reference} sem a entrada do produtor no contexto."
            )
            if evidence["order_preserved"]:
                effect += " A ordem entre os jobs permanece por um caminho indireto."

        lines.append(f"- {rule} em {location}. {effect}")
    return lines


def finding_explanation(finding: dict) -> tuple[str, str, str]:
    rule = finding["rule"]
    evidence = finding["evidence"]

    if rule == "R02_ARTIFACT_ORDER":
        title = "Consumo de artefato sem precedência garantida"
        artifact = inline_code(finding["artifact"])
        producers = evidence["producer_jobs"]

        if producers:
            producer_names = names_as_code(producers)
            explanation = (
                f"O download de {artifact} tem uploads reconhecidos nos jobs {producer_names}. "
                "A análise de precedência não identificou um upload garantido antes desse download."
            )
        else:
            explanation = (
                f"O download de {artifact} tem zero uploads com o mesmo nome "
                "entre as actions de artefato reconhecidas."
            )

        consequence = "O download pode ocorrer antes de o artefato estar disponível."
        return title, explanation, consequence

    if rule == "R03_ARTIFACT_CONDITION":
        title = "Consumo ativo com uploads anteriores desativados"
        artifact = inline_code(finding["artifact"])
        producer_steps = []
        for producer in evidence["producer_steps"]:
            producer_steps.append(location_text(producer))

        producer_text = ", ".join(producer_steps)
        explanation = (
            f"O download de {artifact} está ativo no cenário modelado. "
            f"Os uploads anteriores reconhecidos ficam desativados em {producer_text}."
        )
        consequence = "O download pode ficar sem o artefato nesse cenário."
        return title, explanation, consequence

    if rule == "R05_PARALLEL_REVIEW":
        title = "Dependência a revisar para possível paralelismo"
        source, target = evidence["edge"]
        source_name = inline_code(source)
        target_name = inline_code(target)
        explanation = (
            f"O job {target_name} declara {source_name} em `needs`. "
            "O teste estrutural indica que retirar a aresta altera a ordem "
            "e preserva as relações de dados reconhecidas."
        )
        consequence = "A revisão da dependência pode abrir uma oportunidade de paralelismo."
        return title, explanation, consequence

    if rule == "R06_NEEDS_DIRECT_DEPENDENCY":
        title = "Referência ao contexto needs sem dependência direta"
        reference = inline_code(evidence["reference"])
        explanation = f"O job usa {reference}. {evidence['reason']}"
        consequence = "O contexto needs do consumidor fica sem a entrada do job referenciado."
        return title, explanation, consequence

    return safe_cell(rule), safe_cell(evidence["reason"]), ""


def finding_lines(findings: list[dict]) -> list[str]:
    lines = []

    if not findings:
        lines.append("Nenhum achado pelas regras implementadas no escopo analisado.")

    for current_finding in findings:
        rule = inline_code(current_finding["rule"])
        title, explanation, consequence = finding_explanation(current_finding)
        kind = current_finding["kind"]
        if kind == "warning":
            kind = "Alerta"
        elif kind == "opportunity":
            kind = "Oportunidade de revisão"
        else:
            kind = safe_cell(kind)

        lines.extend([f"### {title} ({rule})", "", kind, ""])

        location = current_finding.get("location")
        if location:
            where = location_text(location)
            lines.extend([f"**Onde** {where}.", ""])
        else:
            job_names = names_as_code(current_finding["jobs"])
            lines.extend([f"**Jobs envolvidos** {job_names}.", ""])
            consumer_step = current_finding["evidence"].get("consumer_step")
            if consumer_step is not None:
                step = inline_code(consumer_step)
                lines.extend([f"O step consumidor ocupa a posição {step} na sua lista.", ""])

        lines.extend([f"**Evidência** {explanation}", ""])
        if consequence:
            lines.extend([f"**Consequência possível** {consequence}", ""])

        context = current_finding["context"]
        if context:
            modeled_context = context_text(context)
            lines.extend([f"**Contexto modelado** {modeled_context}.", ""])
        else:
            lines.extend(["**Contexto** análise da estrutura do workflow.", ""])

        if current_finding["suggestion"]:
            suggestion = safe_cell(current_finding["suggestion"])
            lines.extend([f"**Revisão sugerida** {suggestion}", ""])

    return lines


def coverage_detail_line(detail: dict) -> str:
    description = safe_cell(detail["message"])
    qualifiers = []

    location = detail.get("location")
    if location:
        qualifiers.append(location_text(location))

    context = detail.get("context")
    if context:
        qualifiers.append(context_text(context))

    edge = detail.get("edge")
    if edge:
        source, target = edge
        source_name = inline_code(source)
        target_name = inline_code(target)
        qualifiers.append(f"dependência {source_name} → {target_name}")

    protected_relation = detail.get("protected_relation")
    if protected_relation:
        producer, consumer = protected_relation
        producer_name = inline_code(producer)
        consumer_name = inline_code(consumer)
        qualifiers.append(f"relação protegida {producer_name} → {consumer_name}")

    action = detail.get("action")
    if action:
        action_name = inline_code(action)
        qualifiers.append(f"action {action_name}")

    artifact = detail.get("artifact")
    if artifact:
        artifact_name = inline_code(artifact)
        qualifiers.append(f"artefato {artifact_name}")

    reference = detail.get("reference")
    if reference:
        qualifiers.append(f"referência {inline_code(reference)}")

    if qualifiers:
        qualifier_text = ", ".join(qualifiers)
        return f"- {description} ({qualifier_text})"

    return f"- {description}"


def coverage_lines(snapshots: list[tuple[str, dict]]) -> list[str]:
    lines = []
    coverage_started = False

    for label, analysis in snapshots:
        coverage = analysis.get("coverage")
        if not coverage:
            continue

        if not coverage_started:
            lines.extend(["", "## Cobertura da análise", ""])
            coverage_started = True

        if len(snapshots) > 1:
            lines.extend([f"### Cobertura {label.lower()}", ""])

        lines.extend([
            "| Análise | Situação | Escopo | Motivos |",
            "|---|---|---|---|",
        ])
        detail_lines = []

        for record in coverage:
            name = COVERAGE_NAMES.get(record["analysis"], record["analysis"])
            state = COVERAGE_STATES.get(record["status"], record["status"])
            reasons = " / ".join(record["reasons"])
            if not reasons:
                reasons = "—"

            values = [name, state, record["scope"], reasons]
            safe_values = []
            for value in values:
                safe_values.append(safe_cell(value))
            row = "| " + " | ".join(safe_values) + " |"
            lines.append(row)

            if record["details"]:
                detail_lines.extend([f"**{safe_cell(name)}**", ""])
                for detail in record["details"]:
                    detail_lines.append(coverage_detail_line(detail))
                detail_lines.append("")

        lines.append("")
        if detail_lines:
            lines.extend(["<details>", "<summary>Detalhes da cobertura</summary>", ""])
            lines.extend(detail_lines)
            lines.extend(["</details>", ""])

    return lines


def unordered_pair_lines(analysis: dict) -> list[str]:
    unordered_pairs = analysis["structurally_unordered_pairs"]
    lines = [
        "",
        "## Pares sem ordem imposta por needs",
        "",
        f"Pares identificados **{len(unordered_pairs)}**.",
        "",
    ]

    for first_job, second_job in unordered_pairs:
        first_name = inline_code(first_job)
        second_name = inline_code(second_job)
        lines.append(f"- {first_name} e {second_name}")

    lines.extend([
        "",
        "Esses pares descrevem a ordem estrutural do grafo.",
    ])
    return lines


def assumption_lines(report: dict, snapshots: list[tuple[str, dict]]) -> list[str]:
    lines = ["", "## Premissas e limites", ""]

    for assumption in report["assumptions"]:
        lines.append(f"- {safe_cell(assumption)}")

    for label, analysis in snapshots:
        for limitation in analysis["limitations"]:
            lines.append(f"- **{label}** {safe_cell(limitation)}")

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
        lines.extend(step_change_lines(report.get("step_changes", [])))
        lines.extend(impact_link_lines(report))
        findings_title = "## Alertas e oportunidades da versão modificada"
        snapshots = [
            ("Antes", report["before"]),
            ("Depois", report["after"]),
        ]

    lines.extend(["", findings_title, ""])
    lines.extend(finding_lines(analysis["findings"]))
    lines.extend(coverage_lines(snapshots))
    lines.extend(unordered_pair_lines(analysis))
    lines.extend(assumption_lines(report, snapshots))

    rendered_text = "\n".join(lines)
    return rendered_text + "\n"
