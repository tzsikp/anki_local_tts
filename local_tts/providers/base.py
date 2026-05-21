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

from typing import Any, Protocol

from ..presets import Preset


class ProviderError(Exception):
    """Raised by providers on synthesis failure. The player swallows these
    and skips playback rather than crashing the reviewer."""


class Provider(Protocol):
    """Contract every TTS adapter must satisfy."""

    name: str

    def options_schema(self) -> dict[str, Any]:
        """Describe the provider's preset options; drives the GUI editor."""

    def synthesize(self, text: str, preset: Preset) -> bytes:
        """Return WAV bytes. Raise `ProviderError` on any failure."""

    def health_check(self, preset: Preset) -> tuple[bool, str]:
        """Quick liveness check for the settings dialog's Test button."""
