# Local TTS for Anki — Project Guide

This file is the working brief for Claude. It captures what we're building, the design rules, the relevant Anki internals, and how to use the reference codebase in `awesometts/`.

---

## 1. What we're building

An Anki add-on that synthesizes audio **at review time** (no permanent media files), driven by **reusable named presets** that point at **local AI TTS engines** — primarily for Japanese decks.

User-facing spec: `README.md`. Read it once before writing code.

### Scope vs. AwesomeTTS
AwesomeTTS (the source under `awesometts/`) is **a reference, not a base**. We are not forking it. We will:
- borrow ideas from `text.py` (sanitization), `router.py` (provider dispatch), `service/*.py` (provider adapters), and `ttsplayer.py` (the `{{tts:...}}` hook into Anki's `TTSProcessPlayer`),
- **not** import its code, GUI, config schema, or service catalogue. Most of AwesomeTTS targets cloud providers (Google, Azure, AWS, ElevenLabs, etc.) we explicitly don't want.

If you find yourself copy-pasting from `awesometts/`, stop and re-derive the smaller, focused version we actually need.

---

## 2. Non-negotiable design rules

1. **Local AI providers only** for the MVP. VOICEVOX first. Piper, Style-Bert-VITS2, Coqui, and other self-hosted/HTTP-local engines after. Cloud providers are explicitly out of scope — the whole reason this exists is that cloud TTS handles Japanese poorly.
2. **No pre-generated media.** Audio lives in a runtime cache keyed by `(preset config + processed text)`. The cache is disposable; it must never write into the Anki `collection.media` folder.
3. **Presets are the unit of configuration.** Provider, voice, speed, regex rules all live on a named preset. Card templates do **not** name presets — a central routing table (per-deck → per-notetype → per-language → default) decides which preset plays. See §3.
4. **No provider-specific code outside `providers/`.** VOICEVOX is the first adapter, not the architecture. The rest of the addon must talk to providers exclusively through the abstract `Provider` interface (§6). If you find yourself importing `voicevox` from `player.py`, `cache.py`, `presets.py`, or the GUI, you've leaked the abstraction. Swapping to Piper or Style-Bert-VITS2 later must be: add a file under `providers/`, register it, done.
5. **Transparent text processing.** Built-in cleanup pipeline is fixed and documented (HTML strip → ruby → bracket readings → cloze braces). Anything language-specific beyond that must be expressed as user-visible regex rules on the preset. No hidden NLP, no auto-language detection, no silent "smart" rewrites.
6. **Japanese-first, not Japanese-only.** The cleanup pipeline and defaults target Japanese decks (furigana, ruby, `日々[ひび]` bracket readings, pitch notation), but nothing in the architecture should hardcode `ja`.
7. **Non-blocking review UI.** Synthesis runs off the Qt main thread. Cache hits play instantly; misses synthesize asynchronously without freezing the reviewer.
8. **Cache invalidation is automatic.** Changing any field of a preset (voice, speed, regex list, cleanup options) invalidates entries derived from it. Implement by hashing the canonical preset JSON + processed text into the cache key.

---

## 3. Template-tag syntax — decided: option A

We use Anki's built-in TTS tag and register a `TTSProcessPlayer`, the same hook AwesomeTTS uses (`awesometts/awesometts/ttsplayer.py`). Card templates contain a stock-looking tag like:

```
{{tts ja_JP voices=LocalTTS:FieldName}}
```

The voice name (`LocalTTS`) routes playback to our player. We do **not** invent a `{{tts:Preset:Field}}` syntax — that would clash with Anki's namespace and break the built-in playback queue / replay shortcut.

### Preset selection is NOT in the template

This is the biggest UX fix over AwesomeTTS. In AwesomeTTS, the voice/preset is encoded in the card template — changing engine or voice means editing every note type, re-saving, and dealing with the per-language voice mapping. **We don't do that.**

The template only declares "this field wants TTS". The actual preset is chosen by a **central routing table** in the addon config, evaluated at playback time. Resolution order (first match wins):

1. **Per-deck override** — `deck_id → preset_name`. Editable from the global settings dialog as a simple two-column table; no template edits required.
2. **Per-note-type override** — `notetype_id → preset_name`.
3. **Per-language fallback** — `lang_code → preset_name` (e.g. `ja → "Japanese VOICEVOX Tsumugi"`).
4. **Global default preset.**

Switching the entire collection from VOICEVOX-Tsumugi to Piper-Female is a single dropdown change in settings. Switching one deck is one row in the routing table. Templates are never touched.

Implementation notes:
- The Anki `TTSTag` carries a language code (`ja_JP`) but not a deck/note-type. Get the current card via `mw.reviewer.card` inside `_play` to resolve `deck_id` and `notetype_id`. Fall back gracefully if no reviewer context (e.g. preview).
- Register one synthetic `TTSVoice(name="LocalTTS", lang=...)` per language we care about so Anki's TTS tag accepts it for any deck without re-registration. AwesomeTTS does this in `ttsplayer.py:get_available_voices` — same pattern.
- The routing table lives in `config.json`, not in note templates. Changes take effect on next playback (no Anki restart, no template re-save).

---

## 4. Architecture

```
Anki reviewer
   ↓  TTSProcessPlayer.get_available_voices / _play   (ttsplayer.py)
Tag resolver           → which preset?
   ↓
Field text             ← already substituted by Anki
   ↓
Cleanup pipeline       (HTML, ruby, brackets, cloze) — fixed order
   ↓
Regex transforms       (preset.regex_rules, in order)
   ↓
Cache lookup           key = sha256(canonical_preset_json + processed_text)
   ↓ miss
Provider adapter       (voicevox, piper, generic_http, ...)
   ↓
Cache write + playback (av_player / aqt.sound)
```

### Suggested module layout

```
local_tts/
  __init__.py            # Anki entry point: register hooks, build singletons
  addon.py               # Addon class wiring config + providers + cache + player
  config.py              # Load/save settings via mw.addonManager.getConfig
  presets.py             # Preset dataclass, validation, canonical hashing
  text/
    cleanup.py           # HTML, ruby, brackets, cloze — pure functions
    regex_rules.py       # Apply ordered user regex list
  cache.py               # Disk cache (addon user_files dir), LRU + size cap
  providers/
    base.py              # Abstract Provider: synth(text, preset) -> bytes/path
    voicevox.py
    piper.py             # later
    generic_http.py      # later
  player.py              # TTSProcessPlayer subclass; async dispatch
  gui/
    settings.py          # Global settings dialog
    preset_editor.py     # CRUD presets, test synthesis, regex editor with preview
```

Keep modules small and pure where possible. `text/cleanup.py` and `text/regex_rules.py` must be trivially unit-testable without Anki.

---

## 5. Anki internals cheat-sheet

- Anki ≥ 2.1.50 uses Qt 6 / PyQt6. Target current stable (Anki 24.x at time of writing). Imports: `from aqt import mw`, `from aqt.sound import av_player`, `from aqt.tts import TTSProcessPlayer, TTSVoice`, `from anki.sound import AVTag, TTSTag`.
- Config persistence: `mw.addonManager.getConfig(__name__)` / `writeConfig`. JSON-only.
- Per-addon writable dir: `mw.addonManager.addonsFolder(__name__)/user_files/` — cache and exported presets go here.
- Reviewer hooks: `aqt.gui_hooks.card_will_show`, `reviewer_did_show_question/answer`. Field filters: `anki.hooks.field_filter`.
- Long work: never block the main thread. Use `mw.taskman.run_in_background(task, on_done)` — same pattern AwesomeTTS uses (`ttsplayer.py`).
- Logging: a single addon-scoped logger writing to `user_files/log/`. Don't print to stdout.

---

## 5b. Config schema (current)

```jsonc
{
  "enabled": true,
  "default_preset": "Japanese VOICEVOX Tsumugi",
  "routing": {
    "by_deck":     { "1707000000000": "Japanese VOICEVOX Zundamon" },
    "by_notetype": { "1707111111111": "Japanese Piper Female" },
    "by_language": { "ja": "Japanese VOICEVOX Tsumugi", "en": "English Piper" }
  },
  "provider_settings": {
    "voicevox": { "endpoint": "http://localhost:50021" }
  },
  "presets": [
    {
      "name": "Japanese VOICEVOX Tsumugi",
      "provider": "voicevox",
      "options": { "speaker_id": 8, "speed": 0.95, "pitch": 0.0, "intonation": 1.1 },
      "cleanup": { "ruby_mode": "base", "bracket_mode": "base",
                   "brackets": ["[]", "()"], "collapse_cjk_spaces": true },
      "regex_rules": [ { "enabled": true, "pattern": "20日", "replacement": "はつか" } ]
    }
  ],
  "cache": { "max_mb": 1024, "dir": "user_files/cache" },
  "ffmpeg_path": null
}
```

Two configuration scopes, deliberately separated:

- **`provider_settings[name]`** — shared across every preset of that provider (endpoint, future auth tokens). Not part of `preset.fingerprint`, so moving the server does **not** invalidate cached audio. Edited via Settings → Providers.
- **`presets[*].options`** — per-preset voice config (speaker_id, speed, ...). Part of fingerprint.

Routing resolution lives in one function (`routing.resolve(card, lang) -> Preset`) and is the only code that knows about decks/note-types. Provider adapters never see those — they receive `(text, preset, provider_settings)`.

---

## 6. Provider contract

```python
class Provider:
    name: str                       # "voicevox"
    display_name: str               # "VOICEVOX"
    display_language: str           # "Japanese" or "" for multi-lang
    def provider_options_schema(self) -> dict: ...   # shared per-provider settings
    def options_schema(self) -> dict: ...            # per-preset voice options
    def synthesize(self, text: str, preset: Preset, provider_settings: dict) -> bytes: ...
    def health_check(self, provider_settings: dict) -> tuple[bool, str]: ...
    def voices(self, provider_settings: dict) -> list[VoiceInfo]: ...  # optional live discovery
```

Adapters must be **stateless** apart from a `requests.Session` / config; instantiating one is cheap. Throw a typed `ProviderError` on failure; the player turns that into a user-visible message and a silent skip (no audio rather than a crash).

### VOICEVOX (MVP)
- Default endpoint `http://localhost:50021`.
- Flow: `POST /audio_query?speaker={id}&text=...` → mutate `speedScale`, `pitchScale`, `intonationScale` from preset → `POST /synthesis?speaker={id}` → WAV bytes.
- Speaker list: `GET /speakers` — populate the preset editor dropdown lazily; cache for the session.

---

## 7. Cleanup pipeline — exact spec

Fixed order, applied before regex rules:

1. **Strip HTML** — `BeautifulSoup(text, "html.parser").get_text(" ")` then collapse whitespace. Mirrors `awesometts/awesometts/text.py:STRIP_HTML`.
2. **Ruby tags** — `<ruby>本<rt>ほん</rt></ruby>` → either the base char or the reading, per preset flag `ruby_mode: base|reading`.
3. **Bracket readings** — `日々[ひび]` → either `日々` or `ひび`, per preset flag `bracket_mode: base|reading|strip_brackets_only`. Configurable bracket chars (`[]`, `()`, `{}`).
4. **Anki cloze braces** — `{{c1::日本語}}` → `日本語`; on the question side, the rendered `<span class="cloze">[...]</span>` form must also collapse to "blank" or be skipped. See `RE_CLOZE_BRACED` / `RE_CLOZE_RENDERED` in `awesometts/awesometts/text.py` for the regexes — reuse the patterns, not the module.
5. **Whitespace normalize** — collapse runs of whitespace to a single space, trim.

All five steps are pure functions; each takes `str` and returns `str`. Test them independently.

---

## 8. README improvements to fold in

When we touch `local_tts_for_anki_readme.md`, address these gaps (in rough priority):

1. **Resolve the tag-syntax ambiguity** (section 3 above). The README's `{{tts:Preset:Field}}` looks like Anki's built-in tag but isn't — clarify.
2. **State the Anki / Qt / Python version target** explicitly.
3. **Define "local AI provider"** — list concretely: VOICEVOX, Piper, Style-Bert-VITS2, Coqui XTTS, generic HTTP. Note that cloud providers are an explicit non-goal, not a "later".
4. **Cache** section should specify: location (`user_files/cache/`), key derivation (canonical-JSON-hash of preset + processed text), eviction policy (LRU + max size MB), and that it never touches `collection.media`.
5. **Failure behaviour** — what happens if the local engine is down? (Silent skip + log + one-time toast.) Spell this out.
6. **Threading model** — one sentence saying synthesis is async and the reviewer never blocks.
7. ~~**License** — pick one (AwesomeTTS is GPLv3; we're not derivative but if we lift any regex verbatim we should stay GPL-compatible).~~ **Done: MIT.** See `LICENSE`. Acknowledges AwesomeTTS as a design reference; no code lifted.
8. **MVP acceptance checklist** — turn the "MVP scope" bullets into testable criteria ("VOICEVOX preset plays a JA sentence within 2s on cache miss, <100ms on hit").
9. **Drop the cloud providers** from "Planned future providers" — they contradict the project thesis. Replace with local-friendly options (Style-Bert-VITS2, Bark, XTTS).
10. **Add a "Limitations"** section — e.g. AnkiMobile/AnkiWeb cannot run local engines, so this is desktop-only.

Don't rewrite the README unprompted — surface these as a diff when the user asks.

---

## 9. Working conventions

- **Use the AwesomeTTS source as a lookup, not a template.** When you need to know how Anki exposes a hook, grep `awesometts/awesometts/` first; then write our own minimal version.
- **No new files unless needed.** Prefer extending an existing module.
- **Tests:** pure modules (`text/`, `cache.py`, `presets.py`) get unit tests with `pytest`; Anki-integrated modules are smoke-tested manually until we have an Anki test harness.
- **No emojis in code or UI** unless the user explicitly asks.
- **No comments explaining what the code does** — only why, when non-obvious.

---

## 9b. Release & distribution

GitHub remote: `tzsikp/anki_local_tts` (over SSH alias `github.tzsikp`).

### CI

- `.github/workflows/ci.yml` — runs `uv run pytest -q` on every push to `main` and on PRs.
- `.github/workflows/release.yml` — fires on tags matching `v*`. Runs the test suite, then `scripts/build_addon.py`, then attaches `dist/local_tts.ankiaddon` to an auto-generated GitHub Release.

### Cutting a release

1. Bump `human_version` in `local_tts/manifest.json`.
2. Update `ANKIWEB.md` if the listing copy needs to change (e.g. "Current state" section, new requirements).
3. Commit, push.
4. `git tag -a vX.Y.Z -m "..."` and `git push origin vX.Y.Z`.
5. Wait for the Release workflow to attach the `.ankiaddon` to the release page.
6. **AnkiWeb is manual.** No API. Download the artifact from the GitHub release, log in to ankiweb.net, go to "Upload new version" on the existing listing (or `/shared/upload` for first publish), paste the contents of `ANKIWEB.md`'s description block, attach the file, submit. AnkiWeb assigns an immutable numeric ID on first upload; future uploads update the same listing.

### Versioning convention

- `human_version` in `manifest.json` is the source of truth users see in Tools → Add-ons.
- `ANKIWEB.md` does not embed the version inside its body — it's just the current listing copy. Version history lives in git.
- The `v*` git tag is what triggers CI. Always tag *after* committing the manifest bump.

---

## 10. Status

**End-to-end working in Anki against VOICEVOX.** Last touched 2026-05-22.

What's done:
- Full package per §4 — `addon.py`, `config.py`, `presets.py`, `routing.py`, `cache.py`, `player.py`, `_log.py`, `text/{cleanup,regex_rules}.py`, `providers/{base,voicevox}.py`, `gui/{settings,preset_editor}.py`.
- **GUI complete (initial pass):** tabbed Settings dialog with General / Providers / Presets / Routing tabs; modal preset editor with dynamic provider-options form, cleanup flags, regex rules table + Validate; live voice picker (new-preset only) with built-in test-play; quick-switcher submenu (`Tools → Local TTS · Routes`) rebuilt on `aboutToShow`.
- **Provider / preset settings split:** endpoint hoisted into `config.provider_settings`; not in `preset.fingerprint`, so moving servers doesn't invalidate cached audio. One-off migration in `scripts/migrate_provider_endpoint.py`.
- **Opus cache** via ffmpeg subprocess; WAV fallback. macOS Homebrew probing because Anki's PATH excludes `/opt/homebrew/bin`.
- **Playback fix:** `_on_done` explicitly calls `av_player.insert_file(audio_file_path)` then `cb()`. Anki's default `TTSProcessPlayer._on_done` does not auto-enqueue.
- **Diagnostics:** rotating file logger at `user_files/log/local_tts.log`; throttled tooltips (once per session per error type) on provider failure.
- **26 passing tests** under `uv run pytest`. Pure modules only; GUI / Anki-integrated code smoke-tested manually.
- `scripts/dev_link.py` (symlink into `addons21/`), `scripts/build_addon.py` (produces `.ankiaddon`).

Open follow-ups, in rough priority:
- **More providers.** Piper, Style-Bert-VITS2, generic HTTP. Add a file under `providers/`, register it in `ProviderRegistry.default()`.
- **Preset-editor "Test synthesis" button** outside the new-preset flow (the voice picker already has one).
- **AnkiWeb release.** Not yet uploaded; current install is via `scripts/dev_link.py` or `scripts/build_addon.py`.