# AnkiWeb listing

The text below is the source-of-truth for the AnkiWeb shared-addons listing.
Update it whenever the listing should change, commit, and paste into the
AnkiWeb "Upload new version" form alongside the matching `.ankiaddon`.

The `human_version` field in `manifest.json` should match the version
referenced here (or be one ahead while preparing the next release).

---

## Title

> Local TTS for Japanese (VOICEVOX)

## Tags

> tts japanese voicevox local audio

## Supported Anki versions

Tested against Anki 24.x (Qt 6 / PyQt 6). Pick the latest tested point
version from AnkiWeb's checkbox list at upload time.

## Description

```markdown
Synthesize Japanese TTS audio **at review time** through a **local VOICEVOX server** — no cloud, no per-character fees, no pre-generated media files.

## Why
Cloud TTS handles Japanese poorly, and the good engines (ElevenLabs, OpenAI, Azure...) charge per character. Existing Anki TTS add-ons also bake the voice choice into card templates, which makes switching presets painful. Local TTS lets you:

- Run [VOICEVOX](https://voicevox.hiroshiba.jp/) (free, local, dramatically better Japanese quality)
- Pick voices via a live "Pick voice from server" dialog with a built-in test play
- Route presets centrally: per-deck, per-note-type, or per-language, edited from one dialog — no template re-saves
- Cache synthesized audio (Opus, ~12× smaller than WAV) keyed by preset config, never touches `collection.media`
- Use Anki's built-in `{{tts ja_JP voices=LocalTTS:Field}}` tag — no custom template syntax

## Requirements
- Anki 24.x or newer (desktop only — local engines can't run on AnkiMobile / AnkiWeb)
- A running VOICEVOX server. Quickest setup:
  ```
  docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest
  ```
  See [voicevox.hiroshiba.jp](https://voicevox.hiroshiba.jp/) for native Mac / Windows installers.
- Optional: ffmpeg on PATH for Opus cache compression (falls back to WAV).

## Quick start
1. Start VOICEVOX.
2. Install this addon, restart Anki.
3. Tools → Local TTS settings… → confirm the endpoint matches your VOICEVOX URL.
4. In your card template, add `{{tts ja_JP voices=LocalTTS:Expression}}` (replace `Expression` with the actual field name holding Japanese text).
5. Review a card — cache miss ~1–2s, cache hit instant.

## Current state
**Only VOICEVOX is wired up so far.** The architecture is provider-agnostic (Piper / Style-Bert-VITS2 / generic HTTP designed to slot in), but nothing else is implemented yet. Heavily vibe-coded.

**No maintenance guarantees.** I built this for myself. PRs welcome — see the GitHub repo.

## Source / contributing
https://github.com/tzsikp/anki_local_tts

MIT licensed.
```
