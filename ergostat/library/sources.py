"""A fetched library's source, checked (SPEC §2a): each ``libraries:`` entry's name, ``git:``, ``version:``, ``path:``
and ``trust:``, every rule an allowlist matched whole (``re.fullmatch``). Load checks them, and ``fetch`` again before
any git process starts."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

MAX = 16                                            # libraries: at most this many entries
KEYS = {"git", "version", "path", "trust"}
NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")
PORT = re.compile(r"[0-9]{1,5}")
PATH = re.compile(r"/[A-Za-z0-9._~/-]*")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
REF = re.compile(r"[A-Za-z0-9._/-]{1,200}")
SUB = re.compile(r"[A-Za-z0-9._/-]+")


class Bad(ValueError):
    """A ``libraries:`` entry refused; ``code`` the error's code."""

    def __init__(self, msg: str, code: str = "bad-library-source"):
        super().__init__(msg)
        self.code = code


def url(u) -> str:
    """``https://HOST[:PORT]/PATH`` or ``file:///PATH``, written exactly so: no userinfo, query or fragment."""
    p = urlsplit(u) if isinstance(u, str) else None
    if p is None or p.scheme not in ("https", "file") or not PATH.fullmatch(p.path) or \
            ".." in p.path.split("/") or u != f"{p.scheme}://{p.netloc}{p.path}":
        raise Bad("git: https://HOST[:PORT]/PATH or file:///PATH (letters, digits and ._~/- only; no user, query or "
                  "fragment)")
    host, _, port = p.netloc.partition(":")
    if p.scheme == "file" and p.netloc or p.scheme == "https" and (
            not HOST.fullmatch(host) or ":" in p.netloc and not PORT.fullmatch(port) or p.path == "/"):
        raise Bad(f"git: {u!r} is not https://HOST[:PORT]/PATH or file:///PATH")
    return u


def ref(v) -> str:
    """A 40 or 64 lowercase hex commit, or a ref name ([A-Za-z0-9._/-], at most 200, no .., //, @{, leading -, leading
    or trailing / or ., or .lock at the end)."""
    if isinstance(v, str) and SHA.fullmatch(v):
        return v
    if not isinstance(v, str) or not REF.fullmatch(v) or v.startswith("-") or any(x in v for x in ("..", "//", "@{")) \
            or v[0] in "/." or v[-1] in "/." or v.endswith(".lock"):
        raise Bad("version: a tag, a branch or a commit sha (letters, digits and ._/-, at most 200, not starting with - "
                  "and without .., // or @{)")
    return v


def sub(p) -> str:
    if p is None:
        return ""
    if not isinstance(p, str) or not SUB.fullmatch(p) or any(s in ("", "..") for s in p.split("/")):
        raise Bad("path: a relative folder of the repository (letters, digits and ._/-, no .. or empty part)")
    return p


def entry(name, e) -> dict:
    """One entry, checked: ``{git, version, path, trust}`` (path "" for the whole repository)."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise Bad(f"library {name!r}: name: lowercase letters, digits and -, starting with a letter, at most 64")
    if not isinstance(e, dict) or set(e) - KEYS or not {"git", "version"} <= set(e):
        raise Bad(f"library {name}: git: and version: (and path:, trust: owner), and no other key")
    if e.get("trust") not in (None, "owner"):
        raise Bad(f"library {name}: trust: only owner")
    try:
        return {"git": url(e["git"]), "version": ref(e["version"]), "path": sub(e.get("path")), "trust": e.get("trust")}
    except Bad as x:
        raise Bad(f"library {name}: {x}") from None


def check(libs) -> dict[str, dict]:
    """Every entry of ``libraries:``, in order; the first refusal raises ``Bad``."""
    if not isinstance(libs, dict):
        raise Bad("libraries: a map of NAME: {git:, version:}")
    if len(libs) > MAX:
        raise Bad(f"libraries: {len(libs)} entries, at most {MAX}", "too-many-libraries")
    return {n: entry(n, e) for n, e in libs.items()}
