"""Describe a rejected final answer without retaining any model-generated text."""

import json
from typing import Any

from .graders import reject, unique


def parse_shape(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "EMPTY_FINAL_TEXT"
    if text.startswith(("<thinking>", "<analysis>")):
        return "VISIBLE_REASONING_PREFIX"
    if text.startswith(("```", "~~~")):
        return "MARKDOWN_FENCE"
    if text.startswith("<"):
        return "MARKUP_PREFIX"
    if not text.startswith("{") and "{" in text and not text.startswith(("[", '"')):
        return "TEXT_BEFORE_OBJECT"

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        try:
            return unique(items)
        except ValueError:
            raise KeyError from None

    decoder = json.JSONDecoder(object_pairs_hook=pairs, parse_constant=reject)
    try:
        value, end = decoder.raw_decode(text)
    except KeyError:
        return "DUPLICATE_JSON_KEY"
    except (ValueError, RecursionError):
        return "INVALID_JSON_SYNTAX"
    if end < len(text):
        return "TRAILING_CONTENT"
    return "NON_OBJECT_JSON" if not isinstance(value, dict) else "INVALID_JSON_SYNTAX"
