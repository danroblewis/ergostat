"""The ``libraries:`` map (name: ``git:`` URL, ``version:`` branch/tag/commit, optional ``path:`` inside and ``trust:
owner``), each value matched in full against an allowlist before anything runs with it (SPEC §2a): ``git:`` is an
https host and path or ``file:///``, with no userinfo, query, fragment or ``.``/``..`` step; a version or path cannot
begin with ``-`` or ``.``. Load checks them, and ``fetch`` again before any git process starts."""

from __future__ import annotations

import re

MAX = 16
KEYS = ("git", "version", "path", "trust")
OPTIONAL = ("path", "trust")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
_GIT = re.compile(r"(?:https://[A-Za-z0-9][A-Za-z0-9.-]{0,252}(?::[0-9]{1,5})?|file://)"
                  r"(?:/(?!\.\.?(?:/|\Z))[A-Za-z0-9._~-]{1,128}){1,32}/?")
_VERSION = re.compile(r"(?!.*\.\.)(?!.*//)(?!.*/[.-])(?!.*\.lock(?:/|\Z))[A-Za-z0-9][A-Za-z0-9._/-]{0,127}(?<![./])")
_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,99}(?:/[A-Za-z0-9_][A-Za-z0-9._-]{0,99}){0,15}")
_PATTERNS = {"git": _GIT, "version": _VERSION, "path": _PATH, "trust": re.compile("owner")}


class SourceError(ValueError):
    """A ``libraries:`` map refused: ``code`` is too-many-libraries or bad-library-source; ``field`` names where."""

    def __init__(self, code: str, field: str):
        super().__init__(f"{code} at {field}")
        self.code, self.field = code, field


def check(libraries) -> dict[str, dict[str, str]]:
    """The map checked (at most ``MAX`` entries); a missing or unknown key, or a value off its pattern, is refused."""
    if not isinstance(libraries, dict):
        raise SourceError("bad-library-source", "libraries")
    if len(libraries) > MAX:
        raise SourceError("too-many-libraries", "libraries")
    out = {}
    for name, entry in libraries.items():
        if not (isinstance(name, str) and _NAME.fullmatch(name)):
            raise SourceError("bad-library-source", f"libraries: the name {name!r}")
        if not isinstance(entry, dict) or set(entry) - set(KEYS):
            raise SourceError("bad-library-source", f"libraries.{name}: an entry of git, version, path and trust only")
        for key in KEYS:
            v = entry.get(key)
            if not (key in OPTIONAL and v is None or isinstance(v, str) and _PATTERNS[key].fullmatch(v)):
                raise SourceError("bad-library-source", f"libraries.{name}.{key}")
        out[name] = {k: entry[k] for k in KEYS if entry.get(k) is not None}
    return out
