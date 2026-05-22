"""Top-level wiring for the Local TTS Anki add-on.

`LocalTTSAddon` is the composition root: it loads config, builds the
provider registry and cache, and registers our `TTSProcessPlayer` with
Anki's `av_player`. One instance is created at addon load time (see
`__init__.py`); everything else hangs off it.
"""

from __future__ import annotations

from ._log import configure as _configure_log, log
from .cache import AudioCache
from .config import Config
from .player import LocalTTSPlayer
from .providers import ProviderRegistry
from .routing import Router

MENU_ENTRY = "Local TTS settings…"


class LocalTTSAddon:
    """Owns the addon's singletons and wires them to Anki at install time."""

    def __init__(self) -> None:
        self.config = Config.load()
        _configure_log(self.config.addon_dir)
        log.info("addon init; addon_dir=%s cache_dir=%s presets=%d default=%r",
                 self.config.addon_dir, self.config.cache_dir,
                 len(self.config.presets), self.config.default_preset)
        self.providers = ProviderRegistry.default()
        self.cache = AudioCache(self.config.cache_dir, self.config.cache_max_mb,
                                ffmpeg_override=self.config.ffmpeg_path)
        self.router = Router(self.config)
        self.player: LocalTTSPlayer | None = None

    def install(self) -> None:
        """Register our TTS player with Anki. Safe to call once per session."""
        from aqt import mw
        from aqt.sound import av_player
        from aqt.utils import showWarning

        for msg in self.config.validation_errors():
            log.warning("config validation: %s", msg)
            showWarning(f"Local TTS: {msg}", title="Local TTS")

        self.player = LocalTTSPlayer(mw.taskman, self)
        av_player.players.append(self.player)
        log.info("registered TTSProcessPlayer with av_player")

        self._install_menu()

    def _install_menu(self) -> None:
        from aqt import mw
        from aqt.qt import QAction, QMenu

        action = QAction(MENU_ENTRY, mw)
        action.triggered.connect(self.open_settings)
        mw.form.menuTools.addAction(action)

        self._routes_menu = QMenu("Local TTS · Routes", mw)
        self._routes_menu.aboutToShow.connect(self._rebuild_routes_menu)
        mw.form.menuTools.addMenu(self._routes_menu)

    def _rebuild_routes_menu(self) -> None:
        from aqt.qt import QAction

        menu = self._routes_menu
        menu.clear()

        cfg = self.config
        preset_names = [p.name for p in cfg.presets]
        if not preset_names:
            placeholder = QAction("(no presets — create one in Settings)", menu)
            placeholder.setEnabled(False)
            menu.addAction(placeholder)
            return

        default_sub = menu.addMenu("Default")
        self._fill_preset_choices(default_sub, preset_names, cfg.default_preset, self._set_default)

        deck_names = self._deck_id_to_name()
        notetype_names = self._notetype_id_to_name()

        def _section(title: str, entries: list[tuple[str, str]], setter):
            sub = menu.addMenu(title)
            if not entries:
                empty = sub.addAction("(none configured)")
                empty.setEnabled(False)
                return
            for key, current in entries:
                row = sub.addMenu(key)
                self._fill_preset_choices(row, preset_names, current,
                                          lambda name, k=key: setter(k, name))

        by_lang = sorted(cfg.routing.by_language.items())
        _section("By Language", by_lang,
                 lambda key, name: self._set_routing("by_language", key, name))

        by_nt = sorted(
            ((notetype_names.get(k, f"(id {k})"), v) for k, v in cfg.routing.by_notetype.items()),
            key=lambda kv: kv[0].lower(),
        )
        # Note: by_notetype dict keys are IDs, but submenu labels show names; map back on click.
        nt_name_to_id = {notetype_names.get(k, f"(id {k})"): k for k in cfg.routing.by_notetype}
        _section("By Note Type", by_nt,
                 lambda key, name: self._set_routing("by_notetype", nt_name_to_id[key], name))

        by_deck = sorted(
            ((deck_names.get(k, f"(id {k})"), v) for k, v in cfg.routing.by_deck.items()),
            key=lambda kv: kv[0].lower(),
        )
        deck_name_to_id = {deck_names.get(k, f"(id {k})"): k for k in cfg.routing.by_deck}
        _section("By Deck", by_deck,
                 lambda key, name: self._set_routing("by_deck", deck_name_to_id[key], name))

    def _fill_preset_choices(self, submenu, names: list[str], current: str, handler) -> None:
        from aqt.qt import QActionGroup
        group = QActionGroup(submenu)
        group.setExclusive(True)
        for name in names:
            action = submenu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == current)
            group.addAction(action)
            action.triggered.connect(lambda _checked=False, n=name: handler(n))

    def _deck_id_to_name(self) -> dict[str, str]:
        try:
            from aqt import mw
            return {str(d.id): d.name for d in mw.col.decks.all_names_and_ids()}
        except Exception:
            return {}

    def _notetype_id_to_name(self) -> dict[str, str]:
        try:
            from aqt import mw
            return {str(n.id): n.name for n in mw.col.models.all_names_and_ids()}
        except Exception:
            return {}

    def _set_default(self, name: str) -> None:
        self.config.default_preset = name
        self._persist_quick_switch(f"default → {name}")

    def _set_routing(self, table: str, key: str, name: str) -> None:
        getattr(self.config.routing, table)[key] = name
        self._persist_quick_switch(f"routing.{table}[{key}] → {name}")

    def _persist_quick_switch(self, summary: str) -> None:
        self.config.save()
        self.router = Router(self.config)
        if self.player is not None:
            self.player.reset_notifications()
        log.info("quick switch: %s", summary)
        try:
            from aqt import mw
            from aqt.utils import tooltip
            mw.taskman.run_on_main(lambda: tooltip(f"Local TTS: {summary}", period=3000))
        except Exception:
            pass

    def open_settings(self) -> None:
        from .gui import open_settings
        open_settings(self)

    def apply_config(self, new_cfg: Config) -> None:
        """Replace the running config and rebuild dependent state.

        Called by the settings dialog after Save. Writes config.json,
        rebuilds the cache (which re-checks ffmpeg) and the router, so
        the next playback uses the new config without an Anki restart.
        """
        new_cfg.save()
        self.config = new_cfg
        self.cache = AudioCache(new_cfg.cache_dir, new_cfg.cache_max_mb,
                                ffmpeg_override=new_cfg.ffmpeg_path)
        self.router = Router(new_cfg)
        if self.player is not None:
            self.player.reset_notifications()
        log.info("config reloaded; presets=%d default=%r",
                 len(new_cfg.presets), new_cfg.default_preset)
