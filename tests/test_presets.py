from local_tts.presets import Preset, RegexRule


def _preset(**kw) -> Preset:
    return Preset(name="p", provider="voicevox", **kw)


def test_fingerprint_stable_across_key_order():
    a = Preset.from_dict({"name": "p", "provider": "voicevox", "options": {"a": 1, "b": 2}})
    b = Preset.from_dict({"name": "p", "provider": "voicevox", "options": {"b": 2, "a": 1}})
    assert a.fingerprint() == b.fingerprint()


def test_fingerprint_changes_with_regex():
    base = _preset()
    other = _preset(regex_rules=[RegexRule(pattern="x", replacement="y")])
    assert base.fingerprint() != other.fingerprint()


def test_roundtrip():
    raw = {
        "name": "p",
        "provider": "voicevox",
        "options": {"speaker_id": 8},
        "cleanup": {"ruby_mode": "reading", "bracket_mode": "base", "brackets": ["[]"], "collapse_cjk_spaces": True},
        "regex_rules": [{"pattern": "a", "replacement": "b", "enabled": True}],
    }
    assert Preset.from_dict(raw).to_dict() == raw
