from local_tts.text.auto_marker import auto_mark_digit_pauses


def _amp(text: str, marker: str = "・") -> str:
    return auto_mark_digit_pauses(text, marker)


# ---- catches ----

def test_cjk_digits_between():
    assert _amp("三、四倍") == "三・四倍"


def test_arabic_digits_between():
    assert _amp("2023、2024") == "2023・2024"


def test_fullwidth_digits():
    assert _amp("１、２百") == "１・２百"


def test_mixed_halfwidth_and_fullwidth():
    assert _amp("１、2百") == "１・2百"


def test_kanji_compound_digits():
    assert _amp("三十、四十") == "三十・四十"


def test_chain_rewrites_in_single_pass():
    """Lookarounds don't consume — `三、五、七` collapses fully, not partially."""
    assert _amp("三、五、七") == "三・五・七"


def test_inside_japanese_sentence():
    assert _amp("年に一、二回") == "年に一・二回"


def test_juu_then_single_digit():
    # `十三、四` — last char before `、` is `三` (digit), first after is `四` (digit).
    assert _amp("十三、四") == "十三・四"


# ---- ignores ----

def test_non_digit_neighbour_left():
    assert _amp("日本、英語") == "日本、英語"
    assert _amp("数千、数万") == "数千、数万"  # `数` not in digit class


def test_non_digit_neighbour_right():
    # `三、月` (3, [the word] month) — `月` is not a digit.
    assert _amp("三月、四月") == "三月、四月"


def test_no_comma_returns_unchanged():
    assert _amp("年に三四回") == "年に三四回"


def test_only_natural_commas_untouched():
    assert _amp("こんにちは、世界") == "こんにちは、世界"


# ---- guards ----

def test_empty_marker_is_noop():
    assert _amp("三、四", marker="") == "三、四"


def test_uses_configured_marker():
    assert _amp("三、四", marker="|") == "三|四"


def test_empty_text():
    assert _amp("") == ""


def test_does_not_touch_other_punctuation():
    assert _amp("三 四") == "三 四"
    assert _amp("三。四") == "三。四"
