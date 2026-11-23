"""A dashboard's variables put into a query's text so that no value can change what the query means (SPEC §4e,
*Variables*). ``$name`` and ``${name}`` are a variable's place; each language says how a value is written there:

- Inside a string literal, a value is the string's content, escaped for that literal: it cannot end the string.
- In PromQL, a string after ``=~`` or ``!~`` is a regular expression: each value is escaped as a literal (RE2), and
  several are ``(?:a|b)``. Anywhere else a string takes exactly one value.
- Outside a string a value must be a bare name or a number or duration (not a keyword), and only one: anything else is
  refused, never written in.
- A PromQL comment is left as it is.

A language with no rules here refuses every variable it is given (fail closed). ``analysis`` and ``model`` (the call
syntax of the chart catalog, ``psd(A, detrend="linear")``) have the call rules, ready for when those types exist. A name
that is not among the variables given is left as written."""

from __future__ import annotations

import re

from . import SourceError

NAME = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_METRIC = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]*\Z")
_NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]+)?|(?:[0-9]+(?:ms|[smhdwy]))+)\Z")
_KEYWORDS = {"and", "or", "unless", "by", "without", "on", "ignoring", "group_left", "group_right", "offset", "bool",
             "atan2", "start", "end", "if", "else", "not", "in", "is", "true", "false", "null", "none"}
_RE2_SPECIAL = set("\\.+*?()|[]{}^$")


class Rules:
    def __init__(self, quotes: str, comment: str | None, regex: bool, bare: re.Pattern):
        self.quotes, self.comment, self.regex, self.bare = quotes, comment, regex, bare


PROMQL = Rules("\"'`", "#", True, _METRIC)
CALLS = Rules("\"'", None, False, _IDENT)
LANGUAGES = {"promql": PROMQL, "analysis": CALLS, "model": CALLS}


def uses(text: str) -> set[str]:
    """The variable names a text names."""
    return {a or b for a, b in NAME.findall(text or "")}


def _literal(value: str, quote: str) -> str:
    """A value as the content of a string literal opened by ``quote``."""
    if quote == "`":                                # a raw string has no escapes: a backtick could only end it
        if "`" in value:
            raise SourceError("refused", "a variable's value holds a backtick, which a `raw string` cannot hold")
        return value
    out = []
    for c in value:
        if c == "\\" or c == quote:
            out.append("\\" + c)
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    return "".join(out)


def _regex(value: str) -> str:
    return "".join("\\" + c if c in _RE2_SPECIAL else c for c in value)


def _matcher_before(text: str, at: int) -> bool:
    """Whether the string opening at ``at`` follows ``=~`` or ``!~``."""
    before = text[:at].rstrip()
    return before.endswith("=~") or before.endswith("!~")


def _one(name: str, values: list) -> str:
    if len(values) != 1:
        raise SourceError("refused", f"${name} has {len(values)} values selected and is used where one goes; "
                                     "in PromQL match several with =~")
    return values[0]


def _value(name: str, values: list, quote: str | None, regex: bool, rules: Rules) -> str:
    if not values:
        raise SourceError("refused", f"${name} has no value selected")
    if quote is None:
        v = _one(name, values)
        if not (rules.bare.match(v) or _NUMBER.match(v)) or v.lower() in _KEYWORDS:
            raise SourceError("refused", f"${name}'s value {v[:60]!r} is not a plain name or number, so it can only "
                                         "go inside quotes")
        return v
    if regex:
        parts = [_regex(v) for v in values]
        return _literal(parts[0] if len(parts) == 1 else "(?:" + "|".join(parts) + ")", quote)
    return _literal(_one(name, values), quote)


def interpolate(language: str, text: str, given: dict) -> str:
    """``text`` with each variable in ``given`` (name: list of values) written in, by ``language``'s rules; SourceError
    (refused) when a value cannot go where it is used, or the language has no rules and a variable is used."""
    named = {n for n in uses(text) if n in given}
    if not named:
        return text
    rules = LANGUAGES.get(str(language).lower())
    if rules is None:
        raise SourceError("refused", f"variables cannot be used in {language}: there are no rules yet to write a "
                                     "value in safely")
    out, i, quote, regex, n = [], 0, None, False, len(text)
    while i < n:
        c = text[i]
        if quote is None and rules.comment and c == rules.comment:
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(text[i:end])
            i = end
            continue
        if quote is not None and c == "\\" and quote != "`":
            out.append(text[i:i + 2])
            i += 2
            continue
        if c in rules.quotes and (quote is None or c == quote):
            if quote is None:
                quote, regex = c, rules.regex and _matcher_before(text, i)
            else:
                quote = None
            out.append(c)
            i += 1
            continue
        m = NAME.match(text, i) if c == "$" else None
        if m and (m.group(1) or m.group(2)) in given:
            name = m.group(1) or m.group(2)
            values = [str(v) for v in given[name]]
            out.append(_value(name, values, quote, regex, rules))
            i = m.end()
            continue
        out.append(c)
        i += 1
    return "".join(out)
