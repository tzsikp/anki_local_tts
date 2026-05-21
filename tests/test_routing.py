from local_tts.config import Config, RoutingConfig
from local_tts.presets import Preset
from local_tts.routing import Router


def _cfg() -> Config:
    return Config(
        default_preset="default",
        routing=RoutingConfig(
            by_deck={"1": "deck_preset"},
            by_notetype={"100": "nt_preset"},
            by_language={"ja": "lang_preset"},
        ),
        presets=[
            Preset(name="default", provider="voicevox"),
            Preset(name="deck_preset", provider="voicevox"),
            Preset(name="nt_preset", provider="voicevox"),
            Preset(name="lang_preset", provider="voicevox"),
        ],
    )


def test_deck_wins():
    r = Router(_cfg())
    p = r.resolve(deck_id=1, notetype_id=100, lang="ja_JP")
    assert p is not None and p.name == "deck_preset"


def test_notetype_wins_over_lang():
    r = Router(_cfg())
    p = r.resolve(deck_id=999, notetype_id=100, lang="ja_JP")
    assert p is not None and p.name == "nt_preset"


def test_lang_fallback():
    r = Router(_cfg())
    p = r.resolve(deck_id=999, notetype_id=999, lang="ja_JP")
    assert p is not None and p.name == "lang_preset"


def test_default():
    r = Router(_cfg())
    p = r.resolve(deck_id=999, notetype_id=999, lang="fr_FR")
    assert p is not None and p.name == "default"
