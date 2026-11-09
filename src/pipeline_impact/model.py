from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
import re
from typing import Any

import yaml


class InputError(ValueError):
    pass


class WorkflowLoader(yaml.SafeLoader):
    yaml_implicit_resolvers = deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)


for key, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    novas_regras = []

    for item in resolvers:
        if item[0] != "tag:yaml.org,2002:bool":
            novas_regras.append(item)

    WorkflowLoader.yaml_implicit_resolvers[key] = novas_regras

WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"),
    list("tTfF")
)


def unique_mapping(loader: WorkflowLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, (str, int, float, bool)):
            raise InputError("Chave YAML não suportada.")
        if key in result:
            raise InputError(f"Chave YAML duplicada: {key!r}, linha {key_node.start_mark.line + 1}.")
        result[key] = loader.construct_object(value_node)
    return result


WorkflowLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def condition(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if not isinstance(value, str):
        raise InputError("Condição 'if' deve ser texto ou booleano.")
    return value.strip()


@dataclass
class Workflow:
    source: str
    raw: dict
    jobs: dict[str, dict]
    order: list[str]
    limitations: list[str]

    def unresolved_job(self, job: str) -> bool:
        data = self.jobs[job]

        if "uses" in data:
            return True

        if "strategy" in data:
            return True

        concurrent_step_keys = ("parallel", "background", "wait", "wait-all", "cancel")
        for step in data["steps"]:
            for key in concurrent_step_keys:
                if key in step:
                    return True

        return False





def parse(text: str, source: str = "<memory>") -> Workflow:
    try:
        raw = yaml.load(text, Loader=WorkflowLoader)

    except yaml.YAMLError as exc:
        raise InputError(f"YAML inválido em {source}: {exc}") from exc

    if not isinstance(raw, dict):
        raise InputError(f"{source}: esperado um workflow com 'jobs' não vazio.")

    if not isinstance(raw.get("jobs"), dict):
        raise InputError(f"{source}: esperado um workflow com 'jobs' não vazio.")

    if not raw["jobs"]:
        raise InputError(f"{source}: esperado um workflow com 'jobs' não vazio.")

    jobs = deepcopy(raw["jobs"])

    for job_id in jobs:
        if not isinstance(job_id, str):
            raise InputError("Identificador de job inválido.")

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", job_id):
            raise InputError("Identificador de job inválido.")

    canonical = {}
    for job_id in jobs:
        canonical[job_id.lower()] = job_id

    if len(canonical) != len(jobs):
        raise InputError("Identificadores de jobs duplicados, ignorando maiúsculas/minúsculas.")

    limitations = []
    triggers = raw.get("on")

    if not isinstance(triggers, (str, list, dict)):
        raise InputError("Workflow deve declarar eventos em 'on'.")

    if isinstance(triggers, list):
        for event_name in triggers:
            if not isinstance(event_name, str):
                raise InputError("Lista de eventos inválida.")

    if isinstance(triggers, dict):
        for event_name in triggers:
            if not isinstance(event_name, str):
                raise InputError("Nomes de eventos devem ser textos.")

    if isinstance(triggers, dict):
        for event_configuration in triggers.values():
            if event_configuration:
                limitations.append("Filtros/configurações de eventos: simulação de condições indisponível.")
                break

    for job_id, data in jobs.items():
        if not isinstance(data, dict):
            raise InputError(f"Job {job_id}: esperado mapeamento.")

        needs = data.get("needs", [])

        if isinstance(needs, str):
            needs = [needs]

        if not isinstance(needs, list):
            raise InputError(f"Job {job_id}: 'needs' deve ser texto ou lista de textos.")

        for dependency in needs:
            if not isinstance(dependency, str):
                raise InputError(f"Job {job_id}: 'needs' deve ser texto ou lista de textos.")

        for dependency in needs:
            if dependency.lower() not in canonical:
                raise InputError(f"Job {job_id}: referência a job inexistente em 'needs'.")

        normalized_needs = []
        for dependency in needs:
            original_identifier = canonical[dependency.lower()]
            normalized_needs.append(original_identifier)

        needs = normalized_needs

        if len(needs) != len(set(needs)):
            raise InputError(f"Job {job_id}: dependências duplicadas.")

        data["needs"] = needs

        data["if"] = condition(data.get("if"))
        data.setdefault("continue-on-error", False)

        data.setdefault("outputs", {})
        if not isinstance(data["outputs"], dict):
            raise InputError(f"Job {job_id}: outputs deve ser mapeamento.")

        if "uses" in data or "strategy" in data:
            limitations.append(f"Job {job_id}: workflow reutilizável ou matriz não expandido.")

        steps = data.get("steps", [])
        if not isinstance(steps, list):
            raise InputError(f"Job {job_id}: 'steps' deve ser lista de mapeamentos.")

        for step in steps:
            if not isinstance(step, dict):
                raise InputError(f"Job {job_id}: 'steps' deve ser lista de mapeamentos.")

        data["steps"] = steps

        for step in steps:
            step["if"] = condition(step.get("if"))
            if "with" in step and not isinstance(step["with"], dict):
                raise InputError(f"Job {job_id}: parâmetros 'with' devem ser mapeamento.")

            concurrent_step_keys = ("parallel", "background", "wait", "wait-all", "cancel")
            for key in concurrent_step_keys:
                if key in step:
                    limitations.append(f"Job {job_id}: execução concorrente entre steps não modelada.")
                    break


    has_concurrency = "concurrency" in raw

    if not has_concurrency:
        for job_data in jobs.values():
            if "concurrency" in job_data:
                has_concurrency = True
                break

    if has_concurrency:
        limitations.append("Grupos de concurrency não modelados; sugestões de paralelismo suspensas.")

    try:
        dependencies = {}
        for job_id, data in jobs.items():
            dependencies[job_id] = data["needs"]

        sorter = TopologicalSorter(dependencies)
        order = list(sorter.static_order())

    except CycleError as exc:
        raise InputError("Ciclo nas dependências dos jobs.") from exc


    return Workflow(
        source=source,
        raw=raw,
        jobs=jobs,
        order=order,
        limitations=limitations,
    )


def load(path: str | Path) -> Workflow:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    source = str(path)
    workflow = parse(text, source)
    return workflow
