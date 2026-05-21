"""Persisted addon configuration.

Two dataclasses: `RoutingConfig` (the deck/notetype/language → preset
lookup tables) and `Config` (the full settings blob). Loaded from and
saved to Anki's per-addon JSON via `mw.addonManager`. The on-disk shape
mirrors `config.json` in the project root, which Anki uses as defaults
on first install.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .presets import Preset


@dataclass
class RoutingConfig:
    """Routing tables consulted in order: deck → notetype → language."""

    by_deck: dict[str, str] = field(default_factory=dict)
    by_notetype: dict[str, str] = field(default_factory=dict)
    by_language: dict[str, str] = field(default_factory=dict)


@dataclass
class Config:
    """Full addon config. Fields map 1:1 to keys in `config.json`."""
    enabled: bool = True
    default_preset: str = ""
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    presets: list[Preset] = field(default_factory=list)
    cache_dir: Path = field(default_factory=lambda: Path("user_files/cache"))
    cache_max_mb: int = 200
    ffmpeg_path: str | None = None
    addon_dir: Path = field(default_factory=Path)

    @classmethod
    def load(cls) -> Config:
        """Read config from Anki; return defaults if not running inside Anki.

        Relative paths in the config (e.g. `cache.dir: "user_files/cache"`)
        are resolved against the addon's own folder — Anki's CWD at addon
        load is its app bundle, which is read-only on macOS.
        """
        addon_dir: Path | None = None
        try:
            from aqt import mw
            raw = mw.addonManager.getConfig(__package__) or {}
            addon_dir = Path(mw.addonManager.addonsFolder(__package__))
        except Exception:
            raw = {}
        cfg = cls.from_dict(raw)
        if addon_dir is not None:
            cfg.addon_dir = addon_dir
            if not cfg.cache_dir.is_absolute():
                cfg.cache_dir = addon_dir / cfg.cache_dir
        return cfg

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Config:
        routing_raw = raw.get("routing", {})
        routing = RoutingConfig(
            by_deck=dict(routing_raw.get("by_deck", {})),
            by_notetype=dict(routing_raw.get("by_notetype", {})),
            by_language=dict(routing_raw.get("by_language", {})),
        )
        presets = [Preset.from_dict(p) for p in raw.get("presets", [])]
        cache_raw = raw.get("cache", {})
        return cls(
            enabled=raw.get("enabled", True),
            default_preset=raw.get("default_preset", ""),
            routing=routing,
            presets=presets,
            cache_dir=Path(cache_raw.get("dir", "user_files/cache")),
            cache_max_mb=int(cache_raw.get("max_mb", 200)),
            ffmpeg_path=raw.get("ffmpeg_path") or None,
        )

    def save(self) -> None:
        from aqt import mw
        mw.addonManager.writeConfig(__package__, self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "default_preset": self.default_preset,
            "routing": {
                "by_deck": self.routing.by_deck,
                "by_notetype": self.routing.by_notetype,
                "by_language": self.routing.by_language,
            },
            "presets": [p.to_dict() for p in self.presets],
            "cache": {"dir": str(self.cache_dir), "max_mb": self.cache_max_mb},
            "ffmpeg_path": self.ffmpeg_path,
        }

    def preset_by_name(self, name: str) -> Preset | None:
        return next((p for p in self.presets if p.name == name), None)

    def validation_errors(self) -> list[str]:
        """Return human-readable errors for the loaded config.

        Currently checks regex pattern compilability per preset. Intended
        for the settings dialog ("3 rules invalid in preset X") and for
        an at-load warning when running inside Anki.
        """
        from .text.regex_rules import validate_rules

        msgs: list[str] = []
        for preset in self.presets:
            for rule, err in validate_rules(preset.regex_rules):
                msgs.append(f"Preset {preset.name!r}: pattern {rule.pattern!r}: {err}")
        return msgs


def canonical_json(obj: Any) -> str:
    """Stable JSON serialization for hashing — sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
