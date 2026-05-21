import shutil
import struct
import wave
from pathlib import Path

import pytest

from local_tts.cache import AudioCache
from local_tts.presets import Preset


def _wav_bytes(seconds: float = 0.2, freq: int = 440, rate: int = 24000) -> bytes:
    import io
    import math
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        frames = b"".join(
            struct.pack("<h", int(0.2 * 32767 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(n)
        )
        w.writeframes(frames)
    return buf.getvalue()


@pytest.fixture
def cache(tmp_path: Path) -> AudioCache:
    return AudioCache(tmp_path / "cache", max_mb=10)


def test_put_then_get_roundtrip(cache: AudioCache):
    preset = Preset(name="p", provider="voicevox")
    key = cache.key(preset, "こんにちは")
    p = cache.put(key, _wav_bytes())
    assert p.exists()
    got = cache.get(key)
    assert got is not None and got == p


def test_get_miss(cache: AudioCache):
    assert cache.get("deadbeef") is None


def test_uses_opus_when_ffmpeg_available(cache: AudioCache):
    if shutil.which("ffmpeg") is None:  # pyright: ignore[reportDeprecated]
        pytest.skip("ffmpeg not installed")
    preset = Preset(name="p", provider="voicevox")
    key = cache.key(preset, "テスト")
    p = cache.put(key, _wav_bytes())
    assert p.suffix == ".opus"
    assert p.stat().st_size < len(_wav_bytes())


def test_falls_back_to_wav_without_ffmpeg(monkeypatch, cache: AudioCache):
    monkeypatch.setattr("local_tts.cache._encode_opus", lambda _b: None)
    preset = Preset(name="p", provider="voicevox")
    key = cache.key(preset, "テスト")
    p = cache.put(key, _wav_bytes())
    assert p.suffix == ".wav"


def test_key_changes_with_preset_or_text(cache: AudioCache):
    a = Preset(name="a", provider="voicevox", options={"speed": 1.0})
    b = Preset(name="a", provider="voicevox", options={"speed": 0.9})
    assert cache.key(a, "x") != cache.key(b, "x")
    assert cache.key(a, "x") != cache.key(a, "y")
