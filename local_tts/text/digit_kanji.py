"""Convert ASCII / full-width digit runs to Japanese kanji numerals.

VOICEVOX reads bare digit sequences digit-by-digit (`7月` → "nana-tsuki"
instead of "shichi-gatsu"; `1990年` → "ichi kyuu kyuu zero nen" with a
pause between each digit). Replacing the digit run with its classical
kanji form (`七月`, `千九百九十年`) makes the engine pronounce the number
as a number.

Pure module. Idempotent on text without digits, so the cache key for
digit-free entries is unaffected when the toggle flips.
"""

from __future__ import annotations

import re

_KANJI_DIGITS = ("", "一", "二", "三", "四", "五", "六", "七", "八", "九")
_FULLWIDTH_TO_ASCII = str.maketrans("０１２３４５６７８９", "0123456789")
_UNITS: tuple[tuple[str, int], ...] = (
    ("", 1),
    ("万", 10_000),
    ("億", 10**8),
    ("兆", 10**12),
    ("京", 10**16),
)
_DIGIT_RUN = re.compile(r"[0-9０-９]+")


def _under_10000(n: int) -> str:
    if n == 0:
        return ""
    out: list[str] = []
    thousands, n = divmod(n, 1000)
    if thousands:
        out.append((_KANJI_DIGITS[thousands] if thousands > 1 else "") + "千")
    hundreds, n = divmod(n, 100)
    if hundreds:
        out.append((_KANJI_DIGITS[hundreds] if hundreds > 1 else "") + "百")
    tens, ones = divmod(n, 10)
    if tens:
        out.append((_KANJI_DIGITS[tens] if tens > 1 else "") + "十")
    if ones:
        out.append(_KANJI_DIGITS[ones])
    return "".join(out)


def int_to_kanji(n: int) -> str:
    if n == 0:
        return "零"
    if n < 0:
        return "マイナス" + int_to_kanji(-n)
    parts: list[str] = []
    for name, factor in reversed(_UNITS):
        chunk = (n // factor) % 10_000
        if chunk:
            parts.append(_under_10000(chunk) + name)
    return "".join(parts)


def convert(text: str) -> str:
    """Rewrite every run of ASCII or full-width digits as a kanji numeral."""
    if not text:
        return text

    def _repl(m: re.Match) -> str:
        digits = m.group(0).translate(_FULLWIDTH_TO_ASCII)
        try:
            return int_to_kanji(int(digits))
        except ValueError:
            return m.group(0)

    return _DIGIT_RUN.sub(_repl, text)
