"""Tokenization and numeric extraction for SVG path parsing."""

from __future__ import annotations

import math
import re

from svg2ooxml.common.geometry.paths.parser_types import PathParseError, Token

_COMMAND_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")
_TOKEN_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def _tokenize(data: str) -> list[Token]:
    tokens: list[Token] = []
    position = 0
    for match in _TOKEN_RE.finditer(data):
        _raise_for_invalid_path_gap(data, position, match.start())
        cmd, number = match.groups()
        if cmd:
            tokens.append(cmd)
        elif number:
            value = float(number)
            if not math.isfinite(value):
                raise PathParseError("Path data contains non-finite numbers")
            tokens.append(value)
        position = match.end()
    _raise_for_invalid_path_gap(data, position, len(data))
    return tokens


def _raise_for_invalid_path_gap(data: str, start: int, end: int) -> None:
    if all(char == "," or char.isspace() for char in data[start:end]):
        return
    raise PathParseError("Path data contains invalid tokens")


def _take_numbers(
    tokens: list[Token],
    index: int,
    required: int,
    *,
    allow_multiple: bool = False,
) -> tuple[list[float], int]:
    numbers: list[float] = []
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str) and _COMMAND_RE.match(token):
            break
        if not isinstance(token, float):
            raise PathParseError(f"Expected number, got {token!r}")
        numbers.append(token)
        index += 1
        if not allow_multiple and len(numbers) >= required:
            break
    if len(numbers) < required:
        raise PathParseError("Insufficient numeric values for command")
    return numbers, index


__all__ = ["_take_numbers", "_tokenize"]
