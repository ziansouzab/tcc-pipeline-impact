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
