from local_tts.presets import CleanupOptions, Preset, RegexRule


def _preset(**kw) -> Preset:
    return Preset(name="p", provider="voicevox", **kw)


def test_fingerprint_stable_across_key_order():
    a = Preset.from_dict({"name": "p", "provider": "voicevox", "options": {"a": 1, "b": 2}})
    b = Preset.from_dict({"name": "p", "provider": "voicevox", "options": {"b": 2, "a": 1}})
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_ignores_name_cleanup_and_regex():
    a = _preset(options={"speaker_id": 1})
    b = Preset(
        name="different",
        provider="voicevox",
        options={"speaker_id": 1},
        cleanup=CleanupOptions(ruby_mode="reading"),
        regex_rules=[RegexRule(pattern="x", replacement="y")],
    )
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_changes_with_options():
    a = _preset(options={"speaker_id": 1})
    b = _preset(options={"speaker_id": 2})
    assert a.fingerprint() != b.fingerprint()


def test_roundtrip_minimal_no_overrides():
    raw = {"name": "p", "provider": "voicevox", "options": {"speaker_id": 8}}
    assert Preset.from_dict(raw).to_dict() == raw


def test_roundtrip_with_overrides():
    raw = {
        "name": "p",
        "provider": "voicevox",
        "options": {"speaker_id": 8},
        "cleanup": {"ruby_mode": "reading", "bracket_mode": "base",
                    "brackets": ["[]"], "collapse_cjk_spaces": True},
        "regex_rules": [{"pattern": "a", "replacement": "b", "enabled": True}],
    }
    assert Preset.from_dict(raw).to_dict() == raw


def test_override_distinguishes_none_from_empty_list():
    no_override = Preset.from_dict({"name": "p", "provider": "voicevox"})
    empty_override = Preset.from_dict({"name": "p", "provider": "voicevox", "regex_rules": []})
    assert no_override.regex_rules is None
    assert empty_override.regex_rules == []


def test_player_treats_empty_regex_override_as_inherit():
    """Mirrors `player._play`: empty list and None both fall back to global.

    Older versions saved `regex_rules: []` on every preset regardless of
    intent; legacy data must not silently suppress every global rule.
    """
    global_rules = [RegexRule(pattern="A", replacement="B")]
    own_rules = [RegexRule(pattern="X", replacement="Y")]

    def resolve(preset_rules):
        return preset_rules if preset_rules else global_rules

    assert resolve(None) is global_rules
    assert resolve([]) is global_rules
    assert resolve(own_rules) is own_rules
