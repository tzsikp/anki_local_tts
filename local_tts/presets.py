"""Preset data model.

A `Preset` bundles everything needed to turn a piece of card text into
audio: which provider to call, that provider's options, the cleanup
flags, and a list of user-defined regex rewrites. Presets are the unit
of cache invalidation — their `fingerprint()` is the sha256 of their
canonical JSON and is part of every cache key, so editing any field
transparently invalidates derived audio.
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
    provider-specific bag (voice id, endpoint, speed...). Providers must
    never see fields outside `options` — that's the abstraction line.
    """

    name: str
    provider: str
    options: dict[str, Any] = field(default_factory=dict)
    cleanup: CleanupOptions = field(default_factory=CleanupOptions)
    regex_rules: list[RegexRule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "options": dict(self.options),
            "cleanup": self.cleanup.to_dict(),
            "regex_rules": [r.to_dict() for r in self.regex_rules],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Preset:
        return cls(
            name=raw["name"],
            provider=raw["provider"],
            options=dict(raw.get("options", {})),
            cleanup=CleanupOptions.from_dict(raw.get("cleanup", {})),
            regex_rules=[RegexRule.from_dict(r) for r in raw.get("regex_rules", [])],
        )

    def fingerprint(self) -> str:
        """Stable hash of the preset's canonical JSON; drives cache keys.

        Any change to provider/options/cleanup/regex flips the fingerprint,
        which invalidates every cache entry derived from this preset.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
