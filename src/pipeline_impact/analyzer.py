from __future__ import annotations

from hashlib import sha256
from itertools import combinations
import json
import re

from . import __version__
from .conditions import states
from .event_context import event_eligibility
from .model import Workflow
from .step_comparison import compare_job_steps


SCHEMA_VERSION = "0.4"
OUTPUT_REF = re.compile(
    r"needs\.([A-Za-z_][A-Za-z0-9_-]*)\.outputs\.([A-Za-z_][A-Za-z0-9_-]*)"
)


def finding(
    rule,
    kind,
    jobs,
    evidence,
    *,
    artifact=None,
    context=None,
    suggestion=None,
    location=None,
):
    identifier_data = {
        "rule": rule,
        "jobs": jobs,
        "artifact": artifact,
        "context": context,
        "evidence": evidence,
    }
    identifier_text = json.dumps(identifier_data, sort_keys=True)
    identifier_bytes = identifier_text.encode()
    identifier_hash = sha256(identifier_bytes).hexdigest()
    finding_id = identifier_hash[:16]

    return {
        "id": finding_id,
        "rule": rule,
        "kind": kind,
        "jobs": jobs,
        "artifact": artifact,
        "context": context,
        "evidence": evidence,
        "suggestion": suggestion,
        "location": location,
    }


def coverage_detail(result, message, *, location=None, context=None):
    detail = {"result": result, "message": message}
    if location is not None:
        detail["location"] = location
    if context is not None:
        detail["context"] = context
    return detail


def coverage_entry(analysis, scope, status, reasons, details):
    return {
        "analysis": analysis,
        "scope": scope,
        "status": status,
        "reasons": reasons,
        "details": details,
    }


def artifact_steps(workflow, observations=None):
    uploads = []
    downloads = []
    limitations = []

    if observations is None:
        observations = []

    for job, data in workflow.jobs.items():
        if workflow.unresolved_job(job):
            observations.append(coverage_detail(
                "unresolved_job",
                "O reconhecimento de artefatos não examina os steps deste job.",
                location={"job": job},
            ))
            continue

        for index, step in enumerate(data["steps"]):
            if "uses" not in step:
                continue

            location = {"job": job, "step": index + 1}
            uses = step["uses"]
            if not isinstance(uses, str):
                observations.append(coverage_detail(
                    "invalid_action_reference",
                    "A referência à action não é um texto.",
                    location=location,
                ))
                continue

            action_parts = uses.split("@")
            action = action_parts[0].lower()
            supported_actions = ("actions/upload-artifact", "actions/download-artifact")
            if action not in supported_actions:
                observation = coverage_detail(
                    "unrecognized_action",
                    "Esta action está fora do reconhecimento de transferências de artefatos.",
                    location=location,
                )
                if re.fullmatch(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+", action):
                    observation["action"] = action
                observations.append(observation)
                continue

            params = step.get("with", {})
            is_upload = action.endswith("/upload-artifact")

            if is_upload:
                name = params.get("name", "artifact")
            else:
                name = params.get("name", None)

            unsupported_selector = False
            if not isinstance(name, str):
                unsupported_selector = True
            elif not name.strip():
                unsupported_selector = True
            elif "${{" in name:
                unsupported_selector = True

            selector_keys = ("pattern", "run-id", "repository", "github-token")
            for key in selector_keys:
                if key in params:
                    unsupported_selector = True
                    break

            if unsupported_selector:
                limitations.append(
                    f"Job {job}, step {index + 1}: seletor de artefato dinâmico, múltiplo ou externo."
                )
                observations.append(coverage_detail(
                    "unsupported_selector",
                    "O seletor está fora do modelo de nomes literais individuais.",
                    location=location,
                ))
                continue

            record = {
                "job": job,
                "step": index,
                "name": name,
                "condition": step["if"],
            }

            if is_upload:
                uploads.append(record)
                observation = coverage_detail(
                    "recognized_upload",
                    "Upload reconhecido pelo nome literal do artefato.",
                    location=location,
                )
            else:
                downloads.append(record)
                observation = coverage_detail(
                    "recognized_download",
                    "Download reconhecido pelo nome literal do artefato.",
                    location=location,
                )

            observation["artifact"] = name
            observations.append(observation)

    return uploads, downloads, limitations


def precedes(workflow, producer, consumer):
    if producer["job"] == consumer["job"]:
        return producer["step"] < consumer["step"]

    consumer_ancestors = workflow.ancestors(consumer["job"])
    return producer["job"] in consumer_ancestors


def snapshot(workflow: Workflow, contexts=None) -> dict:
    artifact_observations = []
    uploads, downloads, artifact_limits = artifact_steps(workflow, artifact_observations)
    limits = list(workflow.limitations)
    limits.extend(artifact_limits)
    findings = []
    data_pairs = set()
    supported_contexts = []
    context_evaluations = []
    coverage = []
    artifact_scan_incomplete = False
    recognition_status = "executed"
    recognition_reasons = ["A leitura examina as actions oficiais de upload e download por nome literal."]

    for observation in artifact_observations:
        result = observation["result"]
        if result == "unrecognized_action":
            recognition_status = "partial"
        elif result in ("unresolved_job", "unsupported_selector", "invalid_action_reference"):
            recognition_status = "partial"
            artifact_scan_incomplete = True

    if recognition_status == "partial":
        recognition_reasons.append("Há jobs, actions ou seletores fora do reconhecimento.")

    coverage.append(coverage_entry(
        "artifact_recognition",
        "Transferências por actions oficiais e nomes literais individuais.",
        recognition_status,
        recognition_reasons,
        artifact_observations,
    ))


    by_lower = {}
    for job in workflow.jobs:
        by_lower[job.lower()] = job

    for target, data in workflow.jobs.items():
        job_text = json.dumps(data)
        output_references = OUTPUT_REF.findall(job_text)

        for source, output_name in output_references:
            source = by_lower.get(source.lower(), source)
            data_pairs.add((source, target))

    unresolved_jobs = set()
    for job in workflow.jobs:
        if workflow.unresolved_job(job):
            unresolved_jobs.add(job)


    order_details = []
    checked_consumer_order = False
    for consumer in downloads:
        location = {"job": consumer["job"], "step": consumer["step"] + 1}
        producers = []
        for producer in uploads:
            if producer["name"] == consumer["name"]:
                producers.append(producer)

        for producer in producers:
            data_pairs.add((producer["job"], consumer["job"]))

        ordered_producers = []
        for producer in producers:
            if precedes(workflow, producer, consumer):
                ordered_producers.append(producer)

        if consumer["job"] in unresolved_jobs:
            continue
        if workflow.jobs[consumer["job"]]["if"] == "false":
            order_details.append(coverage_detail(
                "consumer_skipped",
                "A condição literal false do job exclui o consumidor desta verificação.",
                location=location,
            ))
            continue
        if consumer["condition"] == "false":
            order_details.append(coverage_detail(
                "consumer_skipped",
                "A condição literal false do step exclui o consumidor desta verificação.",
                location=location,
            ))
            continue

        checked_consumer_order = True
        if not ordered_producers:
            involved_jobs = {consumer["job"]}
            producer_jobs = set()
            for producer in producers:
                involved_jobs.add(producer["job"])
                producer_jobs.add(producer["job"])

            evidence = {
                "consumer_step": consumer["step"] + 1,
                "producer_jobs": sorted(producer_jobs),
                "reason": "Não há upload de mesmo nome com precedência garantida no modelo local.",
            }
            artifact_finding = finding(
                "R02_ARTIFACT_ORDER",
                "warning",
                sorted(involved_jobs),
                evidence,
                artifact=consumer["name"],
                suggestion="Verificar o produtor, o nome do artefato e a ordem necessária antes do download.",
                location=location,
            )
            findings.append(artifact_finding)
            order_details.append(coverage_detail(
                "warning",
                "O consumidor não tem upload reconhecido com precedência garantida.",
                location=location,
            ))
        else:
            order_details.append(coverage_detail(
                "ordered",
                "Há pelo menos um upload reconhecido com precedência estrutural.",
                location=location,
            ))

    order_status = "executed"
    order_reasons = ["A precedência foi examinada para os consumidores incluídos no modelo."]
    if artifact_scan_incomplete:
        order_status = "partial"
        order_reasons = ["A verificação usa as relações que o reconhecimento de artefatos conseguiu representar."]
    elif not checked_consumer_order:
        order_status = "not_applicable"
        order_reasons = ["Não há consumidores reconhecidos sujeitos à verificação de ordem."]

    coverage.append(coverage_entry(
        "R02_ARTIFACT_ORDER",
        "Precedência entre uploads e downloads reconhecidos.",
        order_status,
        order_reasons,
        order_details,
    ))

    condition_details = []
    condition_analysis_partial = artifact_scan_incomplete
    triggers = workflow.raw["on"]
    indeterminate_event = False

    if contexts is not None:
        for context in contexts:
            eligible, reason = event_eligibility(triggers, context)
            evaluation = {"context": context, "reason": reason, "step_states": {}}
            context_evaluations.append(evaluation)

            if eligible is None:
                evaluation["event_status"] = "indeterminate"
                indeterminate_event = True
                limits.append(reason)
                condition_details.append(coverage_detail(
                    "context_indeterminate", reason, context=context
                ))
                continue

            if eligible is False:
                evaluation["event_status"] = "excluded"
                condition_details.append(coverage_detail(
                    "context_excluded", reason, context=context
                ))
                continue

            evaluation["event_status"] = "eligible"
            supported_contexts.append(context)
            active_steps, state_limits = states(workflow, context)
            limits.extend(state_limits)
            condition_details.append(coverage_detail(
                "context_examined",
                "Estados de steps avaliados sob a premissa de sucesso.",
                context=context,
            ))

            if state_limits:
                condition_analysis_partial = True
                condition_details.append(coverage_detail(
                    "unsupported_condition",
                    "Há expressões fora do subconjunto interpretado.",
                    context=context,
                ))

            for step_key, step_state in active_steps.items():
                job, index = step_key
                job_step_states = evaluation["step_states"].setdefault(job, [])
                job_step_states.append(step_state)
                if step_state is None:
                    condition_analysis_partial = True
                    condition_details.append(coverage_detail(
                        "indeterminate_step",
                        "O estado deste step ficou indeterminado no cenário.",
                        location={"job": job, "step": index + 1},
                        context=context,
                    ))

            for consumer in downloads:
                consumer_key = (consumer["job"], consumer["step"])
                location = {"job": consumer["job"], "step": consumer["step"] + 1}
                consumer_state = active_steps.get(consumer_key)
                if consumer_state is not True:
                    if consumer_state is False:
                        condition_details.append(coverage_detail(
                            "consumer_skipped",
                            "O consumidor está desativado no cenário modelado.",
                            location=location,
                            context=context,
                        ))
                    continue

                ordered_producers = []
                for producer in uploads:
                    if producer["name"] == consumer["name"]:
                        if precedes(workflow, producer, consumer):
                            ordered_producers.append(producer)

                if not ordered_producers:
                    condition_details.append(coverage_detail(
                        "no_ordered_producer",
                        "A verificação condicional requer um upload reconhecido com precedência estrutural.",
                        location=location,
                        context=context,
                    ))
                    continue

                producer_states = []
                for producer in ordered_producers:
                    producer_key = (producer["job"], producer["step"])
                    producer_states.append(active_steps[producer_key])

                all_producers_skipped = True
                for producer_state in producer_states:
                    if producer_state is not False:
                        all_producers_skipped = False
                        break

                if all_producers_skipped:
                    involved_jobs = {consumer["job"]}
                    producer_steps = []
                    for producer in ordered_producers:
                        involved_jobs.add(producer["job"])
                        producer_steps.append({
                            "job": producer["job"],
                            "step": producer["step"] + 1,
                        })

                    evidence = {
                        "consumer_step": consumer["step"] + 1,
                        "producer_steps": producer_steps,
                        "reason": "Download ativo e todos os uploads anteriores de mesmo nome pulados no contexto modelado.",
                    }
                    condition_finding = finding(
                        "R03_ARTIFACT_CONDITION",
                        "warning",
                        sorted(involved_jobs),
                        evidence,
                        artifact=consumer["name"],
                        context=context,
                        suggestion="Alinhar as condições de produção e consumo, ou definir consumo opcional explicitamente.",
                        location=location,
                    )
                    findings.append(condition_finding)
                elif True not in producer_states:
                    condition_analysis_partial = True
                    limits.append(
                        f"Artefato {consumer['name']}: disponibilidade indeterminada no contexto {context}."
                    )
                    condition_details.append(coverage_detail(
                        "producer_indeterminate",
                        "A disponibilidade modelada do artefato ficou indeterminada.",
                        location=location,
                        context=context,
                    ))

    condition_status = "executed"
    condition_reasons = ["Os cenários compatíveis foram examinados sob a premissa de sucesso."]
    if not contexts:
        condition_status = "suspended"
        condition_reasons = ["A avaliação condicional requer pelo menos um contexto informado."]
    elif not supported_contexts and indeterminate_event:
        condition_status = "suspended"
        condition_reasons = ["A compatibilidade dos contextos com os gatilhos ficou indeterminada."]
    elif not supported_contexts:
        condition_status = "not_applicable"
        condition_reasons = ["Os gatilhos excluem todos os contextos informados."]
    elif condition_analysis_partial or indeterminate_event:
        condition_status = "partial"
        condition_reasons = ["Há estados, condições ou relações de artefatos que o modelo não conseguiu representar."]
    elif not downloads:
        condition_status = "not_applicable"
        condition_reasons = ["Os estados foram calculados, mas não há consumidores de artefatos reconhecidos."]

    coverage.append(coverage_entry(
        "R03_ARTIFACT_CONDITION",
        "Disponibilidade modelada de artefatos nos contextos informados.",
        condition_status,
        condition_reasons,
        condition_details,
    ))

    has_concurrency = "concurrency" in workflow.raw
    if not has_concurrency:
        for job_data in workflow.jobs.values():
            if "concurrency" in job_data:
                has_concurrency = True
                break


    can_review_parallelism = True
    parallel_reasons = []
    parallel_details = []
    if unresolved_jobs:
        can_review_parallelism = False
        job_names = ", ".join(sorted(unresolved_jobs))
        parallel_reasons.append(f"Jobs fora do modelo: {job_names}.")
    if artifact_limits:
        can_review_parallelism = False
        parallel_reasons.append("Há seletores de artefatos fora do modelo.")
    if has_concurrency:
        can_review_parallelism = False
        parallel_reasons.append("A presença de concurrency suspende a revisão de dependências.")

    if can_review_parallelism:
        for source, target in sorted(workflow.edges):
            edges_without_dependency = workflow.edges.copy()
            edges_without_dependency.remove((source, target))

            remaining_ancestors = workflow.ancestors(target, edges_without_dependency)
            if source in remaining_ancestors:
                detail = coverage_detail(
                    "order_preserved",
                    "Outro caminho mantém a mesma ordem após a remoção hipotética.",
                )
                detail["edge"] = [source, target]
                parallel_details.append(detail)
                continue

            breaks_data_relation = False
            for producer_job, consumer_job in sorted(data_pairs):
                if producer_job not in workflow.jobs:
                    continue
                if consumer_job not in workflow.jobs:
                    continue
                if producer_job == consumer_job:
                    continue

                original_ancestors = workflow.ancestors(consumer_job)
                if producer_job not in original_ancestors:
                    continue

                modified_ancestors = workflow.ancestors(
                    consumer_job,
                    edges_without_dependency,
                )
                if producer_job not in modified_ancestors:
                    breaks_data_relation = True
                    detail = coverage_detail(
                        "data_relation_protected",
                        "A remoção rompe a precedência de uma relação de dados reconhecida.",
                    )
                    detail["edge"] = [source, target]
                    detail["protected_relation"] = [producer_job, consumer_job]
                    parallel_details.append(detail)
                    break

            if breaks_data_relation:
                continue

            evidence = {
                "edge": [source, target],
                "reason": "Remover esta dependência altera a ordem; nenhuma relação de dados reconhecida exige a aresta.",
            }
            parallel_finding = finding(
                "R05_PARALLEL_REVIEW",
                "opportunity",
                [source, target],
                evidence,
                suggestion="Revisar possível paralelismo. Confirmar efeitos externos, recursos compartilhados e proteção contra falhas antes de remover a dependência.",
                location={"job": target, "field": "needs"},
            )
            findings.append(parallel_finding)
            detail = coverage_detail(
                "review_suggested",
                "A remoção mudaria a ordem e preservaria as precedências das relações de dados reconhecidas.",
            )
            detail["edge"] = [source, target]
            parallel_details.append(detail)

    if not can_review_parallelism:
        parallel_status = "suspended"
    elif not parallel_details:
        parallel_status = "not_applicable"
        parallel_reasons.append("Não há dependências diretas a examinar.")
    else:
        parallel_status = "executed"
        parallel_reasons.append("As dependências diretas foram examinadas uma por vez.")

    coverage.append(coverage_entry(
        "R05_PARALLEL_REVIEW",
        "Remoção hipotética de arestas e precedência das relações de dados reconhecidas.",
        parallel_status,
        parallel_reasons,
        parallel_details,
    ))

    eligible_pairs = []
    for first_job, second_job in combinations(sorted(workflow.jobs), 2):
        second_ancestors = workflow.ancestors(second_job)
        if first_job in second_ancestors:
            continue

        first_ancestors = workflow.ancestors(first_job)
        if second_job in first_ancestors:
            continue

        eligible_pairs.append([first_job, second_job])

    edge_records = []
    for source, target in sorted(workflow.edges):
        edge_records.append([source, target])

    data_relation_records = []
    for producer_job, consumer_job in sorted(data_pairs):
        data_relation_records.append([producer_job, consumer_job])

    return {
        "source": workflow.source,
        "jobs": sorted(workflow.jobs),
        "edges": edge_records,
        "data_relations": data_relation_records,
        "structurally_unordered_pairs": eligible_pairs,
        "contexts_checked": supported_contexts,
        "context_evaluations": context_evaluations,
        "findings": findings,
        "limitations": sorted(set(limits)),
        "coverage": coverage,
    }


def analysis_assumptions():
    return [
        "Análise estática experimental; nenhum comando ou action foi executado.",
        "Condições verificadas somente nos contextos listados, supondo sucesso dos comandos/actions executados, sem falhas ou cancelamento.",
        "Upload executado não garante existência de arquivos; produtores alternativos e dependências externas podem não estar representados.",
        "Pares sem ordem estrutural não comprovam independência nem paralelismo observado.",
        "Oportunidades exigem revisão e execução experimental; não há estimativa de economia ou garantia de segurança.",
        "Sem histórico de execução nesta versão; nenhuma conclusão de eficácia da pesquisa foi medida.",
    ]


def audit(workflow: Workflow, contexts=None) -> dict:
    analysis = snapshot(workflow, contexts)
    summary = {"warning": 0, "opportunity": 0}

    for current_finding in analysis["findings"]:
        kind = current_finding["kind"]
        summary[kind] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "mode": "audit",
        "analysis": analysis,
        "summary": summary,
        "assumptions": analysis_assumptions(),
    }


def step_state_in_context(evaluation, job, position):
    if evaluation["event_status"] == "excluded":
        return "event_excluded"
    if evaluation["event_status"] == "indeterminate":
        return "indeterminate"

    job_states = evaluation["step_states"].get(job, [])
    index = position - 1
    if index >= len(job_states):
        return "indeterminate"
    if job_states[index] is True:
        return "active"
    if job_states[index] is False:
        return "skipped"
    return "indeterminate"


def compare(before: Workflow, after: Workflow, contexts=None) -> dict:
    changes = []
    step_changes = []

    all_jobs = set(before.jobs)
    all_jobs.update(after.jobs)

    for job in sorted(all_jobs):
        old_job = before.jobs.get(job)
        new_job = after.jobs.get(job)


        downstream_jobs = set()
        if old_job:
            downstream_jobs.update(before.descendants(job))
        if new_job:
            downstream_jobs.update(after.descendants(job))
        downstream = sorted(downstream_jobs)

        if old_job is None or new_job is None:
            if old_job is None:
                change_type = "added"
            else:
                change_type = "removed"

            changes.append({
                "rule": "R01_JOB_CHANGE",
                "job": job,
                "change": change_type,
                "affected_jobs": downstream,
            })
            continue

        tracked_fields = (
            ("needs", "R01_DEPENDENCY_CHANGE"),
            ("if", "R04_CONDITION_CHANGE"),
            ("continue-on-error", "R04_FAILURE_POLICY_CHANGE"),
            ("steps", "STEP_CHANGE"),
            ("outputs", "OUTPUT_CHANGE"),
        )

        for field, rule in tracked_fields:
            before_value = old_job.get(field)
            after_value = new_job.get(field)

            if field == "needs":
                before_value = sorted(before_value)
                after_value = sorted(after_value)

            if before_value != after_value:
                change = {
                    "rule": rule,
                    "job": job,
                    "field": field,
                    "affected_jobs": downstream,
                }
                if field in ("needs", "if", "continue-on-error"):
                    change["before"] = before_value
                    change["after"] = after_value

                changes.append(change)

        if old_job["steps"] != new_job["steps"]:
            sequential = not before.unresolved_job(job) and not after.unresolved_job(job)
            job_step_changes = compare_job_steps(
                job, old_job["steps"], new_job["steps"], sequential=sequential
            )
            step_changes.extend(job_step_changes)

        before_ancestors = before.ancestors(job)
        after_ancestors = after.ancestors(job)
        if before_ancestors != after_ancestors:
            changes.append({
                "rule": "R01_REACHABILITY_CHANGE",
                "job": job,
                "before": sorted(before_ancestors),
                "after": sorted(after_ancestors),
                "affected_jobs": downstream,
            })

        modeled_fields = {"needs", "if", "continue-on-error", "steps", "outputs", "name"}
        all_job_fields = set(old_job)
        all_job_fields.update(new_job)
        unmodeled_fields = all_job_fields.difference(modeled_fields)

        for field in sorted(unmodeled_fields):
            if old_job.get(field) != new_job.get(field):
                changes.append({
                    "rule": "UNMODELED_JOB_CHANGE",
                    "job": job,
                    "field": field,
                    "affected_jobs": downstream,
                })

    if before.raw.get("on") != after.raw.get("on"):
        changes.append({
            "rule": "TRIGGER_CHANGE",
            "affected_jobs": sorted(after.jobs),
        })

    all_workflow_fields = set(before.raw)
    all_workflow_fields.update(after.raw)
    presentation_or_modeled_fields = {"on", "jobs", "name", "run-name"}
    unmodeled_workflow_fields = all_workflow_fields.difference(
        presentation_or_modeled_fields
    )

    for field in sorted(unmodeled_workflow_fields):
        if before.raw.get(field) != after.raw.get(field):
            changes.append({
                "rule": "UNMODELED_WORKFLOW_CHANGE",
                "field": field,
                "affected_jobs": sorted(after.jobs),
            })

    before_snapshot = snapshot(before, contexts)
    after_snapshot = snapshot(after, contexts)

    for step_change in step_changes:
        if "if" not in step_change["fields"]:
            continue

        job = step_change["job"]
        before_position = step_change["before_step"]
        after_position = step_change["after_step"]
        context_comparisons = []
        context_pairs = zip(
            before_snapshot["context_evaluations"], after_snapshot["context_evaluations"]
        )
        for before_evaluation, after_evaluation in context_pairs:
            before_state = step_state_in_context(before_evaluation, job, before_position)
            after_state = step_state_in_context(after_evaluation, job, after_position)
            context_comparisons.append({
                "context": before_evaluation["context"],
                "before": before_state,
                "after": after_state,
            })
        step_change["context_comparisons"] = context_comparisons

    summary = {"changes": len(changes)}
    for current_finding in after_snapshot["findings"]:
        kind = current_finding["kind"]
        if kind not in summary:
            summary[kind] = 0
        summary[kind] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": __version__,
        "mode": "compare",
        "before": before_snapshot,
        "after": after_snapshot,
        "changes": changes,
        "step_changes": step_changes,
        "summary": summary,
        "assumptions": analysis_assumptions(),
    }
