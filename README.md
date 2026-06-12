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
Regex rules               global, with optional per-preset override
   ↓
Cache lookup              sha256(provider+options ‖ processed text)
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

## Install

Easiest: from [AnkiWeb](https://ankiweb.net/shared/info/1279936795) via Tools → Add-ons → Get Add-ons in Anki.

Or grab the `.ankiaddon` from the [latest GitHub release](https://github.com/tzsikp/anki_local_tts/releases/latest) and double-click to install.

### Run from this repo (developer)

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
   - *Presets* tab: the bundled "Japanese VOICEVOX 春日部つむぎ · ノーマル" preset is ready. Click New to add more; the editor's "Pick voice from server…" button (only on new presets) fetches the live speaker list from VOICEVOX with a built-in test-play. Each preset may optionally override the global cleanup / regex rules.
   - *Rules* tab: global text cleanup, regex substitutions, split marker for tight pauses, and voice defaults inherited by every preset. See the [Settings guide](#settings-guide) for details.
   - *Routing* tab: which preset plays for which deck / note type / language.
4. **Card template** — add to any field you want spoken. Edit your note type's card template (Browse → Cards…) and insert, for example:
   ```
   {{tts ja_JP voices=LocalTTS:Expression}}
   ```
   `Expression` is a placeholder for **whichever field on your note type holds the text to be spoken** — it must be the exact name of an existing field. If your note type has a field called `Sentence` instead, write `…voices=LocalTTS:Sentence`. The field should contain Japanese text (or whatever language matches the preset routed for it). If the field is empty for a given card, nothing plays — no error.
5. **Review** a card. Cache miss → ~1–2s synth + play. Cache hit → instant.

A quick switcher is available at **Tools → Local TTS · Routes** for changing the default / per-language / per-deck preset without opening Settings.

---

## Settings guide

Everything lives under **Tools → Local TTS settings…**. Save applies the changes on the next playback — no restart.

### General

- **Enable Local TTS** — master switch. Off leaves the addon installed but inert.
- **Default preset** — used when no per-deck / per-notetype / per-language rule matches.
- **ffmpeg path** — leave blank to auto-detect on `PATH` and common install locations (Homebrew, `/usr/local/bin`, `/usr/bin`). Set explicitly if you have multiple installs. Without ffmpeg the cache falls back to WAV (~12× larger but still works).
- **Cache size limit** — total disk budget for synthesized audio under `<addon-folder>/user_files/cache/`. LRU-evicted by file access time when full.
- **Clear cache now** — delete every cached file. Next playback will re-synthesize on demand.

### Providers

Provider-level settings, **shared across every preset** that uses that provider. Edit once when you move the server; presets don't need editing.

- **VOICEVOX → endpoint** — `http://localhost:50021` by default. Change if you run VOICEVOX on a different host/port (e.g. `http://macmini.local:50021` for a LAN server).

### Presets

A preset is a voice configuration — provider + voice ID + per-voice options (speed, pitch, …). Add, edit, duplicate, or delete presets here. Each preset has:

- **Name** — what shows up in the routing table.
- **Provider** — which engine to use. Currently only VOICEVOX.
- **Pick voice from server…** (new-preset only) — live-queries VOICEVOX for the speaker list with a built-in test-play button.
- **Speaker / speed / pitch / intonation / volume** — voice parameters. By default these inherit from **Voice defaults** under the Rules tab; tick the "Use global" checkbox off if you want this preset to pin its own value.
- **Override global cleanup / regex rules** — opt-in checkboxes. Off (default) means the preset inherits the global Rules. On replaces the global list with the preset's own block.

### Rules

Global text and prosody settings. Apply to every preset that doesn't explicitly override them.

#### Cleanup

Fixed-order pipeline applied before regex rules. Configurable:

- **Ruby tags** (`<ruby>本<rt>ほん</rt></ruby>`) → keep the base character (`本`) or the reading (`ほん`).
- **Bracket readings** (`日々[ひび]`) → keep the base, the reading, or both.
- **Bracket pairs** — which bracket characters get the bracket-reading treatment. Defaults: `[]`, `()`.
- **Collapse spaces between Japanese characters** — removes furigana-add-on artifacts like `日本　に` → `日本に`. Only collapses where both neighbours are Japanese.

Always-on cleanup (not configurable): HTML strip, Anki cloze braces (`{{c1::X}}` → `X`), whitespace normalize.

#### Numbers

- **Read numbers as words** (on by default) — rewrites every run of ASCII or full-width digits to its classical kanji form before synthesis (`1990` → `千九百九十`, `7月` → `七月`, `100円` → `百円`). Without this, VOICEVOX reads bare digits one at a time ("nana tsuki" instead of "shichi-gatsu"). Off → digits are sent through verbatim.

#### Regex rules

Ordered list of `pattern → replacement` substitutions applied after cleanup. Use them for vocabulary fixes the engine gets wrong:

- `20日` → `はつか`
- `背負ってくる` → `しょってくる`

Per row: **On** (enable), **Pattern** (Python regex), **Replacement** (literal or backreferences). The **Validate** button compiles every pattern and reports failures inline. Validation also runs at config load — broken patterns produce a one-time popup and are skipped at runtime, never crashing playback.

#### Split marker (VOICEVOX)

Insert the marker character in card text where you want a short pause instead of VOICEVOX's default ~0.15s comma pause. The engine still pronounces neighbouring digits separately (`三・四倍` → "san, yon-bai", not "sanjuuyon-bai") and prosody flows continuously across the join.

- **Marker character** — what to look for in card text. Default `・`. Leave empty to disable entirely.
- **Pause length** — gap inserted at marker positions. Default `0.03 s`. Set `0` for no audible gap.
- **Auto-mark digit-、-digit pauses** — when on, any `、` sitting between two digits is rewritten to the marker before synthesis, so you don't have to type the marker in cards. Covers half-width (`2023、2024`), full-width (`１、２`), and CJK digits (`三、四`, `十三、四`, `三十、四十`). Commas in non-digit contexts (`三月、四月`, `日本、英語`) are untouched. Off by default.

#### Voice defaults

Global baseline for the per-voice numeric parameters. Each preset's editor shows an "Use global (X)" checkbox per parameter — checked = inherit, unchecked = preset pins its own value.

- **speed** — 1.0 is natural pace. <1 slower, >1 faster. Recommended 0.9–1.2.
- **pitch** — offset from the speaker's natural pitch. 0.0 = unchanged. VOICEVOX is sensitive here — stay within roughly ±0.1.
- **intonation** — how much the pitch moves while speaking. 1.0 normal, 0.0 monotone/robotic, >1 exaggerated. Recommended 0.8–1.3.
- **volume** — output multiplier. 1.0 default, 1.5–2.0 audibly louder, above ~2.0 starts clipping.

Changing a global value here re-synthesizes any preset that inherits it on next play. Presets that override the value are unaffected.

### Routing

Decides which preset plays when a TTS tag fires. Resolution order, first match wins:

1. **By deck** — `deck → preset`. Most specific.
2. **By note type** — `notetype → preset`.
3. **By language** — `ja → preset`, `en → preset`, … Use the `ja_JP` / `en_US` style in your card template's TTS tag; the language root (`ja`) is what matches here.
4. **Default preset** — set under the General tab.

`Tools → Local TTS · Routes` gives a one-click submenu to switch the default / per-language / per-deck preset without opening Settings.

---

### Cache

- **Location:** `<addon-folder>/user_files/cache/`. Never touches `collection.media`.
- **Key:** `sha256(preset.fingerprint() ‖ processed_text)`. The fingerprint covers only `provider + options`. Endpoint, cleanup flags, and regex rules are **not** in it — moving servers or tweaking rules doesn't invalidate audio for unaffected text.
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
