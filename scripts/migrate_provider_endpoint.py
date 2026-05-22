"""One-shot migration: hoist `endpoint` off preset.options into provider_settings.

Run once against any config JSON that predates the provider-settings split.
Idempotent — safe to re-run.

Usage:
    uv run python scripts/migrate_provider_endpoint.py [path/to/config.json ...]

Defaults to `local_tts/config.json` and `local_tts/meta.json` (the live
user config Anki writes through the dev symlink) if both exist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS = [ROOT / "local_tts" / "config.json", ROOT / "local_tts" / "meta.json"]
HOISTED = {"voicevox": ("endpoint",)}


def migrate(raw: dict) -> tuple[dict, int]:
    """Return `(migrated_dict, hoist_count)`. Existing provider_settings win."""
    provider_settings: dict[str, dict] = dict(raw.get("provider_settings") or {})
    moved = 0
    for preset in raw.get("presets", []):
        provider = preset.get("provider")
        options = preset.get("options") or {}
        for key in HOISTED.get(provider, ()):
            if key not in options:
                continue
            value = options.pop(key)
            slot = provider_settings.setdefault(provider, {})
            slot.setdefault(key, value)
            moved += 1
        preset["options"] = options
    raw["provider_settings"] = provider_settings
    return raw, moved


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv] or [p for p in DEFAULTS if p.exists()]
    if not paths:
        print("nothing to do — no config files found")
        return 0
    for path in paths:
        if not path.exists():
            print(f"skip {path} (missing)")
            continue
        original = json.loads(path.read_text())
        migrated, moved = migrate(original)
        if moved == 0:
            print(f"{path}: already migrated")
            continue
        path.write_text(json.dumps(migrated, indent=4, ensure_ascii=False) + "\n")
        print(f"{path}: moved {moved} key(s) into provider_settings")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
