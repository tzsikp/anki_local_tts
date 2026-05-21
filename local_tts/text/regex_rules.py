"""User-defined regex rewrites, applied after the built-in cleanup pipeline.

This is the only place language-specific transforms belong — readings
that VOICEVOX gets wrong, vocabulary substitutions, etc. Rules apply in
order.

Validation happens up front (`validate_pattern`, called by `Config.load`
and exposed for live use in the preset editor). The runtime `apply` is
still defensive: a malformed rule that slips past validation is skipped
rather than allowed to crash a review.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..presets import RegexRule


def validate_pattern(pattern: str) -> str | None:
    """Compile `pattern` and return an error message, or None if it's valid."""
    try:
        re.compile(pattern)
        return None
    except re.error as exc:
        return str(exc)


def validate_rules(rules: Iterable[RegexRule]) -> list[tuple[RegexRule, str]]:
    """Return `(rule, error)` for every rule whose pattern fails to compile."""
    errors: list[tuple[RegexRule, str]] = []
    for rule in rules:
        err = validate_pattern(rule.pattern)
        if err is not None:
            errors.append((rule, err))
    return errors


def apply(text: str, rules: Iterable[RegexRule]) -> str:
    """Apply enabled rules in order. Invalid patterns are silently skipped
    so a typo can't break playback; use `validate_rules` for diagnostics."""
    for rule in rules:
        if not rule.enabled:
            continue
        try:
            text = re.sub(rule.pattern, rule.replacement, text)
        except re.error:
            continue
    return text
