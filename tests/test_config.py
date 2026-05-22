from local_tts.config import Config


def test_provider_settings_roundtrip():
    raw = {
        "provider_settings": {"voicevox": {"endpoint": "http://example:50021"}},
    }
    cfg = Config.from_dict(raw)
    assert cfg.provider_settings == {"voicevox": {"endpoint": "http://example:50021"}}
    assert cfg.to_dict()["provider_settings"] == raw["provider_settings"]
