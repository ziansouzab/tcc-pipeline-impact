from __future__ import annotations

import re


STRING_TOKEN_PATTERN = r"('(?:[^']|'')*')"
OPERATOR_TOKEN_PATTERN = r"(\&\&|\|\||==|!=|!|\(|\))"
IDENTIFIER_TOKEN_PATTERN = r"([A-Za-z_][A-Za-z0-9_.]*)"


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

    def atom():
        nonlocal status_function_used

        token = take()

        if token == "(":
            value = disjunction()
            take(")")
            return value

        if token == "!":
            value = atom()

            if value is not None:
                if not isinstance(value, bool):
                    raise UnsupportedCondition(expression)

            if value is None:
                return None

            return not value

        if token.startswith("'"):
            text_without_quotes = token[1:-1]
            text_with_unescaped_quotes = text_without_quotes.replace("''", "'")
            return text_with_unescaped_quotes

        if token == "true":
            return True

        if token == "false":
            return False

        if token in ("success", "failure", "cancelled", "always"):
            take("(")
            take(")")
            status_function_used = True

            if token == "success":
                return success


            if token == "failure":
                return False

            if token == "cancelled":
                return False

            return True

        if token in context:
            context_value = context[token]

            if context_value is None:
                return None

            if isinstance(context_value, (str, bool)):
                return context_value

            raise UnsupportedCondition(expression)

        raise UnsupportedCondition(expression)

    def comparison():
        left_value = atom()
        next_token = peek()

        if next_token in ("==", "!="):
            operator = take()
            right_value = atom()


            if type(left_value) != type(right_value):
                raise UnsupportedCondition(expression)

            if left_value is None:
                raise UnsupportedCondition(expression)


            if isinstance(left_value, str):
                left_value = left_value.casefold()
                right_value = right_value.casefold()

            if operator == "==":
                left_value = left_value == right_value
            else:
                left_value = left_value != right_value

        if left_value is not None:
            if not isinstance(left_value, bool):
                raise UnsupportedCondition(expression)

        return left_value

    def conjunction():
        value = comparison()

        while peek() == "&&":
            take("&&")
            right_value = comparison()
            value = tri_and(value, right_value)

        return value

    def disjunction():
        value = conjunction()

        while peek() == "||":
            take("||")
            right_value = conjunction()
            value = tri_or(value, right_value)

        return value


    value = disjunction()

    if cursor != len(tokens):
        raise UnsupportedCondition(expression)

    if status_function_used:
        return value


    return tri_and(success, value)


def states(workflow, context: dict[str, str | bool | None]) -> tuple[dict, list[str]]:
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

        try:
            active = evaluate(data["if"], context, success)
        except UnsupportedCondition:
            active = None
            limitations.append(f"Job {job}: condição não suportada: {data['if']}")

        if workflow.unresolved_job(job):
            active = None

        job_states[job] = active

        for index, step in enumerate(data["steps"]):
            step_key = (job, index)

            try:
                condition_result = evaluate(step["if"], context)
                step_states[step_key] = tri_and(active, condition_result)
            except UnsupportedCondition:
                if active is False:
                    step_states[step_key] = False
                else:
                    step_states[step_key] = None

                limitations.append(
                    f"Job {job}, step {index + 1}: condição não suportada: {step['if']}"
                )

    return step_states, limitations
