"""Runtime audio cache.

Stores synthesized audio under `user_files/cache/` (never the Anki
`collection.media` folder). Keys are `sha256(preset.fingerprint() ‖ text)`,
so editing any preset field transparently invalidates derived entries.
Eviction is LRU by file `atime`, bounded by `max_mb`.

Providers return WAV. We transcode to Opus on write if ffmpeg is on PATH —
~10× smaller for speech, indistinguishable in quality. If ffmpeg is
missing we fall back to storing WAV so the addon still works.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from functools import cache
from pathlib import Path

from .presets import Preset

CACHE_EXTS = ("opus", "wav")


@cache
def _ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")  # pyright: ignore[reportDeprecated]


def _encode_opus(wav_bytes: bytes) -> bytes | None:
    """WAV → Opus/Ogg via ffmpeg subprocess. Returns None on any failure."""
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        return None
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error",
             "-f", "wav", "-i", "pipe:0",
             "-c:a", "libopus", "-b:a", "32k", "-vbr", "on",
             "-application", "voip",
             "-f", "ogg", "pipe:1"],
            input=wav_bytes, capture_output=True, timeout=15, check=True,
        )
        return proc.stdout or None
    except (subprocess.SubprocessError, OSError):
        return None


class AudioCache:
    """Disk-backed audio cache with LRU eviction."""

    def __init__(self, cache_dir: Path, max_mb: int) -> None:
        self.cache_dir = Path(cache_dir)
        self.max_bytes = max_mb * 1024 * 1024
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(preset: Preset, processed_text: str) -> str:
        """Cache key bound to both the preset config and the post-cleanup text."""
        h = hashlib.sha256()
        h.update(preset.fingerprint().encode("utf-8"))
        h.update(b"\x00")
        h.update(processed_text.encode("utf-8"))
        return h.hexdigest()

    def get(self, key: str) -> Path | None:
        """Return the cached file (any supported format), or None on miss."""
        for ext in CACHE_EXTS:
            p = self.cache_dir / f"{key}.{ext}"
            if p.exists():
                p.touch()
                return p
        return None

    def put(self, key: str, wav_bytes: bytes) -> Path:
        """Write WAV bytes to the cache; transcodes to Opus when possible."""
        opus = _encode_opus(wav_bytes)
        if opus is not None:
            return self._write(key, "opus", opus)
        return self._write(key, "wav", wav_bytes)

    def _write(self, key: str, ext: str, data: bytes) -> Path:
        p = self.cache_dir / f"{key}.{ext}"
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)
        self._evict_if_needed()
        return p

    def _evict_if_needed(self) -> None:
        files = [(f, f.stat()) for f in self.cache_dir.iterdir() if f.is_file()]
        total = sum(s.st_size for _, s in files)
        if total <= self.max_bytes:
            return
        files.sort(key=lambda fs: fs[1].st_atime)
        for f, s in files:
            if total <= self.max_bytes:
                break
            try:
                f.unlink()
                total -= s.st_size
            except OSError:
                pass
