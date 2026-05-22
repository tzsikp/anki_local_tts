# Local TTS for Anki

An Anki add-on that synthesizes audio **at review time** through **local AI TTS engines** — no pre-generated media files, no cloud. Built for Japanese decks first; language-agnostic underneath.

> ⚠️ **Current state: one provider, Japanese-focused.** Only [VOICEVOX](https://voicevox.hiroshiba.jp/) is wired up so far. The architecture is provider-agnostic (Piper / Style-Bert-VITS2 / generic HTTP are designed to slot in as new files under `providers/`), but nothing else is implemented yet.
>
> Heavily vibe-coded. Blame Claude if something's not awesome.
>
> **PRs welcome — fork ahead.** I built this for myself and have no plans to actively maintain it. If you add a provider, fix a bug, or polish the UI, send a PR and I'll happily merge. Just don't count on me shipping updates on any schedule.

## Why this exists

The two big existing TTS add-ons — AwesomeTTS and HyperTTS — both work, but:

- **Configuration is painful.** Voice/preset is encoded in the card template, so changing engine or voice means re-editing every note type and re-saving. Preset management is rigid; switching providers across a deck is a chore.
- **The good voices are behind paywalls.** ElevenLabs, Azure, OpenAI TTS, Google Cloud TTS, etc. all charge per character. For daily Anki reviews this adds up fast, and cloud engines also handle Japanese poorly compared to dedicated Japanese models.

Local AI engines — VOICEVOX, Piper, Style-Bert-VITS2 — sound dramatically better for Japanese, run on your own machine, and cost nothing. This addon is built around that constraint: **local providers only, presets are first-class, routing is central**.

---

## How it works

Card templates use Anki's built-in TTS tag with a custom voice name:

```
{{tts ja_JP voices=LocalTTS:Expression}}
```

At review time:

```
Anki reviewer
   ↓  TTSProcessPlayer
Routing table             deck → notetype → language → default
   ↓
Cleanup pipeline          HTML, ruby, brackets, cloze, CJK spaces
   ↓
User regex rules          ordered, transparent
   ↓
Cache lookup              sha256(preset fingerprint ‖ processed text)
   ↓  miss
Provider                  VOICEVOX (Piper, Style-Bert-VITS2 next)
   ↓
Cache write + playback    Opus via ffmpeg, WAV fallback
```

Templates only declare *that* a field wants TTS. **Which** preset speaks is decided by a central routing table — switching voices for one deck (or your whole collection) is a single dropdown change, not a template rewrite.

---

## Requirements

- **Anki 24.x or newer** (Qt 6 / PyQt 6, Python 3.13 bundled).
- **macOS, Windows, or Linux desktop.** AnkiMobile / AnkiWeb can't run local engines, so this is desktop-only.
- **A local TTS engine.** [VOICEVOX](https://voicevox.hiroshiba.jp/) is the first-class provider; others come next. Quickest setup is Docker:
  ```
  docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest
  ```
  For other install options (native Mac app, Windows installer, GPU image, etc.) see VOICEVOX's official site at [voicevox.hiroshiba.jp](https://voicevox.hiroshiba.jp/) and the engine repo at [github.com/VOICEVOX/voicevox_engine](https://github.com/VOICEVOX/voicevox_engine). Whatever you run, point the addon at it via Settings → Providers → endpoint (default `http://localhost:50021`).
- **ffmpeg (optional but recommended).** Used to transcode the cache to Opus (~12× smaller than WAV). Without it the addon falls back to WAV.

---

## Install (developer / current state)

The addon isn't on AnkiWeb yet. Two ways to run it from this repo:

### Symlink (live edits)

```bash
uv sync --extra dev
uv run python scripts/dev_link.py
```

Then restart Anki. The script symlinks `local_tts/` into Anki's `addons21/` folder. Edit files in the repo, restart Anki to reload.

`uv run python scripts/dev_link.py --unlink` removes it.

### Build a `.ankiaddon`

```bash
uv run python scripts/build_addon.py
```

Produces `dist/local_tts.ankiaddon` — double-click to install in Anki.

---

## Quickstart

1. **Start VOICEVOX** (or your engine of choice).
2. **Install the addon** (above).
3. **Tools → Local TTS settings…**
   - *Providers* tab: confirm or change the VOICEVOX endpoint.
   - *Presets* tab: the bundled "Japanese VOICEVOX 春日部つむぎ · ノーマル" preset is ready. Click New to add more; the editor's "Pick voice from server…" button (only on new presets) fetches the live speaker list from VOICEVOX with a built-in test-play.
   - *Routing* tab: which preset plays for which deck / note type / language.
4. **Card template** — add to any field you want spoken. Edit your note type's card template (Browse → Cards…) and insert, for example:
   ```
   {{tts ja_JP voices=LocalTTS:Expression}}
   ```
   `Expression` is a placeholder for **whichever field on your note type holds the text to be spoken** — it must be the exact name of an existing field. If your note type has a field called `Sentence` instead, write `…voices=LocalTTS:Sentence`. The field should contain Japanese text (or whatever language matches the preset routed for it). If the field is empty for a given card, nothing plays — no error.
5. **Review** a card. Cache miss → ~1–2s synth + play. Cache hit → instant.

A quick switcher is available at **Tools → Local TTS · Routes** for changing the default / per-language / per-deck preset without opening Settings.

---

## Configuration

Three levels:

| Scope | Lives in | Example | Edited via |
|---|---|---|---|
| **Provider settings** | `provider_settings[name]` | VOICEVOX `endpoint` | Settings → Providers |
| **Preset** (voice config) | `presets[*]` | speaker_id, speed, pitch, cleanup flags, regex rules | Settings → Presets |
| **Routing** | `routing.{by_deck,by_notetype,by_language}` | "deck 12345 → preset X" | Settings → Routing |

Provider settings are **shared across all presets of that provider**. Moving your VOICEVOX server only requires updating the endpoint once.

### Cleanup pipeline

Fixed-order, applied before user regex rules:

1. Ruby tags — `<ruby>本<rt>ほん</rt></ruby>` → base or reading
2. Strip HTML
3. Bracket readings — `日々[ひび]` → base or reading
4. Anki cloze braces — `{{c1::日本語}}` → `日本語`
5. Whitespace normalize
6. Collapse spaces between Japanese characters (artifacts from furigana add-ons; only collapses where both neighbours are JP)

Each step is a pure function. Flags live on the preset's `cleanup` block.

### Regex rules

Per-preset, ordered, applied after the cleanup pipeline. Use them for vocabulary fixes a model gets wrong (e.g. `20日` → `はつか`). The preset editor's regex table includes a **Validate** button that compiles every pattern and reports failures inline.

Validation also runs at config load — broken patterns produce a one-time warning popup, and the runtime skips broken rules instead of crashing.

### Cache

- **Location:** `<addon-folder>/user_files/cache/`. Never touches `collection.media`.
- **Key:** `sha256(preset.fingerprint() ‖ processed_text)`. Endpoint is **not** part of the fingerprint — moving servers doesn't invalidate cached audio.
- **Format:** Opus if `ffmpeg` is on PATH (or set explicitly in Settings → General), WAV otherwise.
- **Eviction:** LRU by file `atime`, capped at the configured MB ceiling.
- **Clear:** Settings → General → "Clear cache now".

### Failure handling

If a provider is unreachable, you'll see a transient tooltip (e.g. `Local TTS: VOICEVOX is not reachable at http://localhost:50021 — start the engine or update the endpoint.`) — once per session per error type, not every card. The log at `<addon-folder>/user_files/log/local_tts.log` has the full picture.

---

## Architecture, briefly

```
local_tts/
├── __init__.py            entry point
├── addon.py               composition root, menu wiring, apply_config
├── config.py              persisted settings + load/save + addon_dir resolution
├── presets.py             Preset / RegexRule / CleanupOptions + fingerprint
├── routing.py             deck > notetype > language > default
├── cache.py               disk cache + Opus transcode + LRU eviction
├── player.py              TTSProcessPlayer subclass, _on_done queue inject
├── providers/             abstract Provider + adapters
│   ├── base.py
│   └── voicevox.py
├── text/
│   ├── cleanup.py         pure functions, unit-testable
│   └── regex_rules.py     validate_pattern + apply
└── gui/
    ├── settings.py        tabbed dialog
    └── preset_editor.py   modal editor + live voice picker
```

Provider adapters are stateless: they receive `(text, preset, provider_settings)` and return WAV bytes. Nothing outside `providers/` may import a concrete provider.

---

## Development

```bash
uv sync --extra dev
uv run pytest                                 # 26 tests, fully pure
uv run python scripts/dev_link.py             # symlink into Anki
uv run python scripts/build_addon.py          # build dist/local_tts.ankiaddon
```

Tests cover the pure modules — cleanup pipeline, preset fingerprint stability, routing precedence, cache roundtrip + Opus path, config roundtrip, regex validation. GUI and Anki-integrated code is smoke-tested manually.

---

## Limitations

- **Desktop only.** AnkiMobile / AnkiWeb can't run local engines.
- **One config per Anki profile.** Multi-profile users get one independent install each, which is fine.
- **Anki reloads addons only at startup.** After edits, restart Anki (`pkill -x Anki && open -a Anki` if you're impatient on macOS).
- **The replay button works** via an explicit `av_player.insert_file` in `_on_done` — Anki's default `TTSProcessPlayer` does not auto-enqueue.

---

## License

MIT — use it, modify it, share it, sell it, do whatever. No warranty, no liability. See [LICENSE](LICENSE).

Code design was informed by [AwesomeTTS](https://github.com/AwesomeTTS/awesometts-anki-addon) (GPLv3), but **no code from AwesomeTTS is included or redistributed** — only design ideas (the `TTSProcessPlayer` hook pattern, sanitization approach).
