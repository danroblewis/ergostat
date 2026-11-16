"""The world's truth about textkit: what each operation customers want should do, how much they
want it, and inputs to try it with.

This is the market, not the product. The factory's agents never read it: a ticket carries what a
customer reported (support) or what was asked for, with examples (the product manager), the way
it would in a real company. The world uses it to judge every answer the deployed product gives.
"""

from __future__ import annotations

import random
import re
import string

# ---- what customers want, most wanted first


def upper(text: str) -> str:
    return text.upper()


def lower(text: str) -> str:
    return text.lower()


def word_count(text: str) -> int:
    return len(text.split())


def slugify(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words)


def title_case(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def reverse_words(text: str) -> str:
    return " ".join(reversed(text.split()))


def snake_case(text: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", text.lower()))


def count_vowels(text: str) -> int:
    return sum(1 for c in text.lower() if c in "aeiou")


def initials(text: str) -> str:
    return "".join(w[0].upper() for w in re.findall(r"[A-Za-z]+", text))


def camel_case(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return words[0] + "".join(w[:1].upper() + w[1:] for w in words[1:]) if words else ""


def dedupe_words(text: str) -> str:
    seen, out = set(), []
    for w in text.split():
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return " ".join(out)


def rot13(text: str) -> str:
    a, b = string.ascii_lowercase, string.ascii_uppercase
    return text.translate(str.maketrans(a + b, a[13:] + a[:13] + b[13:] + b[:13]))


def strip_digits(text: str) -> str:
    return " ".join("".join(c for c in w if not c.isdigit()) for w in text.split() if any(not c.isdigit() for c in w))


def longest_word(text: str) -> str:
    words = re.findall(r"[A-Za-z]+", text)
    return max(words, key=len) if words else ""


def kebab_case(text: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))


def is_palindrome(text: str) -> bool:
    s = [c for c in text.lower() if c.isalnum()]
    return bool(s) and s == s[::-1]


def capitalize_sentences(text: str) -> str:
    parts = re.split(r"([.!?]\s+)", text.strip())
    return "".join(p[:1].upper() + p[1:] if i % 2 == 0 else p for i, p in enumerate(parts))


OPS = [upper, lower, word_count, slugify, title_case, reverse_words, snake_case, count_vowels, initials, camel_case,
       dedupe_words, rot13, strip_digits, longest_word, kebab_case, is_palindrome, capitalize_sentences]
BY_NAME = {f.__name__: f for f in OPS}

DESCRIPTIONS = {
    "upper": "the text in capitals",
    "lower": "the text in small letters",
    "word_count": "how many words: runs of characters between whitespace, however much whitespace",
    "slugify": "a URL slug: the letters and digits in lower case, each run joined to the next by one '-', nothing else",
    "title_case": "each word with its first letter a capital and the rest small, words joined by one space",
    "reverse_words": "the words in reverse order, joined by one space",
    "snake_case": "the letters and digits in lower case, each run joined to the next by one '_'",
    "count_vowels": "how many of a, e, i, o, u it holds, in either case",
    "initials": "the first letter of each run of letters, as capitals, run together",
    "camel_case": "the runs of letters and digits in lower case, the first kept small, each later one capitalised, "
                  "run together",
    "dedupe_words": "the words with every repeat after the first left out (ignoring case), joined by one space",
    "rot13": "each letter moved 13 places along the alphabet, keeping its case; everything else as it was",
    "strip_digits": "the words with their digits removed (a word that was only digits is dropped), joined by one space",
    "longest_word": "the longest run of letters (the first, if several are as long); empty if there are none",
    "kebab_case": "the letters and digits in lower case, each run joined to the next by one '-'",
    "is_palindrome": "true when its letters and digits, in lower case, read the same both ways (false when it has none)",
    "capitalize_sentences": "the text with the first letter of each sentence a capital (a sentence ends with . ! or ? "
                            "and a space)",
}

# ---- inputs, as customers type them

WORDS = ("data flow stock queue Ticket loop Goal sensor Valve deploy release Merge review agent Factory build "
         "level rate error budget oncall pager latency Cache retry backlog").split()


def phrase(rng: random.Random, digits: bool | None = None) -> str:
    n = rng.randint(1, 6)
    ws = [rng.choice(WORDS) for _ in range(n)]
    if digits if digits is not None else rng.random() < 0.3:
        ws.insert(rng.randrange(len(ws) + 1), str(rng.randint(1, 999)))
    text = ""
    for i, w in enumerate(ws):
        sep = "" if i == 0 else rng.choice([" ", " ", " ", "  ", ", ", " - "])
        text += sep + w
    if rng.random() < 0.3:
        text += rng.choice([".", "!", "?", ". and more"])
    if rng.random() < 0.15:
        text = "  " + text + " "
    return text


def examples(op: str, n: int = 3, seed: int = 7) -> list[dict]:
    """What a product manager writes into a feature ticket: plain cases, no digits."""
    rng = random.Random(f"{op}-{seed}")
    out = []
    while len(out) < n:
        t = phrase(rng, digits=False)
        out.append({"input": t, "expected": BY_NAME[op](t)})
    return out
