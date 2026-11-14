from __future__ import annotations

from copy import copy

from .conditions import states
from .needs_references import job_needs_references
from .step_comparison import pair_job_steps


def precedes(workflow, producer, consumer, edges=None):
    if producer["job"] == consumer["job"]:
        return producer["step"] < consumer["step"]

    consumer_ancestors = workflow.ancestors(consumer["job"], edges)
    return producer["job"] in consumer_ancestors


def matched_steps(before, after):
    positions = {}
    for job, current in after.jobs.items():
        if job not in before.jobs:
            continue
        matching = pair_job_steps(before.jobs[job]["steps"], current["steps"])
        for before_index, after_index in matching["pairs"].items():
            positions[(job, after_index + 1)] = before_index + 1
    return positions


def removed_dependencies(changes):
    removed = {}
    for index, change in enumerate(changes):
        if change["rule"] != "R01_DEPENDENCY_CHANGE":
            continue
        for producer in change["before"]:
            if producer not in change["after"]:
                removed[(producer, change["job"])] = index
    return removed


def artifact_positions(artifacts):
    positions = {}
    for artifact in artifacts:
        key = (artifact["job"], artifact["step"] + 1, artifact["name"])
        positions[key] = artifact
    return positions


def previous_artifact(artifact, previous_positions, step_pairs):
    job = artifact["job"]
    previous_step = step_pairs.get((job, artifact["step"] + 1))
    return previous_positions.get((job, previous_step, artifact["name"]))


def make_impact_link(impact_type, change_index, finding, evidence):
    return {
        "type": impact_type,
        "change_index": change_index,
        "finding_id": finding["id"],
        "location": finding["location"],
        "evidence": evidence,
    }


def order_loss_links(before, after, before_artifacts, after_artifacts, finding, removed, step_pairs):
    before_uploads, before_downloads = before_artifacts
    after_uploads, after_downloads = after_artifacts
    location = finding["location"]
    consumer_job = location["job"]
    artifact_name = finding["artifact"]
    consumer_key = (consumer_job, location["step"], artifact_name)
    consumer = after_downloads[consumer_key]
    old_consumer = previous_artifact(consumer, before_downloads, step_pairs)
    if old_consumer is None:
        return []
    if old_consumer["condition"] == "false" or before.jobs[consumer_job]["if"] == "false":
        return []

    producers = []
    for producer in after_uploads.values():
        if producer["name"] != artifact_name or producer["job"] == consumer_job:
            continue
        old_producer = previous_artifact(producer, before_uploads, step_pairs)
        if old_producer is not None and precedes(before, old_producer, old_consumer):
            producers.append(producer)

    if not producers:
        return []

    links = []
    for edge, change_index in removed.items():
        source, target = edge
        if source not in after.jobs:
            continue
        if target in after.ancestors(source):
            continue
        restored_edges = after.edges
        restored_edges.add(edge)
        for producer in producers:
            if not precedes(after, producer, consumer, restored_edges):
                continue
            evidence = {
                "artifact": artifact_name,
                "producer_job": producer["job"],
                "consumer_job": consumer_job,
                "removed_edge": list(edge),
                "precedence_before": True,
                "precedence_after": False,
                "precedence_with_restored_edge": True,
            }
            links.append(make_impact_link("artifact_order_lost", change_index, finding, evidence))
            break
    return links


def direct_needs_loss_link(before, after, finding, removed, step_pairs):
    location = finding["location"]
    consumer = location["job"]
    producer = finding["evidence"]["producer_job"]
    change_index = removed.get((producer, consumer))
    if change_index is None or producer not in after.jobs:
        return None
    if consumer in after.ancestors(producer):
        return None

    after_step = location.get("step")
    before_step = None
    if after_step is not None:
        before_step = step_pairs.get((consumer, after_step))
        if before_step is None:
            return None

    field = location["field"]
    reference = finding["evidence"]["reference"]
    previous_references = job_needs_references(before.jobs[consumer])
    for position, previous_field, _, previous_reference in previous_references:
        if position != before_step or previous_field != field:
            continue
        if previous_reference.lower() != reference.lower():
            continue

        evidence = {
            "producer_job": producer,
            "consumer_job": consumer,
            "reference": reference,
            "removed_edge": [producer, consumer],
            "order_preserved": producer in after.ancestors(consumer),
        }
        return make_impact_link("direct_needs_lost", change_index, finding, evidence)

    return None


def structural_impact_links(before, after, changes, findings, before_artifacts, after_artifacts, step_pairs):
    removed = removed_dependencies(changes)
    if not removed:
        return []

    links = []
    for finding in findings:
        rule = finding["rule"]
        if rule == "R02_ARTIFACT_ORDER":
            links.extend(order_loss_links(
                before, after, before_artifacts, after_artifacts, finding, removed, step_pairs
            ))
        elif rule == "R06_NEEDS_DIRECT_DEPENDENCY":
            link = direct_needs_loss_link(before, after, finding, removed, step_pairs)
            if link is not None:
                links.append(link)
    return links


def active_step(evaluation, job, position):
    job_states = evaluation["step_states"].get(job, [])
    return position <= len(job_states) and job_states[position - 1] is True


def states_with_restored_if(workflow, context, job, position, previous_if):
    restored_workflow = copy(workflow)
    restored_workflow.jobs = workflow.jobs.copy()
    restored_job = workflow.jobs[job].copy()
    restored_steps = list(restored_job["steps"])
    restored_step = restored_steps[position - 1].copy()
    restored_step["if"] = previous_if
    restored_steps[position - 1] = restored_step
    restored_job["steps"] = restored_steps
    restored_workflow.jobs[job] = restored_job
    restored_states, _ = states(restored_workflow, context)
    return restored_states


def eligible_evaluation_pairs(before_snapshot, after_snapshot):
    pairs = []
    evaluations = zip(before_snapshot["context_evaluations"], after_snapshot["context_evaluations"])
    for previous, current in evaluations:
        if previous["event_status"] == "eligible" and current["event_status"] == "eligible":
            pairs.append((previous, current))
    return pairs


def conditional_impact_links(
    before, after, changes, step_changes, before_snapshot, after_snapshot,
    before_artifacts, after_artifacts, step_pairs,
):
    before_uploads, before_downloads = before_artifacts
    after_uploads, after_downloads = after_artifacts
    evaluations = eligible_evaluation_pairs(before_snapshot, after_snapshot)
    if not evaluations:
        return []

    step_changes_by_job = {}
    for index, change in enumerate(changes):
        if change["rule"] == "STEP_CHANGE":
            step_changes_by_job[change["job"]] = index

    changed_conditions = {}
    for index, change in enumerate(step_changes):
        if "if" in change["fields"]:
            changed_conditions[(change["job"], change["after_step"])] = (index, change)

    links = []
    restored_states_by_step = {}
    for finding in after_snapshot["findings"]:
        if finding["rule"] != "R03_ARTIFACT_CONDITION":
            continue

        artifact_name = finding["artifact"]
        location = finding["location"]
        consumer_job = location["job"]
        consumer_step = location["step"]
        consumer = after_downloads[(consumer_job, consumer_step, artifact_name)]
        old_consumer = previous_artifact(consumer, before_downloads, step_pairs)
        if old_consumer is None:
            continue

        context = finding["context"]
        for evaluation_index, (previous, current) in enumerate(evaluations):
            if context != current["context"]:
                continue
            old_consumer_step = old_consumer["step"] + 1
            if not active_step(previous, consumer_job, old_consumer_step):
                continue
            if not active_step(current, consumer_job, consumer_step):
                continue

            for producer_location in finding["evidence"]["producer_steps"]:
                producer_job = producer_location["job"]
                producer_step = producer_location["step"]
                condition_change = changed_conditions.get((producer_job, producer_step))
                if condition_change is None:
                    continue

                step_change_index, step_change = condition_change
                producer = after_uploads[(producer_job, producer_step, artifact_name)]
                old_producer = previous_artifact(producer, before_uploads, step_pairs)
                if old_producer is None or not precedes(before, old_producer, old_consumer):
                    continue
                old_producer_step = old_producer["step"] + 1
                if old_producer_step != step_change["before_step"]:
                    continue
                if not active_step(previous, producer_job, old_producer_step):
                    continue

                cache_key = (evaluation_index, producer_job, producer_step)
                if cache_key not in restored_states_by_step:
                    previous_if = step_change["fields"]["if"]["before"]
                    restored_states_by_step[cache_key] = states_with_restored_if(
                        after, context, producer_job, producer_step, previous_if
                    )
                restored_states = restored_states_by_step[cache_key]
                if restored_states.get((producer_job, producer_step - 1)) is not True:
                    continue
                if restored_states.get((consumer_job, consumer_step - 1)) is not True:
                    continue

                evidence = {
                    "artifact": artifact_name,
                    "producer_job": producer_job,
                    "producer_step_before": old_producer_step,
                    "producer_step_after": producer_step,
                    "consumer_job": consumer_job,
                    "consumer_step_before": old_consumer_step,
                    "consumer_step_after": consumer_step,
                    "upload_state_before": "active",
                    "upload_state_after": "skipped",
                    "upload_state_with_restored_if": "active",
                }
                link = make_impact_link(
                    "upload_condition_changed", step_changes_by_job[producer_job], finding, evidence
                )
                link["step_change_index"] = step_change_index
                link["context"] = context
                links.append(link)
    return links
