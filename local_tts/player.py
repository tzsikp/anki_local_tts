"""Anki TTS hook.

`LocalTTSPlayer` is a `TTSProcessPlayer` subclass that Anki calls when a
card template renders a `{{tts <lang> voices=LocalTTS:...}}` tag. We
register one synthetic `TTSVoice` per supported language so the tag is
accepted without re-registration when a user adds a new deck.

`_play` runs on a background thread. The flow: resolve the preset via
the router, run the cleanup pipeline + user regex rules, look up the
cache, synthesize on miss. We set `self.audio_file_path`; Anki handles
actual playback. On any failure we return silently — no audio is better
than a crash mid-review.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

try:
    from anki.sound import AVTag, TTSTag
    from aqt.sound import OnDoneCallback
    from aqt.taskman import TaskManager
    from aqt.tts import TTSProcessPlayer, TTSVoice
except ImportError:
    TTSProcessPlayer = object  # type: ignore[assignment,misc]
    TTSVoice = object  # type: ignore[assignment,misc]
    AVTag = TTSTag = object  # type: ignore[assignment,misc]
    OnDoneCallback = object  # type: ignore[assignment,misc]
    TaskManager = object  # type: ignore[assignment,misc]

from .providers.base import ProviderError
from .text import cleanup, regex_rules

if TYPE_CHECKING:
    from .addon import LocalTTSAddon

VOICE_NAME = "LocalTTS"
SUPPORTED_LANGS = ["ja_JP", "en_US", "en_GB"]


class LocalTTSPlayer(TTSProcessPlayer):
    def __init__(self, taskman: TaskManager, addon: LocalTTSAddon) -> None:
        super().__init__(taskman)
        self._addon = addon

    def get_available_voices(self) -> List[TTSVoice]:
        return [TTSVoice(name=VOICE_NAME, lang=lang) for lang in SUPPORTED_LANGS]

    def _play(self, tag: AVTag) -> None:
        assert isinstance(tag, TTSTag)
        text = tag.field_text
        if not text or not text.strip():
            return

        preset = self._resolve_preset(tag)
        if preset is None:
            return

        processed = regex_rules.apply(cleanup.clean(text, preset.cleanup), preset.regex_rules)
        if not processed.strip():
            return

        key = self._addon.cache.key(preset, processed)
        cached = self._addon.cache.get(key)
        if cached is None:
            provider = self._addon.providers.get(preset.provider)
            if provider is None:
                return
            try:
                data = provider.synthesize(processed, preset)
            except ProviderError:
                return
            cached = self._addon.cache.put(key, data)

        self.audio_file_path = str(cached)

    def _resolve_preset(self, tag: TTSTag):
        try:
            from aqt import mw
            card = mw.reviewer.card if mw and mw.reviewer else None
        except Exception:
            card = None
        lang = getattr(tag, "lang", None)
        if card is None:
            preset_name = self._addon.config.routing.by_language.get(_lang_root(lang or "")) \
                or self._addon.config.default_preset
            return self._addon.config.preset_by_name(preset_name) if preset_name else None
        return self._addon.router.resolve_for_card(card, lang)


def _lang_root(lang: str) -> str:
    return lang.split("_", 1)[0].lower() if lang else ""
