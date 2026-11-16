"""textkit's own tests: run with python3 test_textkit.py (no other tools needed)."""

import textkit


def test_upper():
    assert textkit.upper("data flow") == "DATA FLOW"


def test_lower():
    assert textkit.lower("Data Flow") == "data flow"


def test_word_count():
    assert textkit.word_count("one two three") == 3


def test_slugify():
    assert textkit.slugify("Data Flow") == "data-flow"


def test_title_case():
    assert textkit.title_case("data flow") == "Data Flow"


def test_reverse_words():
    assert textkit.reverse_words("a b c") == "c b a"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as e:                      # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"{'ok' if not failed else 'FAILED'}: {failed} failed")
    raise SystemExit(1 if failed else 0)
