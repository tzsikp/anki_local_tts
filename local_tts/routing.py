"""Preset selection logic.

Templates carry only a language tag (`{{tts ja_JP voices=LocalTTS:...}}`);
the routing table picks the preset at playback time. This is the central
fix over AwesomeTTS — switching voices for a deck is one settings edit,
not a template rewrite. Resolution is strictly first-match-wins, in this
order: deck override → notetype override → language fallback → default.
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .presets import Preset


class Router:
    """Stateless preset resolver bound to a `Config` snapshot."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def resolve(self, *, deck_id: int | None, notetype_id: int | None, lang: str | None) -> Preset | None:
        """Return the preset for the given context, or None if nothing matches."""
        cfg = self.config
        name = (
            (deck_id is not None and cfg.routing.by_deck.get(str(deck_id)))
            or (notetype_id is not None and cfg.routing.by_notetype.get(str(notetype_id)))
            or (lang and cfg.routing.by_language.get(_lang_root(lang)))
            or cfg.default_preset
        )
        if not name:
            return None
        return cfg.preset_by_name(name)

    def resolve_for_card(self, card: Any, lang: str | None) -> Preset | None:
        """Convenience wrapper that pulls deck_id/notetype_id off an Anki card."""
        deck_id = getattr(card, "did", None)
        notetype_id = None
        try:
            notetype_id = card.note_type()["id"]
        except Exception:
            pass
        return self.resolve(deck_id=deck_id, notetype_id=notetype_id, lang=lang)


def _lang_root(lang: str) -> str:
    return lang.split("_", 1)[0].lower()
