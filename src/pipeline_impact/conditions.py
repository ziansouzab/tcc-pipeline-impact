from __future__ import annotations

import re

from .event_context import CONTEXT_KEYS


STRING_TOKEN_PATTERN = r"('(?:[^']|'')*')"
OPERATOR_TOKEN_PATTERN = r"(\&\&|\|\||==|!=|!|\(|\)|,)"
IDENTIFIER_TOKEN_PATTERN = r"([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)"
IDENTIFIER = re.compile(IDENTIFIER_TOKEN_PATTERN)
STRING_FUNCTIONS = ("contains", "startswith", "endswith")
RUNTIME_NAMESPACES = (
    "steps",
    "needs",
    "job",
    "runner",
    "strategy",
    "matrix",
    "env",
    "vars",
    "secrets",
    "inputs",
)


TOKEN_PATTERN = (
    r"\s*(?:"
    + STRING_TOKEN_PATTERN
    + "|"
    + OPERATOR_TOKEN_PATTERN
    + "|"
    + IDENTIFIER_TOKEN_PATTERN
    + ")"
)
TOKEN = re.compile(TOKEN_PATTERN)


class UnsupportedCondition(ValueError):

    pass


def tri_and(a: bool | None, b: bool | None) -> bool | None:
    if a is False:
        return False

    if b is False:
        return False

    if a is None:
        return None

    if b is None:
        return None

    return True


def tri_or(a: bool | None, b: bool | None) -> bool | None:
    if a is True:
        return True

    if b is True:
        return True

    if a is None:
        return None

    if b is None:
        return None

    return False


def evaluate(
    expression: str | None,
    context: dict[str, str | bool | None],
    success: bool | None = True,
    *,
    unavailable_references: dict[str, list[str]] | None = None,
) -> bool | None:
    if expression is None:
        return success

    expression = expression.strip()


    if expression.startswith("${{") and expression.endswith("}}"):
        expression = expression[3:-2]
        expression = expression.strip()


    tokens = []
    position = 0

    while position < len(expression):
        match = TOKEN.match(expression, position)

        if match is None:
            raise UnsupportedCondition(expression)

        for matched_group in match.groups():
            if matched_group is not None:
                tokens.append(matched_group)
                break

        position = match.end()


    cursor = 0
    status_function_used = False

    def take(expected: str | None = None) -> str:
        nonlocal cursor

        if cursor >= len(tokens):
            raise UnsupportedCondition(expression)

        current_token = tokens[cursor]

        if expected is not None:
            if current_token != expected:
                raise UnsupportedCondition(expression)

        cursor += 1
        return current_token

    def peek() -> str | None:
        if cursor < len(tokens):
            return tokens[cursor]

        return None

    def boolean_value(value):
        if value is not None and not isinstance(value, bool):
            raise UnsupportedCondition(expression)
        return value

    def string_function(function_name):
        take("(")
        text = disjunction()
        take(",")
        search = disjunction()
        take(")")

        if text is not None and not isinstance(text, str):
            raise UnsupportedCondition(expression)
        if search is not None and not isinstance(search, str):
            raise UnsupportedCondition(expression)
        if text is None or search is None:
            return None

        text = text.casefold()
        search = search.casefold()
        if function_name == "contains":
            return search in text
        if function_name == "startswith":
            return text.startswith(search)
        return text.endswith(search)

    def unknown_reference(reference):
        namespace, separator, _ = reference.partition(".")
        if not separator or unavailable_references is None:
            raise UnsupportedCondition(expression)

        if reference in CONTEXT_KEYS:
            result = "missing_event_data"
            display_reference = reference
        elif namespace in RUNTIME_NAMESPACES:
            result = "runtime_value"
            display_reference = namespace
            if namespace in ("steps", "needs"):
                display_reference = reference
        else:
            result = "unsupported_context"
            display_reference = None
            if namespace == "github":
                display_reference = namespace

        references = unavailable_references.setdefault(result, [])
        if display_reference and display_reference not in references:
            references.append(display_reference)
        return None

    def atom():
        nonlocal status_function_used

        token = take()

        if token == "(":
            value = disjunction()
            take(")")
            return value

        if token == "!":
            value = boolean_value(atom())

            if value is None:
                return None

            return not value

        if token.startswith("'"):
            text_without_quotes = token[1:-1]
            text_with_unescaped_quotes = text_without_quotes.replace("''", "'")
            return text_with_unescaped_quotes

        token_name = token.casefold()
        if token_name == "true":
            return True

        if token_name == "false":
            return False

        if token_name in ("success", "failure", "cancelled", "always"):
            take("(")
            take(")")
            status_function_used = True

            if token_name == "success":
                return success


            if token_name == "failure":
                return False

            if token_name == "cancelled":
                return False

            return True

        if token_name in STRING_FUNCTIONS and peek() == "(":
            return string_function(token_name)

        if token in context:
            context_value = context[token]

            if context_value is None:
                if unavailable_references is not None:
                    return unknown_reference(token)
                return None

            if isinstance(context_value, (str, bool)):
                return context_value

            raise UnsupportedCondition(expression)

        if IDENTIFIER.fullmatch(token) and peek() != "(":
            return unknown_reference(token)

        raise UnsupportedCondition(expression)

    def comparison():
        left_value = atom()
        next_token = peek()

        if next_token in ("==", "!="):
            operator = take()
            right_value = atom()


            if left_value is None or right_value is None:
                if unavailable_references is not None:
                    return None
                raise UnsupportedCondition(expression)

            if type(left_value) != type(right_value):
                raise UnsupportedCondition(expression)

            if isinstance(left_value, str):
                left_value = left_value.casefold()
                right_value = right_value.casefold()

            if operator == "==":
                left_value = left_value == right_value
            else:
                left_value = left_value != right_value

        return left_value

    def conjunction():
        value = comparison()

        while peek() == "&&":
            take("&&")
            right_value = boolean_value(comparison())
            value = tri_and(boolean_value(value), right_value)

        return value

    def disjunction():
        value = conjunction()

        while peek() == "||":
            take("||")
            right_value = boolean_value(conjunction())
            value = tri_or(boolean_value(value), right_value)

        return value


    value = boolean_value(disjunction())

    if cursor != len(tokens):
        raise UnsupportedCondition(expression)

    if status_function_used:
        return value


    return tri_and(success, value)


def condition_diagnostic(result, location, diagnostics, limitations, references=None):
    if result == "missing_event_data":
        message = "O contexto informado não contém o dado de evento usado na condição."
    elif result == "runtime_value":
        message = "A condição depende de um valor de execução indisponível na análise."
    elif result == "unsupported_context":
        message = "A condição usa uma propriedade fora do contexto analisado."
    else:
        message = "A expressão está fora do subconjunto interpretado."

    if diagnostics is not None:
        detail = {"result": result, "message": message, "location": location}
        if references:
            detail["references"] = references
        diagnostics.append(detail)

    prefix = f"Job {location['job']}"
    if "step" in location:
        prefix += f", step {location['step']}"
    explanation = f"{prefix}: {message}"
    if references:
        explanation += " Referências: " + ", ".join(references) + "."
    limitations.append(explanation)


def state_from_condition(expression, context, success, location, diagnostics, limitations):
    unavailable_references = {}
    try:
        result = evaluate(
            expression,
            context,
            success,
            unavailable_references=unavailable_references,
        )
    except (UnsupportedCondition, RecursionError):
        condition_diagnostic("unsupported_expression", location, diagnostics, limitations)
        return None

    if unavailable_references:
        for cause, references in unavailable_references.items():
            condition_diagnostic(cause, location, diagnostics, limitations, references)
        return None

    return result


def states(
    workflow,
    context: dict[str, str | bool | None],
    *,
    job_states: dict | None = None,
    diagnostics: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    if job_states is None:
        job_states = {}
    step_states = {}
    limitations = []


    for job in workflow.order:
        data = workflow.jobs[job]
        ancestor_states = []

        for ancestor in workflow.ancestors(job):
            ancestor_states.append(job_states[ancestor])

        if False in ancestor_states:
            success = False
        elif None in ancestor_states:
            success = None
        else:
            success = True

        job_location = {"job": job, "field": "if"}
        active = state_from_condition(
            data["if"], context, success, job_location, diagnostics, limitations
        )

        if workflow.unresolved_job(job):
            active = None

        job_states[job] = active

        for index, step in enumerate(data["steps"]):
            step_key = (job, index)

            if active is False:
                step_states[step_key] = False
                continue

            step_location = {"job": job, "step": index + 1, "field": "if"}
            condition_result = state_from_condition(
                step["if"], context, True, step_location, diagnostics, limitations
            )
            step_states[step_key] = tri_and(active, condition_result)

    return step_states, limitations
