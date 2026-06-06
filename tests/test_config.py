from local_tts.config import Config
from local_tts.presets import CleanupOptions, RegexRule


def test_provider_settings_roundtrip():
    raw = {
        "provider_settings": {"voicevox": {"endpoint": "http://example:50021"}},
    }
    cfg = Config.from_dict(raw)
    assert cfg.provider_settings == {"voicevox": {"endpoint": "http://example:50021"}}
    assert cfg.to_dict()["provider_settings"] == raw["provider_settings"]


def test_global_cleanup_and_regex_roundtrip():
    raw = {
        "cleanup": {"ruby_mode": "reading", "bracket_mode": "base",
                    "brackets": ["[]"], "collapse_cjk_spaces": False},
        "regex_rules": [{"pattern": "20日", "replacement": "はつか", "enabled": True}],
    }
    cfg = Config.from_dict(raw)
    assert cfg.cleanup.ruby_mode == "reading"
    assert cfg.cleanup.collapse_cjk_spaces is False
    assert cfg.regex_rules == [RegexRule(pattern="20日", replacement="はつか", enabled=True)]
    out = cfg.to_dict()
    assert out["cleanup"] == raw["cleanup"]
    assert out["regex_rules"] == raw["regex_rules"]


def test_defaults_when_nothing_provided():
    cfg = Config.from_dict({})
    assert cfg.cleanup == CleanupOptions()
    assert cfg.regex_rules == []
    assert cfg.voice_defaults == {"speed": 1.0, "pitch": 0.0, "intonation": 1.0, "volume": 1.0}


def test_voice_defaults_roundtrip():
    raw = {"voice_defaults": {"speed": 0.95, "pitch": 0.0, "intonation": 1.1, "volume": 1.4}}
    cfg = Config.from_dict(raw)
    assert cfg.voice_defaults == raw["voice_defaults"]
    assert cfg.to_dict()["voice_defaults"] == raw["voice_defaults"]


def test_preset_override_does_not_leak_into_global():
    raw = {
        "presets": [
            {"name": "p", "provider": "voicevox",
             "cleanup": {"ruby_mode": "reading", "bracket_mode": "base",
                         "brackets": ["[]"], "collapse_cjk_spaces": True},
             "regex_rules": [{"pattern": "a", "replacement": "b", "enabled": True}]},
        ],
    }
    cfg = Config.from_dict(raw)
    assert cfg.cleanup == CleanupOptions()
    assert cfg.regex_rules == []
    assert cfg.presets[0].cleanup is not None
    assert cfg.presets[0].cleanup.ruby_mode == "reading"
    assert cfg.presets[0].regex_rules == [RegexRule(pattern="a", replacement="b", enabled=True)]


def test_per_preset_validation_errors_still_surfaced():
    cfg = Config.from_dict({
        "presets": [
            {"name": "p", "provider": "voicevox",
             "regex_rules": [{"pattern": "(bad", "replacement": ""}]},
        ],
    })
    msgs = cfg.validation_errors()
    assert len(msgs) == 1 and "'p'" in msgs[0] and "(bad" in msgs[0]
