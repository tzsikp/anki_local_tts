"""Provider-agnostic WAV utilities.

Used when a provider splits an utterance into chunks (e.g. VOICEVOX's
`split_marker` flow) and needs to glue the per-chunk WAV bytes back into
one playable file. Same-format-only — concatenating WAVs of differing
sample rates / bit depths is not supported because the player has no
context to resample.
"""

from __future__ import annotations

import io
import wave


def concat_wavs(wavs: list[bytes], silence_seconds: float = 0.0) -> bytes:
    """Concatenate same-format WAV chunks with optional silence between.

    `silence_seconds == 0` (or no silence segment between adjacent chunks)
    just joins the audio back-to-back.
    """
    if not wavs:
        raise ValueError("concat_wavs: empty input")
    if len(wavs) == 1 and silence_seconds <= 0:
        return wavs[0]

    frames: list[bytes] = []
    params = None
    for w in wavs:
        with wave.open(io.BytesIO(w), "rb") as r:
            p = r.getparams()
            if params is None:
                params = p
            elif (p.nchannels, p.sampwidth, p.framerate) != (
                params.nchannels, params.sampwidth, params.framerate
            ):
                raise ValueError(
                    f"concat_wavs: format mismatch ({p.nchannels}/{p.sampwidth}/{p.framerate} "
                    f"vs {params.nchannels}/{params.sampwidth}/{params.framerate})"
                )
            frames.append(r.readframes(p.nframes))

    assert params is not None
    silence_bytes = b""
    if silence_seconds > 0:
        n_silence = int(silence_seconds * params.framerate)
        silence_bytes = b"\x00" * (n_silence * params.sampwidth * params.nchannels)

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        for i, chunk in enumerate(frames):
            if i > 0 and silence_bytes:
                w.writeframes(silence_bytes)
            w.writeframes(chunk)
    return out.getvalue()
