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

from concurrent.futures import Future
from typing import TYPE_CHECKING, List

try:
    from anki.sound import AVTag, TTSTag
    from aqt.sound import OnDoneCallback, av_player
    from aqt.taskman import TaskManager
    from aqt.tts import TTSProcessPlayer, TTSVoice
except ImportError:
    TTSProcessPlayer = object  # type: ignore[assignment,misc]
    TTSVoice = object  # type: ignore[assignment,misc]
    AVTag = TTSTag = object  # type: ignore[assignment,misc]
    OnDoneCallback = object  # type: ignore[assignment,misc]
    TaskManager = object  # type: ignore[assignment,misc]
    av_player = None  # type: ignore[assignment]

from ._log import log
from .providers.base import ProviderError
from .text import auto_marker, cleanup, digit_kanji, regex_rules

if TYPE_CHECKING:
    from .addon import LocalTTSAddon

VOICE_NAME = "LocalTTS"
SUPPORTED_LANGS = ["ja_JP", "en_US", "en_GB"]


class LocalTTSPlayer(TTSProcessPlayer):
    def __init__(self, taskman: TaskManager, addon: LocalTTSAddon) -> None:
        super().__init__(taskman)
        self._addon = addon
        self._notified_errors: set[str] = set()

    def reset_notifications(self) -> None:
        """Clear the throttle set; called after config reload so the user
        sees the new error context if it still applies."""
        self._notified_errors.clear()

    def _notify_once(self, key: str, message: str) -> None:
        if key in self._notified_errors:
            return
        self._notified_errors.add(key)
        try:
            from aqt import mw
            from aqt.utils import tooltip
            mw.taskman.run_on_main(lambda: tooltip(message, period=6000))
        except Exception:
            pass

    def get_available_voices(self) -> List[TTSVoice]:
        return [TTSVoice(name=VOICE_NAME, lang=lang) for lang in SUPPORTED_LANGS]

    def _play(self, tag: AVTag) -> None:
        self.audio_file_path = None
        assert isinstance(tag, TTSTag)
        text = tag.field_text
        log.debug("_play tag.lang=%s text=%r", getattr(tag, "lang", None), text[:80])
        if not text or not text.strip():
            log.debug("empty text, skipping")
            return

        preset = self._resolve_preset(tag)
        if preset is None:
            log.warning("no preset resolved (lang=%s) — check routing/default_preset",
                        getattr(tag, "lang", None))
            return
        log.debug("resolved preset=%s provider=%s", preset.name, preset.provider)

        cfg = self._addon.config
        cleanup_opts = preset.cleanup if preset.cleanup is not None else cfg.cleanup
        # Empty list is treated as "no override" — older versions saved an
        # empty list for every preset regardless of override intent, and an
        # opt-in override with zero rows is indistinguishable from inherit.
        rules = preset.regex_rules if preset.regex_rules else cfg.regex_rules
        processed = regex_rules.apply(cleanup.clean(text, cleanup_opts), rules)
        if getattr(cfg, "digits_to_kanji", True):
            processed = digit_kanji.convert(processed)
            # New kanji may neighbour a space that survived the initial
            # cleanup pass (e.g. `7 月` → `七 月`); re-collapse so the
            # provider sees a single token.
            if cleanup_opts.collapse_cjk_spaces:
                processed = cleanup.collapse_cjk_spaces(processed)
        if getattr(cfg, "split_digits_auto", False):
            processed = auto_marker.auto_mark_digit_pauses(processed, getattr(cfg, "split_marker", ""))
        if not processed.strip():
            log.debug("text empty after cleanup, skipping")
            return
        log.debug("processed text=%r", processed[:80])

        # Marker-based chunking only affects audio when the marker is
        # actually in the text — for unrelated cards the cache key, and
        # therefore any pre-existing audio, is unchanged. We always chunk
        # when the marker is present (even at length 0) — folding the two
        # chunks into one synth call would let VOICEVOX read e.g.
        # `三・四倍` as `三十四倍` because `三四` parses as one number.
        #
        # `getattr` fallbacks defend against a half-reloaded addon where
        # a stale `Config` class from an older version is still in memory
        # and the runtime code references fields it doesn't have.
        split_marker = getattr(cfg, "split_marker", "")
        split_pause_length = getattr(cfg, "split_pause_length", 0.03)
        marker = split_marker if split_marker and split_marker in processed else None
        extra = f"split={marker}|{split_pause_length}" if marker else ""
        # Resolve inherit-from-global keys (volume, speed, pitch, ...) so the
        # cache key and the provider both see the effective bag.
        effective = preset.with_defaults(getattr(cfg, "voice_defaults", {}))
        key = self._addon.cache.key(effective, processed, extra=extra)
        cached = self._addon.cache.get(key)
        if cached is None:
            provider = self._addon.providers.get(preset.provider)
            if provider is None:
                log.error("unknown provider %r in preset %r", preset.provider, preset.name)
                return
            provider_settings = self._addon.config.provider_settings.get(preset.provider, {})
            try:
                data = provider.synthesize(
                    processed, effective, provider_settings,
                    split_marker=marker,
                    split_pause_length=cfg.split_pause_length,
                )
            except ProviderError as exc:
                log.error("synth failed: %s", exc)
                self._notify_once(f"{preset.provider}:{type(exc).__name__}", f"Local TTS: {exc}")
                return
            cached = self._addon.cache.put(key, data)
            log.info("cache miss → wrote %s (%d bytes)", cached.name, cached.stat().st_size)
        else:
            log.debug("cache hit %s", cached.name)

        self.audio_file_path = str(cached)

    def _on_done(self, ret: Future, cb: OnDoneCallback) -> None:
        """Called on the main thread after `_play` finishes.

        Anki's default `TTSProcessPlayer._on_done` does not enqueue the
        synthesized file with `av_player`, so nothing plays. We push the
        file to the front of the queue, then call `cb()` to advance.
        Mirrors AwesomeTTS's `ttsplayer.py:_on_done`.
        """
        try:
            ret.result()
        except Exception as exc:
            log.error("_play raised: %s", exc)
        if self.audio_file_path:
            log.debug("av_player.insert_file %s", self.audio_file_path)
            av_player.insert_file(self.audio_file_path)
        cb()

    def stop(self) -> None:
        pass

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
