"""The size family (dev/bin/complexity.py): per file `lines`, `net_lines` (as scripts/code_evidence.py counts them),
`bytes` (of its UTF-8 text) and, for Python, `tokens`: tokenize's, comments and layout left out, an f-string one
token however the tokenizer splits it. ENV is the Python minor version, since tokenizing changes with it."""

from __future__ import annotations

import io
import sys
import tokenize

VERSION = 1
CODE = ("product", "factory", "scripts")
SCOPE = "ergostat/, dev/bin/ and scripts/ (vendored files left out)"
SERIES = {
    "complexity-tokens": {"unit": "tokens", "part": True, "description": f"Python tokens of {SCOPE}"},
    "complexity-lines-code": {"unit": "lines", "part": False, "description": f"net lines of the Python of {SCOPE}"},
    "complexity-files-code": {"unit": "files", "part": False, "description": f"Python files of {SCOPE}"},
}
LAYOUT = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER,
          tokenize.ENCODING}
STARTS = {getattr(tokenize, n) for n in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, n)}
ENDS = {getattr(tokenize, n) for n in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, n)}


def ENV() -> str:  # noqa: N802 (the contract's name)
    return f"py{sys.version_info.major}.{sys.version_info.minor}"


def tokens(text: str) -> int:
    n = depth = 0
    for t in tokenize.generate_tokens(io.StringIO(text).readline):
        if t.type in STARTS:
            n, depth = n + (depth == 0), depth + 1
        elif t.type in ENDS:
            depth -= 1
        elif not depth and t.type not in LAYOUT:
            n += 1
    return n


def per_file(path: str, text: str) -> dict:
    m = {"lines": len(text.splitlines()), "bytes": len(text.encode()),
         "net_lines": sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))}
    return m | {"tokens": tokens(text)} if path.endswith(".py") else m


def per_commit(snap) -> dict:
    py = {"area": CODE, "lang": "python"}
    return {"complexity-tokens": snap.sum("tokens", **py), "complexity-lines-code": snap.sum("net_lines", **py),
            "complexity-files-code": sum(1 for r in snap.rows if not r["vendored"] and r["area"] in CODE
                                         and r["lang"] == "python")}
