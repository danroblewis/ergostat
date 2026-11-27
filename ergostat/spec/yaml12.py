"""Where YAML 1.1 and YAML 1.2 read a plain scalar differently (SPEC §3, *Which YAML*).

The model's files are read with PyYAML, which follows YAML 1.1: ``9:30`` is 570 (a base-60 number), ``010`` is 8
(octal), ``1_000`` is 1000, ``0b101`` is 5, ``2026-11-18`` a date, while ``1e3`` and ``0o17`` stay text. YAML 1.2's
core schema, which the format follows, reads each the other way (``9:30`` and ``2026-11-18`` are text, ``010`` is
10, ``1e3`` is 1000). ``yes``, ``no``, ``on`` and ``off`` are text to ergostat and to YAML 1.2 already (the loader
dropped 1.1's booleans), but booleans to any YAML 1.1 reader. ``ambiguous`` says, for one plain scalar, what it is
read as and the form to write instead, or None when every reader agrees."""

from __future__ import annotations

import datetime
import math
import re

INT = re.compile(r"[-+]?[0-9]+")
OCT = re.compile(r"0o[0-7]+")
HEX = re.compile(r"0x[0-9a-fA-F]+")
FLOAT = re.compile(r"[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?")
INF = re.compile(r"[-+]?\.(?:inf|Inf|INF)")
NAN = re.compile(r"\.(?:nan|NaN|NAN)")
NULL = {"", "~", "null", "Null", "NULL"}
TRUE, FALSE = {"true", "True", "TRUE"}, {"false", "False", "FALSE"}
WORDS = {"yes", "Yes", "YES", "no", "No", "NO", "on", "On", "ON", "off", "Off", "OFF"}


def core(text: str):
    """The value YAML 1.2's core schema gives a plain scalar."""
    if text in NULL:
        return None
    if text in TRUE or text in FALSE:
        return text in TRUE
    if INT.fullmatch(text):
        return int(text, 10)
    if OCT.fullmatch(text):
        return int(text[2:], 8)
    if HEX.fullmatch(text):
        return int(text[2:], 16)
    if FLOAT.fullmatch(text):
        return float(text)
    if INF.fullmatch(text):
        return -math.inf if text.startswith("-") else math.inf
    if NAN.fullmatch(text):
        return math.nan
    return text


def _same(a, b) -> bool:
    if type(a) is not type(b):
        return isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool) \
            and not isinstance(b, bool) and a == b
    return a == b or (isinstance(a, float) and math.isnan(a) and math.isnan(b))


def _shown(v) -> str:
    if isinstance(v, datetime.date):
        return f"a date ({v.isoformat()})"
    if isinstance(v, str):
        return f"the text {v}"
    return f"the number {v:g}" if isinstance(v, float) else f"the number {v}"


def ambiguous(text: str, read, key: bool = False) -> str | None:
    """What is wrong with a plain scalar ``text`` that the loader read as ``read``, and how to write it, or None."""
    if text in WORDS:
        if key:                                       # the format's own keys (a projection's on:) are words
            return None
        return (f"{text} is read as the text {text!r} here and in YAML 1.2, but as a boolean by YAML 1.1 readers; "
                f"write \"{text}\" (quoted) for the text, or {'true' if text.lower() in ('yes', 'on') else 'false'} "
                f"for a boolean")
    other = core(text)
    if _same(read, other):
        return None
    why = ("a time of day is read as a number of minutes or seconds, base 60" if ":" in text and isinstance(read, int | float)
           else "a number with a leading 0 is read as octal" if isinstance(read, int) and re.fullmatch(r"[-+]?0[0-7]+", text)
           else "_ in a number is dropped" if "_" in text
           else "0b is read as binary" if text.lstrip("+-").startswith("0b")
           else "a date is read as a date, not text" if isinstance(read, datetime.date)
           else "0o is not octal, so it stays text" if isinstance(read, str) and "0o" in text
           else "an exponent needs a sign and a decimal point, so it stays text" if isinstance(read, str)
           else "YAML 1.1 and 1.2 disagree")
    say = f"\"{text}\" (quoted) for the text"
    num = next((x for x in (other, read) if isinstance(x, int | float) and not isinstance(x, bool)), None)
    if num is not None:
        say += f", or {num:g} for the number" if isinstance(num, float) else f", or {num} for the number"
    return (f"{text} is read as {_shown(read)} (YAML 1.1: {why}); YAML 1.2 reads {_shown(other)}. Write {say}")
