"""Provider abstraction.

A `Provider` is the only thing that knows how to talk to a specific TTS
engine. Adding a new engine (Piper, Style-Bert-VITS2, ...) means writing
one file in this package and registering it — nothing outside
`providers/` should ever import a concrete provider.

Providers must be effectively stateless: instantiating one is cheap and
they only ever see `(text, preset.options)`. They never see decks,
note-types, the cache, or the cleanup pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..presets import Preset


class ProviderError(Exception):
    """Raised by providers on synthesis failure. The player swallows these
    and skips playback rather than crashing the reviewer."""


@dataclass
class VoiceInfo:
    """One selectable voice fetched live from a provider's server.

    `label` is what the picker shows. `options` is the partial options
    dict to merge into a new preset (e.g. `{"speaker_id": 8}`).
    """

    label: str
    options: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


class Provider(Protocol):
    """Contract every TTS adapter must satisfy."""

    name: str
    display_name: str        # human-readable, e.g. "VOICEVOX"
    display_language: str    # human-readable default language, e.g. "Japanese"; "" if multi-lang

    def options_schema(self) -> dict[str, Any]:
        """Describe the provider's preset options; drives the GUI editor."""

    def synthesize(self, text: str, preset: Preset) -> bytes:
        """Return WAV bytes. Raise `ProviderError` on any failure."""

    def health_check(self, preset: Preset) -> tuple[bool, str]:
        """Quick liveness check for the settings dialog's Test button."""

    def voices(self, options: dict[str, Any]) -> list[VoiceInfo]:
        """Query the live server for selectable voices. May raise ProviderError.
        Providers without a discovery endpoint return an empty list."""
