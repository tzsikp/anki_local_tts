"""VOICEVOX adapter.

Talks to a local `voicevox/voicevox_engine` HTTP server (Docker or
native install).

Two synthesis paths:

- **Single utterance** (no split marker, or marker absent from text):
  the classic `/audio_query` → mutate scales → `/synthesis` flow.
- **Marker-chunked utterance**: get `AccentPhrase[]` per chunk via
  `/accent_phrases` so VOICEVOX assigns accents independently — this
  is what stops e.g. `三・四倍` from collapsing to `三十四倍`. Merge
  the per-chunk arrays with an inter-chunk `pause_mora` of the user's
  configured length, then `/mora_data` recomputes mora length+pitch
  across the merged sequence so prosody flows continuously across the
  join (no sentence-final upturn before the marker, no sentence-initial
  attack after). One `/synthesis` call renders the whole thing.

Speaker list is exposed for the preset editor's dropdown.
"""

from __future__ import annotations

from typing import Any

from ..presets import Preset
from .base import ProviderError, VoiceInfo


# AudioQuery field defaults we reach for when assembling a query from
# the /accent_phrases + /mora_data path (which doesn't return a full
# AudioQuery on its own). These match the engine's /audio_query response.
_AUDIO_QUERY_BASE: dict[str, Any] = {
    "outputSamplingRate": 24000,
    "outputStereo": False,
    "prePhonemeLength": 0.1,
    "postPhonemeLength": 0.1,
    "pauseLength": None,
    "pauseLengthScale": 1.0,
    "kana": "",
}


class VoicevoxProvider:
    """Reference local AI provider; runs against `localhost:50021` by default."""

    name = "voicevox"
    display_name = "VOICEVOX"
    display_language = "Japanese"

    def provider_options_schema(self) -> dict[str, Any]:
        return {
            "endpoint": {"type": "string", "default": "http://localhost:50021"},
        }

    def options_schema(self) -> dict[str, Any]:
        return {
            "speaker_id": {"type": "integer", "default": 1},
            "speed": {"type": "number", "default": 1.0},
            "pitch": {"type": "number", "default": 0.0},
            "intonation": {"type": "number", "default": 1.0},
            "volume": {"type": "number", "default": 1.0, "min": 0.0, "max": 4.0},
        }

    @staticmethod
    def _endpoint(provider_settings: dict[str, Any]) -> str:
        return (provider_settings.get("endpoint") or "http://localhost:50021").rstrip("/")

    def synthesize(
        self,
        text: str,
        preset: Preset,
        provider_settings: dict[str, Any],
        *,
        split_marker: str | None = None,
        split_pause_length: float = 0.0,
    ) -> bytes:
        opts = preset.options
        endpoint = self._endpoint(provider_settings)
        speaker = int(opts.get("speaker_id", 1))

        chunks = self._split(text, split_marker)
        if len(chunks) == 1:
            return self._synth_simple(chunks[0], opts, speaker, endpoint)
        return self._synth_merged(chunks, split_pause_length, opts, speaker, endpoint)

    @staticmethod
    def _split(text: str, marker: str | None) -> list[str]:
        if not marker or marker not in text:
            return [text]
        return [p for p in text.split(marker) if p.strip()] or [text]

    # ------------------ single-call path ------------------

    def _synth_simple(self, text: str, opts: dict[str, Any], speaker: int, endpoint: str) -> bytes:
        with _vv_errors(endpoint):
            import requests

            q = requests.post(
                f"{endpoint}/audio_query",
                params={"speaker": speaker, "text": text},
                timeout=10,
            )
            q.raise_for_status()
            query = q.json()
            self._apply_scales(query, opts)
            return self._do_synthesis(query, speaker, endpoint)

    # --------------- chunked-merged-prosody path -----------

    def _synth_merged(
        self,
        chunks: list[str],
        pause_length: float,
        opts: dict[str, Any],
        speaker: int,
        endpoint: str,
    ) -> bytes:
        """Per-chunk accent phrases, joined with a configurable pause_mora,
        then one /mora_data + /synthesis pass for continuous prosody."""
        with _vv_errors(endpoint):
            import requests

            merged: list[dict[str, Any]] = []
            for i, chunk in enumerate(chunks):
                r = requests.post(
                    f"{endpoint}/accent_phrases",
                    params={"speaker": speaker, "text": chunk, "is_kana": False},
                    timeout=10,
                )
                r.raise_for_status()
                phrases = r.json()
                if i < len(chunks) - 1 and phrases:
                    phrases[-1]["pause_mora"] = (
                        None if pause_length <= 0 else _pause_mora(pause_length)
                    )
                merged.extend(phrases)

            # Recompute mora length+pitch across the merged sequence so
            # prosody flows naturally over the chunk boundaries.
            r = requests.post(
                f"{endpoint}/mora_data",
                params={"speaker": speaker},
                json=merged,
                timeout=15,
            )
            r.raise_for_status()
            full_phrases = r.json()

            query: dict[str, Any] = dict(_AUDIO_QUERY_BASE)
            query["accent_phrases"] = full_phrases
            self._apply_scales(query, opts)
            return self._do_synthesis(query, speaker, endpoint)

    # ------------------ shared bits ------------------

    @staticmethod
    def _apply_scales(query: dict[str, Any], opts: dict[str, Any]) -> None:
        query["speedScale"] = float(opts.get("speed", 1.0))
        query["pitchScale"] = float(opts.get("pitch", 0.0))
        query["intonationScale"] = float(opts.get("intonation", 1.0))
        query["volumeScale"] = float(opts.get("volume", 1.0))

    @staticmethod
    def _do_synthesis(query: dict[str, Any], speaker: int, endpoint: str) -> bytes:
        import requests

        s = requests.post(
            f"{endpoint}/synthesis",
            params={"speaker": speaker},
            json=query,
            timeout=30,
        )
        s.raise_for_status()
        return s.content

    # ------------------ misc ------------------

    def health_check(self, provider_settings: dict[str, Any]) -> tuple[bool, str]:
        import requests

        endpoint = self._endpoint(provider_settings)
        try:
            r = requests.get(f"{endpoint}/version", timeout=3)
            r.raise_for_status()
            return True, f"VOICEVOX {r.text.strip()}"
        except Exception as exc:
            return False, str(exc)

    def voices(self, provider_settings: dict[str, Any]) -> list[VoiceInfo]:
        import requests
        import requests.exceptions as rex

        endpoint = self._endpoint(provider_settings)
        try:
            r = requests.get(f"{endpoint}/speakers", timeout=3)
            r.raise_for_status()
            data = r.json()
        except rex.ConnectionError:
            raise ProviderError(
                f"VOICEVOX is not reachable at {endpoint}. Start the engine and try again."
            ) from None
        except rex.Timeout:
            raise ProviderError(f"VOICEVOX timed out at {endpoint}.") from None
        except Exception as exc:
            raise ProviderError(f"VOICEVOX /speakers failed at {endpoint}: {exc}") from exc

        voices: list[VoiceInfo] = []
        for speaker in data:
            name = speaker.get("name", "?")
            for style in speaker.get("styles", []):
                style_name = style.get("name", "")
                voices.append(VoiceInfo(
                    label=f"{name} · {style_name}" if style_name else name,
                    options={"speaker_id": int(style["id"])},
                ))
        return voices


def _pause_mora(vowel_length: float) -> dict[str, Any]:
    """Build a `、`-style pause mora with the given vowel length."""
    return {
        "text": "、",
        "consonant": None,
        "consonant_length": None,
        "vowel": "pau",
        "vowel_length": float(vowel_length),
        "pitch": 0.0,
    }


class _vv_errors:
    """Context manager translating `requests` failures into ProviderError."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def __enter__(self) -> _vv_errors:
        return self

    def __exit__(self, exc_type, exc, _tb) -> bool:
        if exc is None:
            return False
        import requests.exceptions as rex

        if isinstance(exc, rex.ConnectionError):
            raise ProviderError(
                f"VOICEVOX is not reachable at {self.endpoint}. "
                f"Start the engine (e.g. `docker run -p 50021:50021 voicevox/voicevox_engine:cpu-latest`) "
                f"or update the endpoint in the preset."
            ) from None
        if isinstance(exc, rex.Timeout):
            raise ProviderError(f"VOICEVOX timed out at {self.endpoint}.") from None
        if isinstance(exc, ProviderError):
            return False
        raise ProviderError(f"VOICEVOX error at {self.endpoint}: {exc}") from exc
