from local_tts.text.cleanup import collapse_cjk_spaces
from local_tts.text.digit_kanji import convert, int_to_kanji


def test_small_integers():
    assert int_to_kanji(0) == "零"
    assert int_to_kanji(1) == "一"
    assert int_to_kanji(9) == "九"
    assert int_to_kanji(10) == "十"
    assert int_to_kanji(11) == "十一"
    assert int_to_kanji(20) == "二十"
    assert int_to_kanji(99) == "九十九"


def test_hundreds_and_thousands():
    assert int_to_kanji(100) == "百"
    assert int_to_kanji(200) == "二百"
    assert int_to_kanji(999) == "九百九十九"
    assert int_to_kanji(1000) == "千"
    assert int_to_kanji(1990) == "千九百九十"
    assert int_to_kanji(2024) == "二千二十四"


def test_man_and_above():
    assert int_to_kanji(10_000) == "一万"
    assert int_to_kanji(12_345) == "一万二千三百四十五"
    assert int_to_kanji(100_000) == "十万"
    assert int_to_kanji(1_000_000) == "百万"
    assert int_to_kanji(100_000_000) == "一億"
    assert int_to_kanji(123_456_789) == "一億二千三百四十五万六千七百八十九"


def test_negative():
    assert int_to_kanji(-5) == "マイナス五"


def test_convert_replaces_digit_runs():
    assert convert("1990年") == "千九百九十年"
    assert convert("100円") == "百円"
    assert convert("７月") == "七月"
    assert convert("２０２４年") == "二千二十四年"


def test_convert_idempotent_without_digits():
    text = "今日は晴れです。"
    assert convert(text) == text


def test_convert_multiple_runs():
    assert convert("1月2日") == "一月二日"
    assert convert("年に1、2回") == "年に一、二回"


def test_convert_empty():
    assert convert("") == ""


def test_convert_mixed_widths():
    assert convert("1２3") == "百二十三"


# --- digit→kanji + collapse_cjk_spaces -----------------------------------
#
# Mirrors what player.py does after the conversion: bracket stripping
# can leave a space between an ASCII digit and a kanji (`7 月`) that the
# first cleanup pass can't remove because `7` isn't in the CJK class.
# Once we rewrite the digit, the space becomes CJK-CJK and the
# follow-up collapse must remove it.


def _convert_and_collapse(text: str) -> str:
    return collapse_cjk_spaces(convert(text))


def test_collapse_after_conversion_removes_space():
    assert _convert_and_collapse("7 月") == "七月"


def test_collapse_after_conversion_real_sentence():
    text = "祇園祭は京都で7 月に1か月続く"
    assert _convert_and_collapse(text) == "祇園祭は京都で七月に一か月続く"


def test_collapse_after_conversion_preserves_ascii_word_boundary():
    # Space between a digit and a Latin word must stay — the digit
    # neighbour becomes kanji, but the other side is still ASCII so
    # the JP-inner-space rule should not fire.
    assert _convert_and_collapse("7 days") == "七 days"


def test_collapse_after_conversion_multiple_runs():
    assert _convert_and_collapse("1 月 と 2 月") == "一月と二月"
