"""Symlink local_tts/ into Anki's addons21 folder for live development.

Anki loads addons from a per-OS directory and reloads Python modules only
at startup, so the dev loop is: edit -> restart Anki. Use --unlink to
remove the symlink.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "local_tts"
ADDON_NAME = "local_tts"


def addons_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Anki2" / "addons21"
    if sys.platform.startswith("win"):
        return Path(os.environ["APPDATA"]) / "Anki2" / "addons21"
    return Path.home() / ".local" / "share" / "Anki2" / "addons21"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unlink", action="store_true", help="remove the symlink and exit")
    args = ap.parse_args()

    dest = addons_dir() / ADDON_NAME

    if args.unlink:
        if not dest.exists() and not dest.is_symlink():
            print(f"not installed at {dest}")
            return 0
        if not dest.is_symlink():
            print(f"refusing to remove {dest}: not a symlink", file=sys.stderr)
            return 1
        dest.unlink()
        print(f"unlinked {dest}")
        return 0

    if not PKG.exists():
        print(f"missing {PKG}", file=sys.stderr)
        return 1
    if not (PKG / "manifest.json").exists():
        print(f"missing {PKG / 'manifest.json'} — addon will not load", file=sys.stderr)
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.is_symlink():
        current = dest.resolve()
        if current == PKG.resolve():
            print(f"already linked: {dest} -> {current}")
            return 0
        print(f"refusing to overwrite existing symlink at {dest} (-> {current})", file=sys.stderr)
        print("remove it first or run --unlink", file=sys.stderr)
        return 1
    if dest.exists():
        print(f"refusing to overwrite real directory at {dest}", file=sys.stderr)
        print("looks like a manually-installed copy; remove it via Anki's add-on dialog first", file=sys.stderr)
        return 1

    dest.symlink_to(PKG, target_is_directory=True)
    print(f"linked {dest} -> {PKG}")
    print("restart Anki to pick up the addon")
    return 0


if __name__ == "__main__":
    sys.exit(main())
