"""Provider registry — the only module outside `providers/` allowed to
know which concrete adapters exist. Everything else looks them up by
name via `ProviderRegistry.get(preset.provider)`."""

from __future__ import annotations

from .base import Provider, ProviderError
from .voicevox import VoicevoxProvider


class ProviderRegistry:
    """Name → Provider lookup. Build via `default()` for the standard set."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider | None:
        return self._providers.get(name)

    def names(self) -> list[str]:
        return sorted(self._providers)

    @classmethod
    def default(cls) -> ProviderRegistry:
        """Registry preloaded with every built-in provider."""
        reg = cls()
        reg.register(VoicevoxProvider())
        return reg


__all__ = ["Provider", "ProviderError", "ProviderRegistry", "VoicevoxProvider"]
