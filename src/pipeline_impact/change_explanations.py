from __future__ import annotations

import re

from .event_context import PATTERN_CHARACTERS
from .model import same_configuration


UNREPORTED = object()


def explanation(field, status, message, *, before=UNREPORTED, after=UNREPORTED):
    result = {"field": field, "status": status, "message": message}
    if before is not UNREPORTED:
        result["before"] = before
    if after is not UNREPORTED:
        result["after"] = after
    return result


def detected_field(field):
    return explanation(
        field,
        "detected",
        "A propriedade mudou. A análise registra a alteração no campo.",
    )


def event_state(evaluation):
    if evaluation["event_status"] == "excluded":
        return "event_excluded"
    return evaluation["event_status"]


def job_state(evaluation, job):
    if evaluation["event_status"] != "eligible":
        return event_state(evaluation)
    active = evaluation.get("job_states", {}).get(job)
    if active is True:
        return "active"
    if active is False:
        return "skipped"
    return "indeterminate"


def compare_contexts(before_snapshot, after_snapshot, job=None):
    comparisons = []
    pairs = zip(before_snapshot["context_evaluations"], after_snapshot["context_evaluations"])
    for before_evaluation, after_evaluation in pairs:
        if job is None:
            before_state = event_state(before_evaluation)
            after_state = event_state(after_evaluation)
        else:
            before_state = job_state(before_evaluation, job)
            after_state = job_state(after_evaluation, job)
        comparisons.append({
            "context": before_evaluation["context"],
            "before": before_state,
            "after": after_state,
        })
    return comparisons


def condition_explanation(comparisons):
    for result in comparisons:
        if result["before"] in ("active", "skipped") and result["after"] in ("active", "skipped"):
            details = explanation(
                "if",
                "explained",
                "A condição mudou. Os estados abaixo refletem as duas configurações no mesmo cenário.",
            )
            break
    else:
        details = explanation(
            "if",
            "indeterminate",
            "A condição mudou. Comparar seus efeitos exige um cenário elegível nas duas versões e valores conhecidos.",
        )
    details["context_comparisons"] = comparisons
    return details


def event_definitions(triggers):
    definitions = {}
    if isinstance(triggers, str):
        definitions[triggers] = {}
    elif isinstance(triggers, list):
        for event in triggers:
            definitions[event] = {}
    else:
        for event, config in triggers.items():
            if config is None:
                definitions[event] = {}
            else:
                definitions[event] = config
    return definitions


def public_event_definitions(definitions):
    visible = {}
    for event, config in definitions.items():
        if re.fullmatch(r"[a-z_][a-z0-9_]*", event) is None:
            continue
        event_summary = {}
        visible[event] = event_summary
        if event not in ("push", "pull_request") or not isinstance(config, dict):
            continue
        for field in ("branches", "branches-ignore"):
            branches = config.get(field)
            if not isinstance(branches, list) or not branches:
                continue
            public_branches = []
            for branch in branches:
                if not isinstance(branch, str) or re.fullmatch(r"[A-Za-z0-9._/-]+", branch) is None:
                    break
                if PATTERN_CHARACTERS.intersection(branch):
                    break
                public_branches.append(branch)
            else:
                event_summary[field] = public_branches
    return visible


def trigger_explanation(before, after, before_snapshot, after_snapshot):
    before_definitions = event_definitions(before)
    after_definitions = event_definitions(after)
    comparisons = compare_contexts(before_snapshot, after_snapshot)
    status = "explained"
    if same_configuration(before_definitions, after_definitions):
        message = "A forma da declaração mudou e manteve os mesmos eventos e configurações de disparo."
    elif before_definitions.keys() != after_definitions.keys():
        message = "A lista de eventos que podem disparar o workflow mudou."
    else:
        message = "A configuração dos eventos mudou. A elegibilidade fica indeterminada nos cenários sem avaliação conclusiva."
        status = "indeterminate"
        for result in comparisons:
            event = result["context"]["github.event_name"]
            if same_configuration(before_definitions.get(event), after_definitions.get(event)):
                continue
            if "indeterminate" not in (result["before"], result["after"]):
                message = "Os filtros ou parâmetros mudaram. Veja a elegibilidade do mesmo evento nas duas versões."
                status = "explained"
                break
    result = explanation(
        "on",
        status,
        message,
        before=public_event_definitions(before_definitions),
        after=public_event_definitions(after_definitions),
    )
    result["context_comparisons"] = comparisons
    return result


def needs_explanation(change, after_workflow):
    job = change["job"]
    before_needs = change["before"]
    after_needs = change["after"]
    added = sorted(set(after_needs).difference(before_needs))
    removed = sorted(set(before_needs).difference(after_needs))
    messages = []
    if added:
        jobs = ", ".join(added)
        messages.append(f"O job {job} passa a depender diretamente de {jobs}.")
    if removed:
        jobs = ", ".join(removed)
        messages.append(f"O job {job} deixa de depender diretamente de {jobs}.")
        remaining_ancestors = after_workflow.ancestors(job)
        for dependency in removed:
            if dependency not in remaining_ancestors:
                messages.append(f"A ordem entre {dependency} e {job} deixou de ser imposta por needs.")
                continue
            for intermediate in after_needs:
                if dependency in after_workflow.ancestors(intermediate):
                    messages.append(f"A dependência indireta por {intermediate} mantém {dependency} antes de {job}.")
                    break
    return explanation(
        "needs",
        "explained",
        " ".join(messages),
        before=before_needs,
        after=after_needs,
    )


def timeout_explanation(before_config, after_config, scope):
    field = "timeout-minutes"
    before = before_config.get(field)
    after = after_config.get(field)
    for config, value in ((before_config, before), (after_config, after)):
        if field in config and (type(value) is not int or value <= 0):
            return explanation(field, "indeterminate", "O limite mudou e requer um valor inteiro positivo para ser determinado.")

    if before is None:
        message = f"O {scope} passou a declarar um limite de execução de {after} minutos."
    elif after is None:
        message = f"O limite explícito de {before} minutos foi removido do {scope}."
        if scope == "job":
            message += " O GitHub Actions aplica seu limite padrão, sujeito ao limite do runner."
    elif after > before:
        message = f"O limite de execução do {scope} aumentou de {before} para {after} minutos."
    else:
        message = f"O limite de execução do {scope} diminuiu de {before} para {after} minutos."
    if after is not None:
        if scope == "job":
            message += " O GitHub cancela o job quando ele atinge o limite aplicável. O runner pode impor um limite menor."
        else:
            message += " O GitHub encerra o processo do step ao atingir esse limite enquanto o job estiver ativo."
    return explanation(field, "explained", message, before=before, after=after)


def failure_policy_explanation(before_config, after_config, scope):
    field = "continue-on-error"
    before = before_config.get(field, False)
    after = after_config.get(field, False)
    if not isinstance(before, bool) or not isinstance(after, bool):
        message = "A política de falha mudou. A análise requer valores booleanos para explicar o efeito."
        return explanation(field, "indeterminate", message)
    if scope == "step":
        affected = "job"
    else:
        affected = "workflow"
    if after:
        message = f"Se este {scope} falhar, sua falha passa a ser tolerada no resultado do {affected}."
    else:
        message = f"Uma falha neste {scope} pode voltar a reprovar o {affected}."
    return explanation(field, "explained", message, before=before, after=after)


def literal_runner_label(value):
    if not isinstance(value, str) or not value.strip():
        return False
    return re.fullmatch(r"[A-Za-z0-9_. -]+", value) is not None


def literal_runner_labels(value):
    if literal_runner_label(value):
        return True
    if not isinstance(value, list) or not value:
        return False
    for label in value:
        if not literal_runner_label(label):
            return False
    return True


def literal_runner(value):
    if literal_runner_labels(value):
        return True
    if not isinstance(value, dict) or not value or value.keys() - {"group", "labels"}:
        return False
    if "group" in value and not literal_runner_label(value["group"]):
        return False
    if "labels" in value and not literal_runner_labels(value["labels"]):
        return False
    return True


def runner_explanation(before_config, after_config):
    field = "runs-on"
    before = before_config.get(field)
    after = after_config.get(field)
    for config, value in ((before_config, before), (after_config, after)):
        if field in config and not literal_runner(value):
            return explanation(field, "indeterminate", "A seleção mudou. Os requisitos do runner não são inteiramente literais.")
    message = "Mudaram os requisitos declarados para selecionar o runner do job."
    return explanation(field, "explained", message, before=before, after=after)


def concurrency_settings(scope_config):
    if "concurrency" not in scope_config:
        return None, None, False
    config = scope_config["concurrency"]
    if isinstance(config, str):
        return config, False, True
    if isinstance(config, dict):
        return config.get("group"), config.get("cancel-in-progress", False), True
    return None, None, True


def public_concurrency(group, cancel, declared):
    if not declared:
        return None
    data = {}
    if literal_runner_label(group):
        data["group"] = group
    if isinstance(cancel, bool):
        data["cancel-in-progress"] = cancel
    return data


def concurrency_explanation(before_config, after_config, scope):
    field = "concurrency"
    before_group, before_cancel, before_declared = concurrency_settings(before_config)
    after_group, after_cancel, after_declared = concurrency_settings(after_config)
    public_before = public_concurrency(before_group, before_cancel, before_declared)
    public_after = public_concurrency(after_group, after_cancel, after_declared)

    messages = []
    uncertain = []
    if not before_declared and after_declared and isinstance(after_group, str) and after_group.strip():
        messages.append(f"O {scope} passa a ter um grupo de concorrência configurado.")
    if before_declared and not after_declared:
        messages.append(f"O grupo de concorrência deixou de ser declarado neste {scope}.")
    if before_declared and after_declared and before_group != after_group:
        if literal_runner_label(before_group) and literal_runner_label(after_group):
            if before_group.casefold() != after_group.casefold():
                messages.append("Mudou o grupo que reúne execuções sujeitas à mesma política de concorrência.")
            else:
                messages.append("O grupo manteve o mesmo nome ao ignorar maiúsculas e minúsculas.")
        else:
            uncertain.append("O grupo declarado mudou. O grupo efetivo depende do valor da configuração.")
    if after_declared and before_cancel is not after_cancel:
        if after_cancel is True:
            messages.append("Uma nova execução pode cancelar a que estiver em andamento no mesmo grupo.")
        elif after_cancel is False and before_declared:
            messages.append("A política atual preserva a execução em andamento quando chega outra no mesmo grupo.")
        elif not isinstance(after_cancel, bool):
            uncertain.append("A avaliação de cancelamento requer o valor de cancel-in-progress na execução.")

    if messages:
        if after_declared and not literal_runner_label(after_group) and not uncertain:
            uncertain.append("Identificar as execuções afetadas exige conhecer o grupo efetivo.")
        messages.extend(uncertain)
        return explanation(field, "explained", " ".join(messages), before=public_before, after=public_after)
    if uncertain or (after_declared and not literal_runner_label(after_group)):
        if not uncertain:
            uncertain.append("O grupo de concorrência ficou indeterminado.")
        return explanation(field, "indeterminate", " ".join(uncertain), before=public_before, after=public_after)
    return detected_field(field)


def action_explanation(values):
    field = "uses"
    if values is None:
        return explanation(field, "indeterminate", "A referência à action mudou. A análise requer uma referência literal.")
    before = values["before"]
    after = values["after"]
    for value in (before, after):
        if value is not None and re.fullmatch(r"[A-Za-z0-9_./@:-]+", value) is None:
            return explanation(field, "detected", "A referência declarada da action mudou.")
    return explanation(field, "explained", "A referência declarada da action mudou.", before=before, after=after)


def step_explanations(record, before_steps, after_steps):
    change = record["change"]
    before_position = record["before_step"]
    after_position = record["after_step"]
    if change == "unmatched":
        message = "A identidade da etapa entre versões ficou indeterminada."
        return [explanation("step", "indeterminate", message)]
    if change == "added":
        message = f"Uma etapa foi adicionada na posição {after_position}."
        return [explanation("step", "explained", message, after=after_position)]
    if change == "removed":
        message = f"A etapa que ocupava a posição {before_position} foi removida."
        return [explanation("step", "explained", message, before=before_position)]
    if change == "reordered":
        message = "A posição da etapa mudou em relação a outras etapas correspondentes."
        return [explanation("order", "explained", message, before=before_position, after=after_position)]

    before = before_steps[before_position - 1]
    after = after_steps[after_position - 1]
    explanations = []
    fields = set(record["fields"])
    fields.update(record["other_fields"])
    for field in sorted(fields):
        if field == "if":
            detail = condition_explanation(record.get("context_comparisons", []))
        elif field == "continue-on-error":
            detail = failure_policy_explanation(before, after, "step")
        elif field == "timeout-minutes":
            detail = timeout_explanation(before, after, "step")
        elif field == "uses":
            detail = action_explanation(record["fields"].get(field))
        else:
            detail = detected_field(field)
        explanations.append(detail)
    return explanations


def explain_changes(before, after, changes, step_changes, before_snapshot, after_snapshot):
    jobs_with_step_details = set()
    for record in step_changes:
        job = record["job"]
        jobs_with_step_details.add(job)
        record["explanations"] = step_explanations(record, before.jobs[job]["steps"], after.jobs[job]["steps"])

    for record in changes:
        rule = record["rule"]
        job = record.get("job")
        field = record.get("field")
        if job is None:
            if rule == "TRIGGER_CHANGE":
                detail = trigger_explanation(before.raw["on"], after.raw["on"], before_snapshot, after_snapshot)
            elif field == "concurrency":
                detail = concurrency_explanation(before.raw, after.raw, "workflow")
            else:
                detail = detected_field(field)
        elif rule == "R01_JOB_CHANGE":
            if record["change"] == "added":
                message = f"O job {job} passou a fazer parte da configuração."
            else:
                message = f"O job {job} foi removido da configuração."
            detail = explanation("job", "explained", message)
        elif rule == "R01_DEPENDENCY_CHANGE":
            detail = needs_explanation(record, after)
        elif rule == "R01_REACHABILITY_CHANGE":
            detail = explanation(
                "reachability",
                "explained",
                "Mudou o conjunto de jobs que precisam preceder este job no grafo.",
                before=record["before"],
                after=record["after"],
            )
        elif rule == "STEP_CHANGE":
            if job in jobs_with_step_details:
                detail = explanation("steps", "detected", "A lista de etapas mudou. A comparação por etapa detalha as diferenças identificadas.")
            else:
                detail = explanation("steps", "indeterminate", "A lista de etapas mudou. O efeito sobre a ordem ficou indeterminado.")
        elif field == "if":
            comparisons = compare_contexts(before_snapshot, after_snapshot, job)
            detail = condition_explanation(comparisons)
        elif field == "continue-on-error":
            detail = failure_policy_explanation(before.jobs[job], after.jobs[job], "job")
        elif field == "timeout-minutes":
            detail = timeout_explanation(before.jobs[job], after.jobs[job], "job")
        elif field == "runs-on":
            detail = runner_explanation(before.jobs[job], after.jobs[job])
        elif field == "concurrency":
            detail = concurrency_explanation(before.jobs[job], after.jobs[job], "job")
        else:
            detail = detected_field(field)
        record["explanations"] = [detail]
