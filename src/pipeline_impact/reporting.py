from __future__ import annotations

import html
import json


COVERAGE_NAMES = {
    "artifact_recognition": "Reconhecimento de artefatos",
    "condition_evaluation": "Avaliação de condições",
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
CONTEXT_STATES = {
    "active": "ativo",
    "skipped": "pulado",
    "eligible": "elegível",
    "event_excluded": "evento excluído",
    "excluded": "evento excluído",
    "indeterminate": "indeterminado",
}
CHANGE_TITLES = {
    "R01_DEPENDENCY_CHANGE": "Dependências diretas",
    "R01_REACHABILITY_CHANGE": "Ordem transitiva dos jobs",
    "R04_CONDITION_CHANGE": "Condição de execução",
    "R04_FAILURE_POLICY_CHANGE": "Política de falha",
    "STEP_CHANGE": "Configuração dos steps",
    "OUTPUT_CHANGE": "Declaração de outputs",
    "UNMODELED_JOB_CHANGE": "Configuração do job",
    "UNMODELED_WORKFLOW_CHANGE": "Configuração do workflow",
    "TRIGGER_CHANGE": "Gatilhos do workflow",
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


def overview_lines(report: dict, mode: str) -> list[str]:
    warnings = report["summary"].get("warning", 0)
    opportunities = report["summary"].get("opportunity", 0)
    version = inline_code(report["tool_version"])
    if mode == "audit":
        source = inline_code(report["analysis"]["source"])
        lines = ["# Auditoria da pipeline", "", f"Arquivo {source}."]
    else:
        lines = ["# Análise de impacto da pipeline"]

    lines.extend([
        "",
        f"Alertas: **{warnings}**. Oportunidades de revisão: **{opportunities}**.",
    ])
    if mode != "audit":
        changes = len(report["changes"])
        impacts = len(report.get("impact_links", []))
        lines.append(f"Mudanças identificadas: **{changes}**. Vínculos com alertas: **{impacts}**.")
    lines.extend(["", f"Protótipo {version}. Análise estática."])
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


def change_value_text(value) -> str:
    if value is None:
        return "sem valor explícito"
    if isinstance(value, list):
        if not value:
            return "nenhum"
        return names_as_code(value)
    if isinstance(value, bool):
        if value:
            return inline_code("true")
        return inline_code("false")
    return inline_code(value)


def context_comparison_lines(comparisons: list[dict]) -> list[str]:
    lines = []
    for comparison in comparisons:
        context = context_text(comparison["context"])
        before_state = comparison["before"]
        after_state = comparison["after"]
        before = CONTEXT_STATES.get(before_state, safe_cell(before_state))
        after = CONTEXT_STATES.get(after_state, safe_cell(after_state))
        lines.append(f"- Cenário {context}. **{before} → {after}**.")
    return lines


def explanation_lines(explanations: list[dict]) -> list[str]:
    lines = []
    for explanation in explanations:
        field = inline_code(explanation["field"])
        message = safe_cell(explanation["message"])
        status = explanation["status"]
        if status == "explained":
            label = "Efeito"
        elif status == "indeterminate":
            label = "Efeito indeterminado"
        else:
            label = "Alteração detectada"

        line = f"- **{label}** em {field}."
        if "before" in explanation and "after" in explanation:
            before = change_value_text(explanation["before"])
            after = change_value_text(explanation["after"])
            line += f" {before} → {after}."
        line += f" {message}"
        lines.append(line)
        lines.extend(context_comparison_lines(explanation.get("context_comparisons", [])))
    return lines


def change_lines(changes: list[dict]) -> list[str]:
    lines = ["", "## Mudanças e efeitos", ""]
    if not changes:
        lines.append("Nenhuma mudança nas propriedades acompanhadas.")

    for change in changes:
        rule = change["rule"]
        if rule == "R01_JOB_CHANGE":
            if change["change"] == "added":
                title = "Job adicionado"
            else:
                title = "Job removido"
        else:
            title = CHANGE_TITLES.get(rule, "Alteração de configuração")

        scope = "workflow"
        if "job" in change:
            scope = f"job {inline_code(change['job'])}"
        lines.extend([f"### {title} no {scope}", ""])

        explanations = change.get("explanations", [])
        if explanations:
            lines.extend(explanation_lines(explanations))
        elif "before" in change and "after" in change:
            before = change_value_text(change["before"])
            after = change_value_text(change["after"])
            lines.append(f"- {before} → {after}.")
        elif "field" in change:
            field = inline_code(change["field"])
            lines.append(f"- Campo alterado {field}.")

        affected_jobs = change["affected_jobs"]
        if affected_jobs:
            jobs = names_as_code(affected_jobs)
            if "job" in change:
                lines.append(f"- **Jobs posteriores no grafo** {jobs}.")
            else:
                lines.append(f"- **Jobs no escopo da configuração** {jobs}.")
        lines.append("")

    return lines


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

        explanations = change.get("explanations", [])
        explained_fields = set()
        fields_with_values = set()
        fields_with_context = set()
        for explanation in explanations:
            field = explanation["field"]
            explained_fields.add(field)
            if "before" in explanation and "after" in explanation:
                fields_with_values.add(field)
            if "context_comparisons" in explanation:
                fields_with_context.add(field)

        for field, values in change["fields"].items():
            if field in fields_with_values:
                continue
            before = change_value_text(values["before"])
            after = change_value_text(values["after"])
            lines.append(f"- {inline_code(field)} passou de {before} para {after}.")

        other_fields = []
        for field in change["other_fields"]:
            if field not in explained_fields:
                other_fields.append(field)
        if other_fields:
            names = names_as_code(other_fields)
            lines.append(f"- Outros campos alterados {names}.")

        lines.extend(explanation_lines(explanations))
        policy = change["fields"].get("continue-on-error")
        if policy is not None and "continue-on-error" not in explained_fields:
            if policy["before"] is False and policy["after"] is True:
                lines.append("- Se o step falhar, sua falha passa a ser tolerada na conclusão do job.")
            elif policy["before"] is True and policy["after"] is False:
                lines.append("- Se o step falhar, sua falha pode voltar a reprovar o job.")
            else:
                lines.append("- A tolerância à falha depende do valor configurado na execução.")

        if change["change"] == "unmatched":
            lines.append("- O modelo não encontrou uma correspondência única entre as versões.")

        if "context_comparisons" in change and "if" not in fields_with_context:
            context_comparisons = change["context_comparisons"]
            if not context_comparisons:
                lines.append("- A avaliação condicional requer contextos de evento.")
            lines.extend(context_comparison_lines(context_comparisons))
        lines.append("")
    return lines


def impact_link_text(link: dict) -> str:
    evidence = link["evidence"]
    if link["type"] == "upload_condition_changed":
        producer = inline_code(evidence["producer_job"])
        position = evidence["producer_step_after"]
        artifact = inline_code(evidence["artifact"])
        context = context_text(link["context"])
        return (
            f"Alterar o `if` do upload de {artifact} em {producer}, step {position}, "
            f"fez o upload passar de ativo para pulado no cenário {context}. "
            "Restaurar somente o `if` anterior reativa o upload no modelo e mantém o download ativo."
        )

    source, target = evidence["removed_edge"]
    source_text = inline_code(source)
    target_text = inline_code(target)
    if link["type"] == "artifact_order_lost":
        artifact = inline_code(evidence["artifact"])
        return (
            f"O download de {artifact} perdeu a precedência reconhecida. Restaurar "
            f"{source_text} em `needs` de {target_text} recupera a ordem no modelo."
        )

    reference = inline_code(evidence["reference"])
    effect = (
        f"Remover {source_text} do `needs` direto de {target_text} deixa "
        f"{reference} sem a entrada do produtor no contexto."
    )
    if evidence["order_preserved"]:
        effect += " A ordem entre os jobs permanece por um caminho indireto."
    return effect


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
        explanation = f"O job usa {reference}. {safe_cell(evidence['reason'])}"
        consequence = "O contexto needs do consumidor fica sem a entrada do job referenciado."
        return title, explanation, consequence

    return safe_cell(rule), safe_cell(evidence["reason"]), ""


def finding_brief(finding: dict) -> str:
    title, _, _ = finding_explanation(finding)
    location = finding.get("location")
    if location:
        where = location_text(location)
    else:
        where = names_as_code(finding["jobs"])
    brief = f"**{title}** em {where}."
    if finding.get("suggestion"):
        brief += f" {safe_cell(finding['suggestion'])}"
    return brief


def finding_lines(findings: list[dict], impact_links: dict) -> list[str]:
    lines = []
    for current_finding in findings:
        rule = inline_code(current_finding["rule"])
        title, explanation, consequence = finding_explanation(current_finding)
        lines.extend([f"### {title} ({rule})", ""])

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

        for link in impact_links.get(current_finding.get("id"), []):
            lines.extend([f"**Mudança associada** {impact_link_text(link)}", ""])

        lines.extend([f"**Evidência** {explanation}", ""])
        if consequence:
            lines.extend([f"**Consequência possível** {consequence}", ""])

        if current_finding["suggestion"]:
            suggestion = safe_cell(current_finding["suggestion"])
            lines.extend([f"**Revisão sugerida** {suggestion}", ""])

        context = current_finding["context"]
        if context:
            modeled_context = context_text(context)
            lines.extend([f"**Contexto modelado** {modeled_context}.", ""])

    return lines


def outcomes_lines(analysis: dict, links: list[dict]) -> list[str]:
    warnings = []
    opportunities = []
    for finding in analysis["findings"]:
        if finding["kind"] == "warning":
            warnings.append(finding)
        elif finding["kind"] == "opportunity":
            opportunities.append(finding)

    impacts = {}
    for link in links:
        impacts.setdefault(link["finding_id"], []).append(link)

    lines = ["", "## Alertas", ""]
    if warnings:
        lines.extend(finding_lines(warnings, impacts))
    else:
        lines.append("Nenhum alerta nas verificações aplicáveis ao escopo analisado.")
    lines.extend(["", "## Oportunidades de revisão", ""])
    if opportunities:
        lines.extend(finding_lines(opportunities, impacts))
    else:
        lines.append("Nenhuma oportunidade de revisão identificada.")
        for record in analysis.get("coverage", []):
            if record["analysis"] == "R05_PARALLEL_REVIEW":
                if record["status"] in ("not_applicable", "suspended", "partial"):
                    lines.extend(["", safe_cell(" ".join(record["reasons"]))])
                break
    return lines


def coverage_detail_line(detail: dict, steps: list[int]) -> str:
    description = safe_cell(detail["message"])
    qualifiers = []

    location = detail.get("location")
    if len(steps) > 1:
        job = inline_code(location["job"])
        step_numbers = names_as_code(steps)
        qualifiers.append(f"job {job}, steps {step_numbers} (posições na lista)")
    elif location:
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

    references = detail.get("references")
    if references:
        qualifiers.append(f"referências {names_as_code(references)}")

    if qualifiers:
        qualifier_text = ", ".join(qualifiers)
        return f"- {description} ({qualifier_text})"

    return f"- {description}"


def grouped_coverage_details(details: list[dict]) -> list[str]:
    grouped_details = []
    steps_by_signature = {}
    for detail in details:
        location = detail.get("location", {})
        step = location.get("step")
        if step is None:
            grouped_details.append((detail, []))
            continue

        group = detail.copy()
        signature_location = location.copy()
        del signature_location["step"]
        group["location"] = signature_location
        signature = json.dumps(group, sort_keys=True)
        steps = steps_by_signature.get(signature)
        if steps is None:
            steps = [step]
            steps_by_signature[signature] = steps
            grouped_details.append((detail, steps))
        elif step not in steps:
            steps.append(step)

    lines = []
    for detail, steps in grouped_details:
        lines.append(coverage_detail_line(detail, steps))
    return lines


def coverage_lines(snapshots: list[tuple[str, dict]]) -> list[str]:
    coverage_by_label = {}
    for label, analysis in snapshots:
        coverage = analysis.get("coverage")
        if coverage:
            coverage_by_label[label] = coverage
    if not coverage_by_label:
        return []

    lines = [
        "",
        "## Cobertura da análise",
        "",
        "<details>",
        "<summary>Ver verificações, cenários e limites</summary>",
        "",
    ]
    scope_groups = []
    if len(snapshots) > 1:
        before = coverage_by_label.get("Antes", [])
        after = coverage_by_label.get("Depois", [])
        shared = []
        before_only = []
        after_only = []
        for record in after:
            if record in before:
                shared.append(record)
            else:
                after_only.append(record)
        for record in before:
            if record not in after:
                before_only.append(record)
        scope_groups = [
            ("Na versão proposta", after_only),
            ("Na versão anterior", before_only),
            ("Nas duas versões", shared),
        ]
    else:
        scope_groups.append(("", coverage_by_label["Workflow"]))

    for label, coverage in scope_groups:
        if not coverage:
            continue
        if label:
            lines.extend([f"### {label}", ""])
        for record in coverage:
            name = safe_cell(COVERAGE_NAMES.get(record["analysis"], record["analysis"]))
            state = COVERAGE_STATES.get(record["status"], record["status"])
            reasons = safe_cell(" ".join(record["reasons"]))
            lines.extend([f"**{name} · {safe_cell(state)}**", "", reasons, ""])
            if record["details"]:
                lines.extend(grouped_coverage_details(record["details"]))
                lines.append("")

    lines.extend(["</details>", ""])
    return lines


def unordered_pair_lines(analysis: dict) -> list[str]:
    unordered_pairs = analysis["structurally_unordered_pairs"]
    if not unordered_pairs:
        return []
    lines = [
        "",
        "**Pares sem ordem imposta por needs**",
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


def graph_lines(analysis: dict, before: dict | None) -> list[str]:
    after_diagram = diagram(analysis)
    if before is None:
        return ["", "## Grafo de dependências", "", "```mermaid", after_diagram, "```"]

    before_diagram = diagram(before)
    if before_diagram == after_diagram:
        return [
            "",
            "## Grafo de dependências",
            "",
            "O grafo é igual nas duas versões.",
            "",
            "```mermaid",
            after_diagram,
            "```",
        ]
    return [
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
    ]


def assumption_lines(report: dict, snapshots: list[tuple[str, dict]]) -> list[str]:
    lines = [
        "",
        "<details>",
        "<summary>Premissas e limites gerais</summary>",
        "",
    ]

    for assumption in report["assumptions"]:
        lines.append(f"- {safe_cell(assumption)}")

    limitations = {}
    for label, analysis in snapshots:
        for limitation in analysis["limitations"]:
            limitations.setdefault(limitation, []).append(label)
    for limitation, labels in limitations.items():
        description = safe_cell(limitation)
        if len(snapshots) < 2:
            lines.append(f"- {description}")
        elif len(labels) == 1:
            lines.append(f"- **{labels[0]}** {description}")
        else:
            lines.append(f"- **Nas duas versões** {description}")

    lines.extend(["", "</details>"])
    return lines


def markdown(report: dict) -> str:
    mode = report.get("mode", "compare")
    lines = overview_lines(report, mode)

    if mode == "audit":
        analysis = report["analysis"]
        before = None
        snapshots = [("Workflow", analysis)]
    else:
        analysis = report["after"]
        before = report["before"]
        snapshots = [("Antes", before), ("Depois", analysis)]

    lines.extend(outcomes_lines(analysis, report.get("impact_links", [])))
    if mode != "audit":
        lines.extend(change_lines(report["changes"]))
        lines.extend(step_change_lines(report.get("step_changes", [])))
    lines.extend(graph_lines(analysis, before))
    lines.extend(unordered_pair_lines(analysis))
    lines.extend(coverage_lines(snapshots))
    lines.extend(assumption_lines(report, snapshots))

    rendered_text = "\n".join(lines)
    return rendered_text + "\n"
