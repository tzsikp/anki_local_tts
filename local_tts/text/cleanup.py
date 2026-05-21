"""Built-in text cleanup pipeline.

Fixed-order, language-agnostic pre-processing applied before user regex
rules and synthesis:

    1. ruby tags        — `<ruby>本<rt>ほん</rt></ruby>` → base or reading
    2. strip HTML       — drop remaining tags
    3. bracket readings — `日々[ひび]` → base or reading
    4. Anki cloze       — `{{c1::日本語}}` → `日本語`
    5. whitespace       — collapse runs of whitespace, trim

All functions are pure (`str -> str`) so they're trivially unit-testable
without Anki. Anything beyond this must be expressed as user-visible
regex rules on the preset — no hidden NLP, no auto-detection.
"""

from __future__ import annotations

import re

from ..presets import CleanupOptions

RE_CLOZE_BRACED = re.compile(r"(?si)\{\{c\d+::(?P<content>.*?)(::(?P<hint>.*?))?\}\}")
RE_CLOZE_RENDERED = re.compile(r"<span class=.?cloze.?>\[(.+?)\]</span>")
RE_WHITESPACE = re.compile(r"[\0\s]+", re.UNICODE)
RE_RUBY = re.compile(r"<ruby[^>]*>(?P<inner>.*?)</ruby>", re.IGNORECASE | re.DOTALL)
RE_RT = re.compile(r"<rt[^>]*>(?P<reading>.*?)</rt>", re.IGNORECASE | re.DOTALL)
RE_RP = re.compile(r"<rp[^>]*>.*?</rp>", re.IGNORECASE | re.DOTALL)

# Hiragana, Katakana, half-width Kana, CJK ideographs, JP punctuation block.
# Spaces between two such chars are artifacts of furigana addons (used to
# disambiguate ruby placement) and have no place in spoken text.
_JP_CHARS = r"぀-ゟ゠-ヿｦ-ﾟ一-鿿　-〿"
RE_JP_INNER_SPACE = re.compile(rf"(?<=[{_JP_CHARS}])[ \t　]+(?=[{_JP_CHARS}])")


def strip_html(text: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(text, "html.parser").get_text(" ")
    except ImportError:
        return re.sub(r"<[^>]+>", " ", text)


def apply_ruby(text: str, mode: str) -> str:
    def repl(m: re.Match[str]) -> str:
        inner = RE_RP.sub("", m.group("inner"))
        if mode == "reading":
            readings = RE_RT.findall(inner)
            return "".join(readings) if readings else RE_RT.sub("", inner)
        return RE_RT.sub("", inner)
    return RE_RUBY.sub(repl, text)


def apply_brackets(text: str, mode: str, brackets: list[str]) -> str:
    for pair in brackets:
        if len(pair) != 2:
            continue
        open_c, close_c = re.escape(pair[0]), re.escape(pair[1])
        pattern = re.compile(rf"(\S+?){open_c}([^{open_c}{close_c}]+){close_c}")
        if mode == "reading":
            text = pattern.sub(r"\2", text)
        elif mode == "strip_brackets_only":
            text = pattern.sub(r"\1 \2", text)
        else:
            text = pattern.sub(r"\1", text)
    return text


def strip_cloze(text: str) -> str:
    text = RE_CLOZE_RENDERED.sub(r"\1", text)
    text = RE_CLOZE_BRACED.sub(lambda m: m.group("content"), text)
    return text


def normalize_whitespace(text: str) -> str:
    return RE_WHITESPACE.sub(" ", text).strip()


def collapse_cjk_spaces(text: str) -> str:
    return RE_JP_INNER_SPACE.sub("", text)


def clean(text: str, opts: CleanupOptions) -> str:
    """Run the full pipeline. Ruby is handled before HTML strip so that
    `<rt>` content can be kept or dropped before the surrounding tags
    vanish. CJK-inner-space collapse runs after bracket stripping, where
    furigana-style spaces become adjacent to their JP neighbours again."""
    text = apply_ruby(text, opts.ruby_mode)
    text = strip_html(text)
    text = apply_brackets(text, opts.bracket_mode, opts.brackets)
    text = strip_cloze(text)
    if opts.collapse_cjk_spaces:
        text = collapse_cjk_spaces(text)
    return normalize_whitespace(text)
