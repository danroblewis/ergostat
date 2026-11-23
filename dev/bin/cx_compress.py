"""The compress family (dev/bin/complexity.py, dev/records/cx-compress-tree.md): how much information the code holds,
as the output length of one fixed compressor (an upper bound on its Kolmogorov complexity).

`packed(data, window)` is raw LZMA2 (no container) with every parameter written out: preset 6's as liblzma gives them,
but a 32 MiB window (`FAR`), so the readings do not jump the day the code passes preset 6's 8 MiB. An input longer than
`FAR` raises (the family is `failed`, never a degraded number); raising `FAR` is a `VERSION` bump. `NEAR` is the same
filter with a 64 KiB window: what the far window finds and the near one does not is the code said again far away.

Per file (cached by blob, Python only): `lzma` (packed bytes of the file alone), `logic` (the text with docstrings
and comments removed, `ast.unparse`d; a file that does not parse keeps its raw text and counts in `unparsed`), `prose`
(its comments and docstrings), `tokens` (as cx_size counts them; absent when it does not tokenize). Per commit, the
Python of the code scope as one stream per kind, files in path order (`stream`).

ENV is the Python minor version (`ast.unparse`'s formatting is its own) and the liblzma version, plus a fingerprint
of the filter's output on a fixed probe, so a library whose version cannot be read still changes ENV when its output
changes.

Cost at 34ece0da (about 5 MB of Python; one core, the factory's Linux container; test_cost_at_todays_size): a commit
whose parent is measured (the blob cache warm, as a backfill goes) 8.3 CPU s (8.4 s wall); with a cold cache (once
per VERSION or ENV) 28.7 CPU s; peak RSS 160 MB. The whole-stream compressions (raw twice, logic, prose) are most of
the warm time. Fitting the window to a smaller input (`packed`) gives the same bytes and took the cold time from
73.7 s; reading the raw texts in one git child (`snap.texts`) took the warm one from 11.7-13.1 s wall."""

from __future__ import annotations

import ast
import functools
import hashlib
import importlib.util
import io
import lzma
import sys
import tokenize
from pathlib import Path

VERSION = 1
FAR, NEAR = 32 << 20, 64 << 10
FILTER = {"id": lzma.FILTER_LZMA2, "lc": 3, "lp": 0, "pb": 2, "mode": lzma.MODE_NORMAL, "mf": lzma.MF_BT4,
          "nice_len": 64, "depth": 48}                # (preset 6; depth 48 is what its 0, automatic, gives bt4 at 64)
CODE = ("product", "factory", "scripts")
PY = {"area": CODE, "lang": "python"}
SCOPE = "the Python of ergostat/, dev/bin/ and scripts/ (vendored files left out), files in path order"
_SIZE = importlib.util.spec_from_file_location("cx_size_for_compress", Path(__file__).with_name("cx_size.py"))
size = importlib.util.module_from_spec(_SIZE)
_SIZE.loader.exec_module(size)


def _s(unit: str, part: bool, description: str) -> dict:
    return {"unit": unit, "part": part, "description": description}


SERIES = {
    "complexity-lzma-logic": _s("bytes", True, f"packed bytes of {SCOPE}, docstrings and comments removed"),
    "complexity-lzma-prose": _s("bytes", True, f"packed bytes of the comments and docstrings of {SCOPE}"),
    "complexity-repeat-share": _s("share", True, f"1 - packed(window 32 MiB) / packed(window 64 KiB) of {SCOPE}: "
                                  "how much is said again farther than 64 KiB away, whatever the file boundaries"),
    "complexity-lzma-code": _s("bytes", False, f"packed bytes of {SCOPE}, as written"),
    "complexity-lzma-ratio": _s("share", False, f"packed over raw bytes of {SCOPE}"),
    "complexity-lzma-per-token": _s("bytes", False, f"packed logic bytes per Python token of {SCOPE}"),
    "complexity-repeat-share-per-file": _s("share", False, f"1 - packed whole / sum of each file packed alone, of "
                                           f"{SCOPE}: rises when a module is split and falls when two are joined, with "
                                           "no repetition added or removed, because a small input compresses worse"),
    "complexity-lzma-window-used": _s("share", False, f"raw bytes of {SCOPE} over the 32 MiB window"),
    "complexity-unparsed-files": _s("files", False, f"files of {SCOPE} that do not parse, kept as raw text"),
}


def packed(data: bytes, window: int = FAR) -> int:
    if len(data) > FAR:
        raise ValueError(f"{len(data)} bytes is over the {FAR}-byte window: raise FAR (a VERSION bump)")
    fitted = min(window, 1 << max(12, (len(data) - 1).bit_length()))    # (no match reaches past the input: the
    return len(lzma.compress(data, format=lzma.FORMAT_RAW, filters=[FILTER | {"dict_size": fitted}]))  # same bytes)


@functools.cache
def liblzma() -> str:
    import ctypes
    import ctypes.util
    try:
        import _lzma
        where = [getattr(_lzma, "__file__", None), ctypes.util.find_library("lzma")]
    except ImportError:
        where = []
    for name in filter(None, where):
        try:
            f = ctypes.CDLL(name).lzma_version_string
        except (OSError, AttributeError):
            continue
        f.restype = ctypes.c_char_p
        return f().decode()
    return "unknown"


@functools.cache
def ENV() -> str:  # noqa: N802 (the contract's name)
    probe = "".join(f"{i * i % 1009} " for i in range(20000)).encode()
    out = lzma.compress(probe, format=lzma.FORMAT_RAW, filters=[FILTER | {"dict_size": NEAR}])
    return f"py{sys.version_info.major}.{sys.version_info.minor}-liblzma{liblzma()}-{hashlib.sha256(out).hexdigest()[:8]}"


def split(text: str) -> tuple[str, str, bool]:
    """(logic, prose, parsed): the text without docstrings and comments, unparsed; and those, in source order."""
    try:
        tree = ast.parse(text)
        said = [(t.start[0], t.string) for t in tokenize.generate_tokens(io.StringIO(text).readline)
                if t.type == tokenize.COMMENT]
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and body \
                    and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                said.append((body[0].lineno, body[0].value.value))
                node.body = body[1:] or [ast.Pass()]
        return ast.unparse(tree), "\n".join(s for _, s in sorted(said)), True
    except (SyntaxError, ValueError, RecursionError, tokenize.TokenError):
        return text, "", False


def per_file(path: str, text: str) -> dict:
    if not path.endswith(".py"):
        return {}
    logic, prose, parsed = split(text)
    m = {"lzma": packed(text.encode()), "logic": logic, "prose": prose, "unparsed": int(not parsed)}
    try:
        return m | {"tokens": size.tokens(text)}
    except (SyntaxError, tokenize.TokenError):
        return m


def rows(snap, where: dict) -> list[tuple[str, dict]]:
    """(path, measures) of the files matching `where`, vendored left out, in sorted path order. A blob first cached
    under a path that is not Python (one empty file is another) is measured here, not taken as having none."""
    def ok(row):
        return not row["vendored"] and all(row.get(k) in v if isinstance(v, tuple | list | set) else row.get(k) == v
                                           for k, v in where.items())
    return [(r["path"], r["m"] if "logic" in r["m"] else per_file(r["path"], snap.text(r["path"])))
            for r in sorted((r for r in snap.rows if ok(r)), key=lambda r: r["path"])]


def stream(snap, where: dict, kind: str) -> bytes:
    """The files' `raw`, `logic` or `prose` text as one stream, in sorted path order."""
    got = rows(snap, where)
    raw = snap.texts([p for p, _ in got]) if kind == "raw" else {}
    return "\n".join(raw[p] if kind == "raw" else m[kind] for p, m in got).encode()


def per_commit(snap) -> dict:
    py = [m for _, m in rows(snap, PY)]
    raw, logic = stream(snap, PY, "raw"), stream(snap, PY, "logic")
    code, near, lg = packed(raw), packed(raw, NEAR), packed(logic)
    out = {"complexity-lzma-logic": lg, "complexity-lzma-prose": packed(stream(snap, PY, "prose")),
           "complexity-repeat-share": 1 - code / near, "complexity-lzma-code": code,
           "complexity-lzma-window-used": len(raw) / FAR, "complexity-unparsed-files": sum(m["unparsed"] for m in py),
           "detail": {"python": f"{sys.version_info.major}.{sys.version_info.minor}", "liblzma": liblzma()}}
    if py and raw:
        out |= {"complexity-lzma-ratio": code / len(raw),
                "complexity-repeat-share-per-file": 1 - code / sum(m["lzma"] for m in py)}
    if py and all("tokens" in m for m in py) and sum(m["tokens"] for m in py):
        out["complexity-lzma-per-token"] = lg / sum(m["tokens"] for m in py)
    return out
