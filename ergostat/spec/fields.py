"""A projection's fields (SPEC §5a): what an object is, each field's type and how values from events fold into it.

``fields: {NAME: {type, fold, description}}``. A type is ``text``, ``number``, ``integer``, ``boolean``, ``time``,
``duration``, ``map``, ``list of T`` or ``one of [a, b, ...]`` (left out: any value). A fold is how a value an event
gives combines with the field's: ``replace`` (the default: newest by event time wins), ``first`` (the earliest by event
time), ``add``, ``min``, ``max``, ``append`` / ``append(N)``, ``union``, ``merge``, ``count``, ``mean``, ``variance``,
``stdev``, ``rms``, or a model's own function. An events entry's plain value is folded by its field's rule; a fold call
in it (``set(...)``, ``add(...)``) is that kind's own rule for the field."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

BASE = ("text", "number", "integer", "boolean", "time", "duration", "map")
FOLDS = ("replace", "first", "add", "min", "max", "append", "union", "merge", "count", "mean", "variance", "stdev", "rms")
NUMERIC = ("number", "integer", "duration")
FITS = {                                         # a fold, and the types it fits (None: any type)
    "replace": None, "set": None, "first": None, "unset": None,
    "add": ("number", "integer", "duration"), "min": ("number", "integer", "time", "duration", "text"),
    "max": ("number", "integer", "time", "duration", "text"), "append": ("list",), "union": ("list",),
    "remove": ("list",), "merge": ("map",), "count": ("integer", "number"), "mean": ("number",),
    "variance": ("number",), "stdev": ("number",), "rms": ("number",)}
CALL = {"replace": "set", "add": "add"}          # a fold's function in an expression (else its own name)
_ONE_OF = re.compile(r"^\s*one\s+of\s*\[(.*)\]\s*$", re.S)
_LIST_OF = re.compile(r"^\s*list\s+of\s+(.+)$", re.S)
_APPEND = re.compile(r"^\s*append\s*\(\s*(\d+)\s*\)\s*$")


class BadField(ValueError):
    def __init__(self, msg: str, code: str = "bad-field"):
        super().__init__(msg)
        self.code = code


@dataclass
class Type:
    base: str | None                 # None: any value; "list", "one of", or one of BASE
    of: Type | None = None           # a list's members
    values: list = field(default_factory=list)   # one of: its values, in order

    def __str__(self) -> str:
        if self.base is None:
            return "any"
        if self.base == "list":
            return f"list of {self.of}"
        if self.base == "one of":
            return "one of [" + ", ".join(self.values) + "]"
        return self.base

    def fits(self, v) -> bool:
        """Whether value ``v`` is one of this type's (null always is: the field is empty)."""
        b = self.base
        if v is None or b is None:
            return True
        if b == "text":
            return isinstance(v, str)
        if b == "number":
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        if b == "integer":
            return type(v) is int or (isinstance(v, float) and v.is_integer())
        if b == "boolean":
            return isinstance(v, bool)
        if b == "time":
            return (isinstance(v, (int, float)) and not isinstance(v, bool)) or (isinstance(v, str) and seconds(v) is not None)
        if b == "duration":
            return (isinstance(v, (int, float)) and not isinstance(v, bool)) or isinstance(v, str)
        if b == "map":
            return isinstance(v, dict)
        if b == "list":
            return isinstance(v, list) and all(self.of.fits(x) for x in v)
        if b == "one of":
            return isinstance(v, str) and v in self.values
        return True


def seconds(v) -> float | None:
    """A time as seconds since the epoch: a number as it is, ISO 8601 text read; None when it is neither."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if not isinstance(v, str) or not v[:4].isdigit():
        return None
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        from datetime import timezone
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def parse_type(raw) -> Type:
    if raw is None:
        return Type(None)
    if isinstance(raw, dict) and set(raw) == {"one of"} and isinstance(raw["one of"], list):
        return Type("one of", values=[str(x) for x in raw["one of"]])
    if isinstance(raw, list):                       # [a, b]: one of them
        return Type("one of", values=[str(x) for x in raw])
    if not isinstance(raw, str):
        raise BadField(f"{raw!r} is not a type ({', '.join(BASE)}, list of T, one of [a, b])", "bad-type")
    t = raw.strip()
    if t in BASE:
        return Type(t)
    if m := _ONE_OF.match(t):
        vals = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
        if not vals:
            raise BadField("one of [...]: name its values", "bad-type")
        return Type("one of", values=vals)
    if m := _LIST_OF.match(t):
        return Type("list", of=parse_type(m.group(1)))
    if t == "list":
        return Type("list", of=Type(None))
    raise BadField(f"{raw!r} is not a type ({', '.join(BASE)}, list of T, one of [a, b])", "bad-type")


@dataclass
class Field:
    name: str
    type: Type
    fold: str = "replace"            # one of FOLDS, or a model's own function's name
    bound: int | None = None         # append(N): the last N kept
    description: str = ""

    def spec(self) -> dict:
        return {"type": str(self.type), "fold": self.fold + (f"({self.bound})" if self.bound else ""),
                **({"description": self.description} if self.description else {})}


def fits(fold: str, t: Type) -> bool:
    """Whether fold rule ``fold`` fits type ``t`` (a model's own function fits any)."""
    ok = FITS.get(fold)
    return ok is None or t.base is None or t.base in ok


def parse_field(name: str, raw, functions: dict) -> Field:
    """A ``fields:`` entry: ``{type, fold, description}``, a type alone (``text``), or nothing (any value, replace)."""
    if raw is None or isinstance(raw, str) and not raw.strip():
        return Field(name, Type(None))
    if isinstance(raw, (str, list)):
        return Field(name, parse_type(raw))
    if not isinstance(raw, dict):
        raise BadField(f"{json.dumps(raw, default=str)[:60]}: a field is {{type, fold, description}}")
    bad = set(raw) - {"type", "fold", "description"}
    if bad:
        raise BadField(f"{', '.join(sorted(map(str, bad)))}: a field says only type, fold and description")
    t = parse_type(raw.get("type"))
    fold, bound = str(raw.get("fold") or "replace").strip(), None
    if m := _APPEND.match(fold):
        fold, bound = "append", int(m.group(1))
        if bound < 1:
            raise BadField("append(N): N is 1 or more", "bad-fold")
    if fold not in FOLDS and fold not in functions:
        raise BadField(f"fold: {fold!r} is not a fold ({', '.join(FOLDS)}, append(N), or one of the model's functions)",
                       "unknown-function")
    if not fits(fold, t):
        raise BadField(f"fold: {fold} does not fit a {t} (it folds {', '.join(FITS[fold])})", "bad-fold")
    return Field(name, t, fold, bound, str(raw.get("description") or ""))


def wrapped(f: Field, text: str) -> str:
    """A plain value's expression folded by its field's rule: ``data.x`` for a field that adds is ``add(data.x)``."""
    if f.fold == "replace":
        return text
    if f.fold == "append" and f.bound:
        return f"append({text}, {f.bound})"
    return f"{CALL.get(f.fold, f.fold)}({text})"


def literal_text(v) -> str | None:
    """A YAML constant as an expression's text (None: a list or a map, which no expression writes)."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return repr(v)
    return None
