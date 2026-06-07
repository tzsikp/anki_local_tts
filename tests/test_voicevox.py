"""VOICEVOX provider + audio.concat_wavs + split-marker integration."""
from __future__ import annotations

import io
import wave

import pytest

from local_tts.audio import concat_wavs
from local_tts.providers.voicevox import VoicevoxProvider


def _wav(samples: int = 240, framerate: int = 24000) -> bytes:
    """A `samples`-frame, 24kHz, 16-bit mono WAV of silence — VOICEVOX's format."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(b"\x00\x00" * samples)
    return out.getvalue()


def _frames(wav: bytes) -> int:
    with wave.open(io.BytesIO(wav), "rb") as r:
        return r.getnframes()


# ---- audio.concat_wavs ----

def test_concat_single_wav_returns_input():
    a = _wav(100)
    assert concat_wavs([a]) == a


def test_concat_two_wavs_joins_frames():
    a = _wav(100)
    b = _wav(150)
    out = concat_wavs([a, b])
    assert _frames(out) == 250


def test_concat_inserts_silence_between_chunks():
    a = _wav(100)
    b = _wav(100)
    # 0.01s at 24000Hz = 240 frames of silence between two 100-frame chunks
    out = concat_wavs([a, b], silence_seconds=0.01)
    assert _frames(out) == 100 + 240 + 100


def test_concat_zero_silence_is_seamless():
    a, b = _wav(50), _wav(50)
    assert _frames(concat_wavs([a, b], 0.0)) == 100


def test_concat_rejects_format_mismatch():
    a = _wav(100, framerate=24000)
    b = _wav(100, framerate=48000)
    with pytest.raises(ValueError, match="format mismatch"):
        concat_wavs([a, b])


def test_concat_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        concat_wavs([])


# ---- VoicevoxProvider._split ----

def test_split_no_marker_returns_whole_text():
    assert VoicevoxProvider._split("年に一、二回", None) == ["年に一、二回"]
    assert VoicevoxProvider._split("年に一、二回", "") == ["年に一、二回"]


def test_split_marker_absent_returns_whole_text():
    assert VoicevoxProvider._split("年に一、二回", "・") == ["年に一、二回"]


def test_split_marker_present_splits():
    assert VoicevoxProvider._split("年に一・二回", "・") == ["年に一", "二回"]


def test_split_drops_empty_chunks_from_double_marker():
    # `・・` and leading/trailing markers shouldn't produce empty chunks.
    assert VoicevoxProvider._split("・年に一・・二回・", "・") == ["年に一", "二回"]


def test_split_marker_only_falls_back_to_full_text():
    # All chunks empty → don't produce zero chunks (would crash concat).
    assert VoicevoxProvider._split("・・・", "・") == ["・・・"]


# ---- config split fields roundtrip ----

def test_config_split_defaults():
    from local_tts.config import Config

    cfg = Config.from_dict({})
    assert cfg.split_marker == "・"
    assert cfg.split_pause_length == 0.03


def test_config_split_roundtrip():
    from local_tts.config import Config

    raw = {"split_marker": "|", "split_pause_length": 0.1}
    cfg = Config.from_dict(raw)
    assert cfg.split_marker == "|"
    assert cfg.split_pause_length == 0.1
    out = cfg.to_dict()
    assert out["split_marker"] == "|"
    assert out["split_pause_length"] == 0.1


# ---- cache key folds the split config in only when marker is present ----

def test_cache_key_unchanged_for_non_matching_text():
    from local_tts.cache import AudioCache
    from local_tts.presets import Preset

    p = Preset(name="p", provider="voicevox", options={"speaker_id": 1})
    # No `extra` ⇒ identical to pre-feature key, so old cache survives.
    assert AudioCache.key(p, "こんにちは") == AudioCache.key(p, "こんにちは", extra="")


def test_zero_pause_still_chunks_to_preserve_digit_boundaries():
    """At length=0 we still chunk so /accent_phrases parses each side
    independently. Folding into one /audio_query would let VOICEVOX read
    `三・四倍` as `三十四倍` (thirty-four times), losing the user's intent.
    The merged-prosody path (per-chunk /accent_phrases → /mora_data →
    /synthesis) gives a zero-gap join *and* correct number parsing."""
    assert VoicevoxProvider._split("三・四倍", "・") == ["三", "四倍"]


def test_pause_mora_shape_matches_engine_format():
    from local_tts.providers.voicevox import _pause_mora

    m = _pause_mora(0.03)
    assert m["vowel"] == "pau"
    assert m["vowel_length"] == 0.03
    assert m["consonant"] is None
    assert m["text"] == "、"


def test_audio_query_base_has_required_synthesis_fields():
    """`_synth_merged` builds the query from `_AUDIO_QUERY_BASE` + scales +
    accent_phrases. /synthesis rejects an AudioQuery missing any of the
    output/phoneme/pause fields, so this defends against accidentally
    dropping one."""
    from local_tts.providers.voicevox import _AUDIO_QUERY_BASE

    required = {"outputSamplingRate", "outputStereo", "prePhonemeLength",
                "postPhonemeLength", "pauseLengthScale"}
    assert required.issubset(_AUDIO_QUERY_BASE.keys())


def test_cache_key_differs_when_split_extra_present():
    from local_tts.cache import AudioCache
    from local_tts.presets import Preset

    p = Preset(name="p", provider="voicevox", options={"speaker_id": 1})
    a = AudioCache.key(p, "年に一・二回")
    b = AudioCache.key(p, "年に一・二回", extra="split=・|0.03")
    c = AudioCache.key(p, "年に一・二回", extra="split=・|0.10")
    assert a != b != c and a != c
