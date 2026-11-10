from __future__ import annotations

from hashlib import sha256
from itertools import combinations
import json
import re

from . import __version__
from .conditions import states
from .model import Workflow


SCHEMA_VERSION = "0.3"
CONTEXTS = [
    {"github.event_name": "push", "github.ref": "refs/heads/main"},
    {"github.event_name": "push", "github.ref": "refs/heads/feature"},
    {"github.event_name": "pull_request", "github.ref": "refs/pull/1/merge"},
]
OUTPUT_REF = re.compile(
    r"needs\.([A-Za-z_][A-Za-z0-9_-]*)\.outputs\.([A-Za-z_][A-Za-z0-9_-]*)"
)


def finding(rule, kind, jobs, evidence, *, artifact=None, context=None, suggestion=None):
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
    }


def artifact_steps(workflow):
    uploads = []
    downloads = []
    limitations = []

    for job, data in workflow.jobs.items():
        if workflow.unresolved_job(job):
            continue

        for index, step in enumerate(data["steps"]):
            uses = step.get("uses", "")
            if not isinstance(uses, str):
                continue

            action_parts = uses.split("@")
            action = action_parts[0].lower()
            supported_actions = ("actions/upload-artifact", "actions/download-artifact")
            if action not in supported_actions:
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
                continue

            record = {
                "job": job,
                "step": index,
                "name": name,
                "condition": step["if"],
            }

            if is_upload:
                uploads.append(record)
            else:
                downloads.append(record)

    return uploads, downloads, limitations


def precedes(workflow, producer, consumer):
    if producer["job"] == consumer["job"]:
        return producer["step"] < consumer["step"]

    consumer_ancestors = workflow.ancestors(consumer["job"])
    return producer["job"] in consumer_ancestors


def snapshot(workflow: Workflow) -> dict:
    uploads, downloads, artifact_limits = artifact_steps(workflow)
    limits = list(workflow.limitations)
    limits.extend(artifact_limits)
    findings = []
    data_pairs = set()
    supported_contexts = []


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


    for consumer in downloads:
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
            continue
        if consumer["condition"] == "false":
            continue

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
            )
            findings.append(artifact_finding)


    triggers = workflow.raw["on"]
    if isinstance(triggers, (dict, list)):
        events = set(triggers)
    else:
        events = {triggers}

    filtered_events = False
    if isinstance(triggers, dict):
        for event_configuration in triggers.values():
            if event_configuration:
                filtered_events = True
                break


    if not filtered_events:
        for context in CONTEXTS:
            if context["github.event_name"] not in events:
                continue

            supported_contexts.append(context)
            active_steps, state_limits = states(workflow, context)
            limits.extend(state_limits)

            for consumer in downloads:
                consumer_key = (consumer["job"], consumer["step"])
                if active_steps.get(consumer_key) is not True:
                    continue

                ordered_producers = []
                for producer in uploads:
                    if producer["name"] == consumer["name"]:
                        if precedes(workflow, producer, consumer):
                            ordered_producers.append(producer)

                if not ordered_producers:

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
                    )
                    findings.append(condition_finding)
                elif True not in producer_states:
                    limits.append(
                        f"Artefato {consumer['name']}: disponibilidade indeterminada no contexto {context}."
                    )

    has_concurrency = "concurrency" in workflow.raw
    if not has_concurrency:
        for job_data in workflow.jobs.values():
            if "concurrency" in job_data:
                has_concurrency = True
                break


    can_review_parallelism = True
    if unresolved_jobs:
        can_review_parallelism = False
    if artifact_limits:
        can_review_parallelism = False
    if has_concurrency:
        can_review_parallelism = False

    if can_review_parallelism:
        for source, target in sorted(workflow.edges):
            edges_without_dependency = workflow.edges.copy()
            edges_without_dependency.remove((source, target))

            remaining_ancestors = workflow.ancestors(target, edges_without_dependency)
            if source in remaining_ancestors:

                continue

            breaks_data_relation = False
            for producer_job, consumer_job in data_pairs:
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
            )
            findings.append(parallel_finding)


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
        "findings": findings,
        "limitations": sorted(set(limits)),
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


def audit(workflow: Workflow) -> dict:
    analysis = snapshot(workflow)
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


def compare(before: Workflow, after: Workflow) -> dict:
    changes = []

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

    before_snapshot = snapshot(before)
    after_snapshot = snapshot(after)

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
        "summary": summary,
        "assumptions": analysis_assumptions(),
    }
