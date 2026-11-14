from __future__ import annotations

import re


STRING_LITERAL = r"'(?:[^']|'')*'"
IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_-]*"
EXPRESSION_BOUNDARY = re.compile(r"\}\}|" + STRING_LITERAL + "|'")
ACCESS_OR_STRING = re.compile(
    STRING_LITERAL
    + r"|(?<![A-Za-z0-9_.-])needs"
    + rf"(?:\s*\.\s*(?P<job_dot>{IDENTIFIER})|\s*\[\s*'(?P<job_index>{IDENTIFIER})'\s*\])"
    + r"(?:\s*\.\s*(?P<property_dot>outputs|result)(?![A-Za-z0-9_-])"
    + r"|\s*\[\s*'(?P<property_index>outputs|result)'\s*\])"
    + rf"(?:\s*\.\s*(?P<output_dot>{IDENTIFIER})|\s*\[\s*'(?P<output_index>{IDENTIFIER})'\s*\])?",
    re.IGNORECASE,
)


def expressions_in_text(text, implicit_condition):
    opening_delimiter = "${{"
    if implicit_condition and not text.lstrip().startswith(opening_delimiter):
        yield text
        return

    position = 0
    while True:
        opening = text.find(opening_delimiter, position)
        if opening == -1:
            return

        expression_start = opening + len(opening_delimiter)
        position = expression_start
        while True:
            boundary = EXPRESSION_BOUNDARY.search(text, position)
            if boundary is None or boundary.group() == "'":
                return

            position = boundary.end()
            if boundary.group() == "}}":
                yield text[expression_start:boundary.start()]
                break


def references_in_expression(expression):
    for match in ACCESS_OR_STRING.finditer(expression):
        producer = match["job_dot"] or match["job_index"]
        if producer is None:
            continue

        previous_position = match.start() - 1
        while previous_position >= 0 and expression[previous_position].isspace():
            previous_position -= 1
        if previous_position >= 0 and expression[previous_position] == ".":
            continue

        member = match["property_dot"] or match["property_index"]
        member = member.lower()
        output = match["output_dot"] or match["output_index"]
        if member == "outputs":
            if output is None:
                continue
            reference = f"needs.{producer}.outputs.{output}"
        else:
            if output is not None:
                continue
            reference = f"needs.{producer}.result"

        yield producer, reference


def references_in_value(value, implicit_condition):
    pending = [(value, implicit_condition)]
    references = {}

    while pending:
        current, allow_implicit_condition = pending.pop()
        if isinstance(current, str):
            for expression in expressions_in_text(current, allow_implicit_condition):
                for producer, reference in references_in_expression(expression):
                    references.setdefault(reference.lower(), (producer, reference))
        elif isinstance(current, dict):
            for child in reversed(list(current.values())):
                pending.append((child, False))
        elif isinstance(current, list):
            for child in reversed(current):
                pending.append((child, False))

    return references.values()


def job_needs_references(job_data):
    fields = [(None, job_data)]
    for position, step in enumerate(job_data["steps"], start=1):
        fields.append((position, step))

    for position, properties in fields:
        for field, value in properties.items():
            if field in ("id", "needs", "steps", "uses"):
                continue
            for producer, reference in references_in_value(value, field == "if"):
                yield position, str(field), producer, reference
