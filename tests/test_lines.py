import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lines import LINES, LINES_HI, fallback_line  # noqa: E402
from app.safety import (SAFE_OUTPUT_CHARS, forbidden_in_output, has_digits, is_profane_name, is_rude,  # noqa: E402
                        money_in_words)
from app.voice import PRICE_KINDS  # noqa: E402
from app.lang import HINDI_LATIN  # noqa: E402


def test_every_builtin_line_obeys_the_same_rules_as_ai_output():
    for book, hindi in ((LINES, False), (LINES_HI, True)):
        for kind, pool in book.items():
            for line in pool:
                body = line.replace("{PRICE}", "").replace("{item}", "umbrella")
                assert SAFE_OUTPUT_CHARS.match(body) and len(line) <= 240, (kind, line)
                assert not forbidden_in_output(body) and not has_digits(body) and not money_in_words(body), (kind, line)
                if not hindi:
                    assert len(HINDI_LATIN.findall(body)) <= 3, (kind, line)
                n = line.count("{PRICE}")
                if kind in PRICE_KINDS or kind in ("DEAL_BIG", "RAISE_LOW"):
                    assert n <= 1, (kind, line)
                else:
                    assert n == 0, (kind, line)


def test_every_kind_has_english_and_hindi_lines():
    assert set(LINES) == set(LINES_HI)


def test_every_decision_that_names_a_price_has_built_in_lines_that_state_it_once():
    for book in (LINES, LINES_HI):
        for kind in PRICE_KINDS + ("DEAL_BIG", "RAISE_LOW"):
            assert book[kind] and all(line.count("{PRICE}") == 1 for line in book[kind]), kind
    assert "₹1,950" in fallback_line("RAISE", "p1", "umbrella", 1950) and "₹1,950" in fallback_line("RAISE", "p1", "umbrella", 1950, script="devanagari")
    assert "₹1,950" in fallback_line("RAISE_LOW", "p1", "umbrella", 1950) and "₹1,950" in fallback_line("RAISE_LOW", "p1", "umbrella", 1950, script="devanagari")


def test_fallback_fills_the_price_and_the_language():
    en = fallback_line("DEAL", "p1", "umbrella", 359, False, "latin")
    hi = fallback_line("DEAL", "p1", "umbrella", 359, False, "devanagari")
    assert "₹359" in en and "₹359" in hi and re.search(r"[\u0900-\u097F]", hi) and not re.search(r"[\u0900-\u097F]", en)
    assert "{PRICE}" not in fallback_line("INSULT", "p1", "umbrella") and "₹" not in fallback_line("INSULT", "p1", "umbrella")


def test_fallback_never_repeats_back_to_back():
    seen = [fallback_line("COUNTER", "p1", "bag", 900) for _ in range(40)]
    assert all(a != b for a, b in zip(seen, seen[1:]))


def test_nobody_is_called_bhaiya_any_more():
    for pool in list(LINES.values()) + list(LINES_HI.values()):
        assert not any("bhaiya" in line.lower() or "भैया" in line for line in pool)


def test_word_filters_do_not_trip_on_real_indian_names():
    for name in ("Kshitij", "Nazia", "Ashit", "Rishit", "Poornima", "Brandon", "Scunthorpe", "Grapes", "सिद्धार्थ", "மணிகண்டன்"):
        assert not is_rude(name) and not is_profane_name(name), name
    for rude in ("you idiot", "stupid shop", "fuck this", "what a loser", "तुम बेवकूफ हो", "गधा कहीं का"):
        assert is_rude(rude), rude
    for bad in ("fuck face", "भेनचोद"):
        assert is_profane_name(bad), bad
