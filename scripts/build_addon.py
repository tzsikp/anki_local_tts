"""Build dist/local_tts.ankiaddon from the local_tts/ package.

The .ankiaddon format is a flat zip of the addon folder's contents
(no wrapping directory). Users install by double-clicking the file.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "local_tts"
DIST = ROOT / "dist"


def _version() -> str:
    raw = json.loads((PKG / "manifest.json").read_text(encoding="utf-8"))
    return str(raw.get("human_version") or "").strip()

EXCLUDE_DIRS = {"__pycache__", "user_files", ".pytest_cache"}
EXCLUDE_NAMES = {"meta.json", ".DS_Store"}


def iter_files() -> list[tuple[Path, str]]:
    """Yield (source_path, arcname) pairs for everything that goes in the zip."""
    items: list[tuple[Path, str]] = []
    for src in PKG.rglob("*"):
        if not src.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in src.parts):
            continue
        if src.name in EXCLUDE_NAMES:
            continue
        items.append((src, str(src.relative_to(PKG))))
    return items


def main() -> int:
    if not (PKG / "manifest.json").exists():
        print(f"missing {PKG / 'manifest.json'}", file=sys.stderr)
        return 1
    version = _version()
    if not version:
        print("manifest.json missing human_version", file=sys.stderr)
        return 1
    DIST.mkdir(exist_ok=True)
    out = DIST / f"local_tts-{version}.ankiaddon"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in iter_files():
            zf.write(src, arc)
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
