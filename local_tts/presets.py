"""Preset data model.

A `Preset` is a voice configuration: provider + options. Cleanup flags
and regex rules live globally on `Config`; a preset may *optionally*
override either with its own block (`cleanup` / `regex_rules` set to
non-None on the preset wins over the global value).

`fingerprint()` covers only `provider` + `options`. Cleanup and regex
rules — global or per-preset — only act by transforming text, so their
effect is already captured by the processed-text dimension of the cache
key. Editing them doesn't invalidate audio for unaffected text.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RegexRule:
    """One user-defined `re.sub(pattern, replacement, text)` step."""
    pattern: str
    replacement: str
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"pattern": self.pattern, "replacement": self.replacement, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RegexRule:
        return cls(
            pattern=raw["pattern"],
            replacement=raw.get("replacement", ""),
            enabled=raw.get("enabled", True),
        )


@dataclass
class CleanupOptions:
    """Per-preset flags driving the built-in cleanup pipeline.

    `ruby_mode` / `bracket_mode`: pick the base char or the reading
    (`日々[ひび]` → `日々` or `ひび`). `strip_brackets_only` keeps both.
    `brackets` lists the bracket pairs to consider (`"[]"`, `"()"`...).
    """

    ruby_mode: str = "base"           # base | reading
    bracket_mode: str = "base"        # base | reading | strip_brackets_only
    brackets: list[str] = field(default_factory=lambda: ["[]", "()"])
    collapse_cjk_spaces: bool = True  # drop spaces between two Japanese chars

    def to_dict(self) -> dict[str, Any]:
        return {
            "ruby_mode": self.ruby_mode,
            "bracket_mode": self.bracket_mode,
            "brackets": list(self.brackets),
            "collapse_cjk_spaces": self.collapse_cjk_spaces,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CleanupOptions:
        return cls(
            ruby_mode=raw.get("ruby_mode", "base"),
            bracket_mode=raw.get("bracket_mode", "base"),
            brackets=list(raw.get("brackets", ["[]", "()"])),
            collapse_cjk_spaces=raw.get("collapse_cjk_spaces", True),
        )


@dataclass
class Preset:
    """A named TTS configuration referenced by the routing table.

    `provider` selects an entry in `ProviderRegistry`; `options` is the
    provider-specific bag (voice id, speed...). Providers must never see
    fields outside `options` — that's the abstraction line.
    """

    name: str
    provider: str
    options: dict[str, Any] = field(default_factory=dict)
    cleanup: CleanupOptions | None = None
    regex_rules: list[RegexRule] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "provider": self.provider,
            "options": dict(self.options),
        }
        if self.cleanup is not None:
            out["cleanup"] = self.cleanup.to_dict()
        if self.regex_rules is not None:
            out["regex_rules"] = [r.to_dict() for r in self.regex_rules]
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Preset:
        cleanup = CleanupOptions.from_dict(raw["cleanup"]) if "cleanup" in raw else None
        regex_rules = (
            [RegexRule.from_dict(r) for r in raw["regex_rules"]]
            if "regex_rules" in raw else None
        )
        return cls(
            name=raw["name"],
            provider=raw["provider"],
            options=dict(raw.get("options", {})),
            cleanup=cleanup,
            regex_rules=regex_rules,
        )

    def with_defaults(self, voice_defaults: dict[str, Any]) -> Preset:
        """Return a copy whose `options` are merged onto `voice_defaults`.

        Keys present (and non-None) on `self.options` override the global
        default; absent keys inherit. Used at synthesis time so the cache
        fingerprint and the provider see the same resolved bag.
        """
        merged: dict[str, Any] = dict(voice_defaults)
        for k, v in self.options.items():
            if v is not None:
                merged[k] = v
        return Preset(
            name=self.name,
            provider=self.provider,
            options=merged,
            cleanup=self.cleanup,
            regex_rules=self.regex_rules,
        )

    def fingerprint(self) -> str:
        """Stable hash of `provider` + `options`; drives cache keys.

        Cleanup and regex rules are NOT included — they only act by
        transforming text, and that effect is already captured by the
        processed-text dimension of the cache key. Renaming a preset
        also doesn't change the fingerprint.
        """
        payload = json.dumps(
            {"provider": self.provider, "options": self.options},
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
