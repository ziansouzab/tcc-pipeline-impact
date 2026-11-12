from __future__ import annotations

import json
from pathlib import Path

from .model import InputError


CONTEXT_KEYS = (
    "github.event_name",
    "github.ref",
    "github.base_ref",
    "github.head_ref",
    "github.event.before",
)
PATTERN_CHARACTERS = set("*+?![]{}\\")


def context_object(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise InputError("Chave repetida no JSON de contextos.")
        values[key] = value
    return values


def load_contexts(path: str | Path) -> list[dict]:
    context_path = Path(path)
    try:
        text = context_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError(f"{context_path}: o arquivo de contextos deve usar codificação UTF-8.") from error

    try:
        contexts = json.loads(text, object_pairs_hook=context_object)
    except json.JSONDecodeError as error:
        raise InputError(f"{context_path}: JSON de contextos inválido na linha {error.lineno}.") from error
    except RecursionError as error:
        raise InputError(f"{context_path}: estrutura do JSON de contextos muito profunda.") from error

    if not isinstance(contexts, list):
        raise InputError("O arquivo de contextos deve conter uma lista de objetos.")

    seen = set()
    for position, context in enumerate(contexts, start=1):
        if not isinstance(context, dict):
            raise InputError(f"Contexto {position}: esperado um objeto.")

        event_name = context.get("github.event_name")
        if not isinstance(event_name, str) or not event_name.strip():
            raise InputError(f"Contexto {position}: github.event_name deve ser um texto não vazio.")

        for key, value in context.items():
            if key not in CONTEXT_KEYS:
                raise InputError(f"Contexto {position}: campo de contexto não suportado.")
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise InputError(f"Contexto {position}: {key} deve ser um texto não vazio ou null.")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise InputError(f"Contexto {position}: {key} contém texto Unicode inválido.") from error

        context_values = tuple(sorted(context.items()))
        if context_values in seen:
            raise InputError(f"Contexto {position}: contexto duplicado.")
        seen.add(context_values)

    return contexts


def event_eligibility(triggers, context) -> tuple[bool | None, str]:
    event_name = context.get("github.event_name")
    if not isinstance(event_name, str) or not event_name.strip():
        return None, "O contexto não identifica o evento do GitHub."

    configuration = None
    if isinstance(triggers, str):
        declared = triggers == event_name
    elif isinstance(triggers, list):
        declared = event_name in triggers
    elif isinstance(triggers, dict):
        declared = event_name in triggers
        configuration = triggers.get(event_name)
    else:
        return None, "A declaração de eventos não pôde ser interpretada."

    if not declared:
        return False, "O evento do contexto não está declarado no workflow."

    if configuration is None or configuration == {}:
        return True, "O evento do contexto está declarado sem filtros."

    if event_name not in ("push", "pull_request") or not isinstance(configuration, dict):
        return None, "A configuração do evento está fora do subconjunto interpretado."

    if len(configuration) != 1:
        return None, "A combinação de filtros ou parâmetros do evento está fora do subconjunto interpretado."

    if "branches" in configuration:
        filter_name = "branches"
    elif "branches-ignore" in configuration:
        filter_name = "branches-ignore"
    else:
        return None, "O filtro ou parâmetro do evento está fora do subconjunto interpretado."

    patterns = configuration[filter_name]
    if not isinstance(patterns, list) or not patterns:
        return None, "O filtro de branches exige uma lista de nomes literais."

    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            return None, "O filtro de branches contém um nome inválido."
        if PATTERN_CHARACTERS.intersection(pattern):
            return None, "O filtro de branches contém padrões fora do subconjunto interpretado."

    if event_name == "push":
        reference = context.get("github.ref")
        if not isinstance(reference, str):
            return None, "O contexto de push não informa uma referência de branch."
        if reference.startswith("refs/tags/") and reference.removeprefix("refs/tags/"):
            return False, "O filtro de branches exclui eventos de push em tags."
        if not reference.startswith("refs/heads/"):
            return None, "A referência do contexto de push não pôde ser interpretada como branch."
        branch = reference.removeprefix("refs/heads/")
    else:
        branch = context.get("github.base_ref")

    if not isinstance(branch, str) or not branch.strip():
        return None, "O contexto não informa a branch necessária para avaliar o filtro."

    matches_filter = branch in patterns
    if filter_name == "branches":
        eligible = matches_filter
    else:
        eligible = not matches_filter

    if eligible:
        return True, "A branch do contexto atende ao filtro do evento."
    return False, "A branch do contexto está fora do filtro do evento."
