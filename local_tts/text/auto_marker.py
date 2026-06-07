"""Auto-mark digit-、-digit pauses.

Pure helper used by the player when `Config.split_digits_auto` is on.
Rewrites every `、` that sits between two digit characters (half-width,
full-width, or the common CJK number kanji) to the user's configured
split marker. Lookarounds rather than capturing groups, so chains like
`三、五、七` rewrite in a single pass.

Why a built-in helper and not just a user regex rule: the substitution
needs the *current* marker as its replacement. If a user later changes
the marker character we'd silently break their rule. Keeping it
addon-side means flipping the toggle is the only configuration knob.
"""

from __future__ import annotations

import re

_DIGIT_CLASS = r"[0-9０-９一二三四五六七八九十百千万]"
_DIGIT_COMMA_DIGIT = re.compile(rf"(?<={_DIGIT_CLASS})、(?={_DIGIT_CLASS})")


def auto_mark_digit_pauses(text: str, marker: str) -> str:
    """Replace every `、` between two digit characters with `marker`.

    Empty / falsy `marker` is a no-op so callers don't need to guard.
    """
    if not marker:
        return text
    return _DIGIT_COMMA_DIGIT.sub(marker, text)
