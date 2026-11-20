"""The AI approver's guard (SPEC §12r), in code: what a fix adds that only a person may let through, from the program's
syntax before and after. A program that is not Python cannot be read so, and always goes to the person."""

from __future__ import annotations

import ast
import re
from collections import Counter

MOST = 40                                  # lines changed, at most
RISKY = {"subprocess", "socket", "eval", "exec", "compile", "__import__", "getattr", "setattr", "importlib", "shutil",
         "urllib", "requests", "http", "ctypes", "pickle", "os.system", "os.popen", "os.environ", "os.getenv", "os.exec",
         "os.spawn", "os.remove", "os.unlink", "os.rename", "os.putenv", "open", "write_text", "write_bytes", "unlink"}
LITERAL = re.compile(r"://|^[/~]|\.\./|\\\\")


def _signals(src: str) -> Counter:
    out: Counter = Counter()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out[f"an import ({ast.unparse(n)})"] += 1
        elif isinstance(n, (ast.Name, ast.Attribute)):
            d = ast.unparse(n)
            if d in RISKY or d.split(".")[0] in RISKY or d.rsplit(".", 1)[-1] in RISKY or \
                    any(d.startswith(r) for r in RISKY if r.startswith("os.")):
                out[f"a call or use of {d}"] += 1
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and LITERAL.search(n.value):
            out[f"a URL or path literal ({n.value[:40]!r})"] += 1
    return out


def escalate(path: str, old: str, new: str, diff: str) -> list[str]:
    """Why a person must decide, or nothing: every risky thing the fix adds, a diff too long, or a program not Python."""
    if not path.endswith(".py"):
        return [f"{path} is not Python: its changes cannot be checked in code"]
    changed = sum(1 for x in diff.splitlines() if x[:1] in "+-" and x[:3] not in ("+++", "---"))
    why = [f"the diff changes {changed} lines (over {MOST})"] if changed > MOST else []
    try:
        added = _signals(new) - _signals(old)
    except (SyntaxError, ValueError) as e:
        return [*why, f"the program cannot be parsed: {e}"]
    return why + [f"it adds {k}" for k in sorted(added)]
