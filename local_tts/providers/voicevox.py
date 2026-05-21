"""VOICEVOX adapter.

Talks to a local `voicevox/voicevox_engine` HTTP server (Docker or
native install). Two-step protocol: `POST /audio_query` returns a JSON
query object describing the utterance, which we mutate with the
preset's speed/pitch/intonation, then `POST /synthesis` returns the
final WAV. Speaker list is exposed for the preset editor's dropdown.
"""

from __future__ import annotations

from typing import Any

from ..presets import Preset
from .base import ProviderError


class VoicevoxProvider:
    """Reference local AI provider; runs against `localhost:50021` by default."""

    name = "voicevox"

    def options_schema(self) -> dict[str, Any]:
        return {
            "endpoint": {"type": "string", "default": "http://localhost:50021"},
            "speaker_id": {"type": "integer", "default": 1},
            "speed": {"type": "number", "default": 1.0},
            "pitch": {"type": "number", "default": 0.0},
            "intonation": {"type": "number", "default": 1.0},
        }

    def synthesize(self, text: str, preset: Preset) -> bytes:
        import requests

        opts = preset.options
        endpoint = opts.get("endpoint", "http://localhost:50021").rstrip("/")
        speaker = int(opts.get("speaker_id", 1))
        try:
            q = requests.post(
                f"{endpoint}/audio_query",
                params={"speaker": speaker, "text": text},
                timeout=10,
            )
            q.raise_for_status()
            query = q.json()
            query["speedScale"] = float(opts.get("speed", 1.0))
            query["pitchScale"] = float(opts.get("pitch", 0.0))
            query["intonationScale"] = float(opts.get("intonation", 1.0))

            s = requests.post(
                f"{endpoint}/synthesis",
                params={"speaker": speaker},
                json=query,
                timeout=30,
            )
            s.raise_for_status()
            return s.content
        except Exception as exc:
            raise ProviderError(f"VOICEVOX synth failed: {exc}") from exc

    def health_check(self, preset: Preset) -> tuple[bool, str]:
        import requests

        endpoint = preset.options.get("endpoint", "http://localhost:50021").rstrip("/")
        try:
            r = requests.get(f"{endpoint}/version", timeout=3)
            r.raise_for_status()
            return True, f"VOICEVOX {r.text.strip()}"
        except Exception as exc:
            return False, str(exc)

    def speakers(self, endpoint: str) -> list[dict[str, Any]]:
        """Fetch the engine's full speaker/style catalogue for the preset UI."""
        import requests

        r = requests.get(f"{endpoint.rstrip('/')}/speakers", timeout=5)
        r.raise_for_status()
        return r.json()
