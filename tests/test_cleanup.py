from local_tts.presets import CleanupOptions
from local_tts.text import cleanup


def _opts(**kw) -> CleanupOptions:
    return CleanupOptions(**kw)


def test_strip_html():
    assert cleanup.clean("<div>今日は</div>", _opts()) == "今日は"


def test_ruby_base():
    out = cleanup.clean("<ruby>本<rt>ほん</rt></ruby>", _opts(ruby_mode="base"))
    assert out == "本"


def test_ruby_reading():
    out = cleanup.clean("<ruby>本<rt>ほん</rt></ruby>", _opts(ruby_mode="reading"))
    assert out == "ほん"


def test_bracket_base():
    out = cleanup.clean("日々[ひび]勉強", _opts(bracket_mode="base"))
    assert out == "日々勉強"


def test_bracket_reading():
    out = cleanup.clean("日々[ひび]", _opts(bracket_mode="reading"))
    assert out == "ひび"


def test_cloze():
    assert cleanup.clean("{{c1::日本語}}", _opts()) == "日本語"


def test_whitespace():
    assert cleanup.clean("  a    b\n\nc  ", _opts()) == "a b c"


def test_collapse_cjk_spaces_furigana_addon_output():
    src = "電車[でんしゃ]の 遅延[ちえん]のため、 旅行保険[りょこうほけん]に 入[はい]っていた 乗客[じょうきゃく]にチケット 代[だい]が 払[はら]い 戻[もど]されました。"
    assert cleanup.clean(src, _opts()) == "電車の遅延のため、旅行保険に入っていた乗客にチケット代が払い戻されました。"


def test_collapse_cjk_spaces_preserves_mixed_language():
    assert cleanup.clean("今日は Tuesday です", _opts()) == "今日は Tuesday です"
    assert cleanup.clean("hello world", _opts()) == "hello world"
    assert cleanup.clean("日本 と USA", _opts()) == "日本と USA"


def test_collapse_cjk_spaces_can_be_disabled():
    out = cleanup.clean("日々[ひび] 勉強", _opts(collapse_cjk_spaces=False))
    assert out == "日々 勉強"


def test_validate_pattern():
    from local_tts.text.regex_rules import validate_pattern

    assert validate_pattern(r"abc") is None
    assert validate_pattern(r"(?P<n>\d+)") is None
    err = validate_pattern(r"(unclosed")
    assert err is not None and err


def test_validate_rules_returns_only_broken():
    from local_tts.presets import RegexRule
    from local_tts.text.regex_rules import validate_rules

    rules = [
        RegexRule(pattern=r"ok", replacement=""),
        RegexRule(pattern=r"(broken", replacement=""),
        RegexRule(pattern=r"also[ok]", replacement=""),
    ]
    errors = validate_rules(rules)
    assert len(errors) == 1
    assert errors[0][0].pattern == "(broken"


def _pipeline(text: str, rules, **cleanup_kw) -> str:
    """Mirrors `player._play`: cleanup first, then user regex rules."""
    from local_tts.text import regex_rules
    return regex_rules.apply(cleanup.clean(text, _opts(**cleanup_kw)), rules)


def test_regex_runs_after_cleanup_on_html_input():
    from local_tts.presets import RegexRule
    rules = [RegexRule(pattern="背負ってくる", replacement="しょってくる")]
    assert _pipeline("<div>背負ってくる</div>", rules) == "しょってくる"


def test_regex_sees_bracket_stripped_text():
    from local_tts.presets import RegexRule
    rules = [RegexRule(pattern="背負ってくる", replacement="しょってくる")]
    assert _pipeline("背負[しょ]ってくる", rules, bracket_mode="base") == "しょってくる"


def test_regex_disabled_rule_is_skipped():
    from local_tts.presets import RegexRule
    rules = [RegexRule(pattern="背負ってくる", replacement="しょってくる", enabled=False)]
    assert _pipeline("背負ってくる", rules) == "背負ってくる"


def test_regex_rules_apply_in_order():
    from local_tts.presets import RegexRule
    rules = [
        RegexRule(pattern="A", replacement="B"),
        RegexRule(pattern="B", replacement="C"),
    ]
    assert _pipeline("A", rules) == "C"


def test_regex_does_not_run_on_ruby_reading_when_mode_base():
    from local_tts.presets import RegexRule
    rules = [RegexRule(pattern="ほん", replacement="X")]
    assert _pipeline("<ruby>本<rt>ほん</rt></ruby>", rules, ruby_mode="base") == "本"


def test_regex_runs_against_ruby_reading_when_mode_reading():
    from local_tts.presets import RegexRule
    rules = [RegexRule(pattern="ほん", replacement="X")]
    assert _pipeline("<ruby>本<rt>ほん</rt></ruby>", rules, ruby_mode="reading") == "X"


def test_regex_runs_after_cloze_strip():
    from local_tts.presets import RegexRule
    rules = [RegexRule(pattern="面倒臭い", replacement="めんどくさい")]
    assert _pipeline("{{c1::面倒臭い}}", rules) == "めんどくさい"


def test_broken_pattern_does_not_crash_pipeline():
    from local_tts.presets import RegexRule
    rules = [
        RegexRule(pattern="(broken", replacement=""),
        RegexRule(pattern="ok", replacement="OK"),
    ]
    assert _pipeline("ok", rules) == "OK"


def test_config_surfaces_validation_errors():
    from local_tts.config import Config

    cfg = Config.from_dict({
        "regex_rules": [{"pattern": "(bad", "replacement": ""}],
    })
    msgs = cfg.validation_errors()
    assert len(msgs) == 1 and "Global" in msgs[0] and "(bad" in msgs[0]
