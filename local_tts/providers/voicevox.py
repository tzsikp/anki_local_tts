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
from .base import ProviderError, VoiceInfo


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
        }

    @staticmethod
    def _endpoint(provider_settings: dict[str, Any]) -> str:
        return (provider_settings.get("endpoint") or "http://localhost:50021").rstrip("/")

    def synthesize(self, text: str, preset: Preset, provider_settings: dict[str, Any]) -> bytes:
        import requests
        import requests.exceptions as rex

        opts = preset.options
        endpoint = self._endpoint(provider_settings)
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
        except rex.ConnectionError:
            raise ProviderError(
                f"VOICEVOX is not reachable at {endpoint}. "
                f"Start the engine (e.g. `docker run -p 50021:50021 voicevox/voicevox_engine:cpu-latest`) "
                f"or update the endpoint in the preset."
            ) from None
        except rex.Timeout:
            raise ProviderError(f"VOICEVOX timed out at {endpoint}.") from None
        except Exception as exc:
            raise ProviderError(f"VOICEVOX error at {endpoint}: {exc}") from exc

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
