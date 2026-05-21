"""Top-level wiring for the Local TTS Anki add-on.

`LocalTTSAddon` is the composition root: it loads config, builds the
provider registry and cache, and registers our `TTSProcessPlayer` with
Anki's `av_player`. One instance is created at addon load time (see
`__init__.py`); everything else hangs off it.
"""

from __future__ import annotations

from .cache import AudioCache
from .config import Config
from .player import LocalTTSPlayer
from .providers import ProviderRegistry
from .routing import Router


class LocalTTSAddon:
    """Owns the addon's singletons and wires them to Anki at install time."""

    def __init__(self) -> None:
        self.config = Config.load()
        self.providers = ProviderRegistry.default()
        self.cache = AudioCache(self.config.cache_dir, self.config.cache_max_mb)
        self.router = Router(self.config)
        self.player: LocalTTSPlayer | None = None

    def install(self) -> None:
        """Register our TTS player with Anki. Safe to call once per session."""
        from aqt import mw
        from aqt.sound import av_player
        from aqt.utils import showWarning

        for msg in self.config.validation_errors():
            showWarning(f"Local TTS: {msg}", title="Local TTS")

        self.player = LocalTTSPlayer(mw.taskman, self)
        av_player.players.append(self.player)
