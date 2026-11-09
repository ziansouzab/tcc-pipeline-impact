from __future__ import annotations

from hashlib import sha256
from itertools import combinations
import json
import re

from .conditions import states
from .model import Workflow


CONTEXTS = [
    {"github.event_name": "push", "github.ref": "refs/heads/main"},
    {"github.event_name": "push", "github.ref": "refs/heads/feature"},
    {"github.event_name": "pull_request", "github.ref": "refs/pull/1/merge"},
]
OUTPUT_REF = re.compile(
    r"needs\.([A-Za-z_][A-Za-z0-9_-]*)\.outputs\.([A-Za-z_][A-Za-z0-9_-]*)"
)


def snapshot(workflow: Workflow) -> dict:
    edge_records = []
    for source, target in sorted(workflow.edges):
        edge_records.append([source, target])

    return {
        "source": workflow.source,
        "jobs": sorted(workflow.jobs),
        "edges": edge_records,
        "data_relations": [],
        "structurally_unordered_pairs": [],
        "contexts_checked": [],
        "findings": [],
        "limitations": sorted(set(workflow.limitations)),
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
        "schema_version": "0.2",
        "tool_version": "0.1.0",
        "before": before_snapshot,
        "after": after_snapshot,
        "changes": changes,
        "summary": summary,
        "assumptions": [
            "Análise estática experimental; nenhum comando ou action foi executado.",
            "Condições verificadas somente nos contextos listados, supondo sucesso dos comandos/actions executados, sem falhas ou cancelamento.",
            "Upload executado não garante existência de arquivos; produtores alternativos e dependências externas podem não estar representados.",
            "Pares sem ordem estrutural não comprovam independência nem paralelismo observado.",
            "Oportunidades exigem revisão e execução experimental; não há estimativa de economia ou garantia de segurança.",
            "Sem histórico de execução nesta versão; nenhuma conclusão de eficácia da pesquisa foi medida.",
        ],
    }
