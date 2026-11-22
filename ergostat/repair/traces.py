"""Tracebacks read from a run's output (SPEC §12r, *Triage*): Python's, Node's, Java's, Go's and Ruby's.
``last`` gives the one whose header line comes last, with its frames innermost first, each marked whether it is the project's own code."""

from __future__ import annotations

import os
import re
from pathlib import Path

WALK = 5000                                          # entries a Java walk of the model's folder reads at most
SKIP = ("site-packages", "node_modules", ".venv", "venv", "vendor")
RUNTIME = ("node:", "<frozen", "<string>", "<internal:")
LIBRARY = ("site-packages", "/lib/python", "<frozen", "<string>")     # Python's signature frame skips these (unchanged)

PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<function>.+)$')
NODE_HEAD = re.compile(r"^(?P<type>[A-Z][\w$]*)(?: \[(?P<code>[^\]]+)\])?: (?P<message>.*)$")
NODE_AT = re.compile(r"^    at (?:(?P<function>.+?) \((?P<loc>[^()]*)\)|(?P<bare>[^ ()]+))$")
LOC = re.compile(r"^(?P<file>.+):(?P<line>\d+):\d+$")
JAVA_HEAD = re.compile(r'^(?:Exception in thread "[^"]*" )?(?P<type>[A-Za-z_$][\w$]*(?:\.[\w$]+)+)(?:: (?P<message>.*))?$')
JAVA_CAUSE = re.compile(r"^Caused by: (?P<type>[A-Za-z_$][\w$.]*)(?:: (?P<message>.*))?$")
JAVA_AT = re.compile(r"^\tat (?:[\w.$@-]+/)*(?P<cls>[\w$.]+)\.(?P<function>[\w$<>]+)\((?P<src>[^)]*)\)$")
GO_HEAD = re.compile(r"^panic: (?P<message>.*)$")
GO_ROUTINE = re.compile(r"^goroutine \d+ \[running\]:$")
GO_AT = re.compile(r"^\t(?P<file>\S+\.go):(?P<line>\d+)(?: \+0x[0-9a-f]+)?$")
RB_AT = r"(?P<file>\S.*?):(?P<line>\d+):in [`'](?P<function>[^`']*)'"
RB_HEAD = re.compile(rf"^{RB_AT}: (?P<message>.*) \((?P<type>[A-Z][\w:]*)\)$")
RB_FROM = re.compile(rf"^\tfrom {RB_AT}$")
PY_END = re.compile(r"^(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:: .*)?$")       # a Python exception line: `pkg.Type: message`


def project(file: str | None, root: Path) -> bool:
    """A frame of the project's code: under the model's folder (a relative path taken against it), in none of the
    library folders below it, and not the runtime's."""
    if not file or file.startswith(RUNTIME):
        return False
    r = root.resolve()
    try:
        f = (r / file).resolve()
    except (OSError, ValueError):
        return False
    return f.is_relative_to(r) and not any(x in SKIP for x in f.relative_to(r).parts)


def _frame(file: str, line: int, function: str, root: Path) -> dict:
    """A frame of Node or Go: its file relative to the model's folder when under it (as Python's are)."""
    try:
        f = Path(file).resolve() if Path(file).is_absolute() else None
    except (OSError, ValueError):
        f = None
    if f is not None and f.is_relative_to(root.resolve()):
        file = str(f.relative_to(root.resolve()))
    return {"file": file, "line": line, "function": function, "project": project(file, root)}


def _python(lines: list[str], root: Path) -> tuple[int, dict] | None:
    """The last Python traceback, by the rules triage has always used (so its signatures do not change)."""
    starts = [i for i, s in enumerate(lines) if s.startswith("Traceback (most recent call last)")]
    if not starts:
        return None
    frames, kind, msg = [], None, ""
    for s in lines[starts[-1] + 1:]:
        if m := PY_FRAME.match(s):
            f = Path(m["file"]).resolve()
            f = str(f.relative_to(root.resolve())) if f.is_relative_to(root.resolve()) else m["file"]
            frames.insert(0, {"file": f, "line": int(m["line"]), "function": m["function"], "project": project(f, root)})
        elif s.strip() and not s[:1].isspace():
            kind, _, msg = s.strip().partition(": ")
            break
    if not kind or not frames:
        return None
    at = next((f for f in frames if not any(x in f["file"] for x in LIBRARY)), frames[0])
    return starts[-1], {"language": "python", "type": kind, "message": msg, **_where(at), "frames": frames}


def _where(f: dict) -> dict:
    return {"file": f["file"], "line": f["line"], "function": f["function"]}


def _signed(language: str, kind: str, message: str, frames: list[dict], **more) -> dict:
    at = next((f for f in frames if f["project"]), frames[0])
    return {"language": language, "type": kind, "message": message, **_where(at), "frames": frames, **more}


def _node(lines: list[str], root: Path) -> tuple[int, dict] | None:
    for i in range(len(lines) - 2, -1, -1):
        h = NODE_HEAD.match(lines[i])
        if not h or not NODE_AT.match(lines[i + 1]):
            continue
        frames = []
        for s in lines[i + 1:]:
            if not (m := NODE_AT.match(s)):
                break
            loc = LOC.match((m["loc"] if m["loc"] is not None else m["bare"]).removeprefix("file://"))
            if loc:                                  # (`at Array.forEach (<anonymous>)`: no place, no frame)
                frames.append(_frame(loc["file"], int(loc["line"]), m["function"] or "<anonymous>", root))
        if frames:
            return i, _signed("node", h["type"], h["message"], frames)
    return None


def _walk(root: Path) -> tuple[list[str], bool]:
    """The files under the model's folder (dot-folders and library folders not entered), and whether the cap was
    reached: every entry read counts, one at a time, so a folder of a million files stops at ``WALK``."""
    seen, out, todo = 0, [], [root]
    while todo:
        try:
            listing = os.scandir(todo.pop())
        except OSError:
            continue
        with listing:
            for x in listing:
                seen += 1
                if seen > WALK:
                    return [], True
                if x.is_dir(follow_symlinks=False):
                    if not x.name.startswith(".") and x.name not in SKIP:
                        todo.append(x.path)
                elif x.is_file(follow_symlinks=False):
                    out.append(os.path.relpath(x.path, root).replace(os.sep, "/"))
    return out, False


def _java(lines: list[str], root: Path) -> tuple[int, dict] | None:
    for i in range(len(lines) - 2, -1, -1):
        h = JAVA_HEAD.match(lines[i])
        if not h or not JAVA_AT.match(lines[i + 1]):
            continue
        chain = [{"type": h["type"], "message": h["message"] or "", "frames": []}]
        for s in lines[i + 1:]:
            if m := JAVA_AT.match(s):
                chain[-1]["frames"].append(m)
            elif c := JAVA_CAUSE.match(s):
                chain.append({"type": c["type"], "message": c["message"] or "", "frames": []})
            elif not (s.startswith(("\t...", "\t\t", "\tSuppressed:"))):    # (a Suppressed: block is not the cause)
                break
        files, capped = _walk(root.resolve())
        for x in chain:
            x["frames"] = [_java_frame(m, files, capped) for m in x["frames"]]
        root_cause = chain[-1]
        at = next((f for x in reversed(chain) for f in x["frames"] if f["project"]),
                  next(x["frames"][0] for x in reversed(chain) if x["frames"]))
        frames = [f for x in reversed(chain) for f in x["frames"]]
        return i, {"language": "java", "type": root_cause["type"], "message": root_cause["message"], **_where(at),
                   "frames": frames, **({"walk": "capped"} if capped else {})}
    return None


def _java_frame(m: re.Match, files: list[str], capped: bool) -> dict:
    cls, src = m["cls"], m["src"].split(":")
    pkg = cls.rpartition(".")[0].replace(".", "/")
    name = src[0] if src[0].endswith(".java") or "." in src[0] else cls.rpartition(".")[2].split("$")[0] + ".java"
    rel = f"{pkg}/{name}" if pkg else name
    ours = not capped and any(f == rel or f.endswith("/" + rel) for f in files)
    return {"file": rel, "line": int(src[1]) if len(src) > 1 and src[1].isdigit() else None,
            "function": f"{cls}.{m['function']}", "project": ours}


def _go(lines: list[str], root: Path) -> tuple[int, dict] | None:
    for i in range(len(lines) - 1, -1, -1):
        h = GO_HEAD.match(lines[i])
        if not h:
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].startswith(("[signal", "\tpanic:"))):
            j += 1
        if j >= len(lines) or not GO_ROUTINE.match(lines[j]):
            continue
        frames, j = [], j + 1
        while j + 1 < len(lines) and not lines[j].startswith("\t") and (m := GO_AT.match(lines[j + 1])):
            frames.append(_frame(m["file"], int(m["line"]), re.sub(r"\([^()]*\)$", "", lines[j].strip()), root))
            j += 2
        if frames:
            return i, _signed("go", "panic", h["message"], frames)
    return None


def _ruby(lines: list[str], root: Path) -> tuple[int, dict] | None:
    """``path:N:in 'meth': message (Type)`` directly followed by ``\\tfrom path:N:in ...`` lines, innermost first;
    a frame under ``vendor`` or ``gems`` is a library's."""
    for i in range(len(lines) - 1, -1, -1):
        if not (h := RB_HEAD.match(lines[i])):
            continue
        frames = []
        for m in [h, *map(RB_FROM.match, lines[i + 1:])]:
            if not m:
                break
            f = _frame(m["file"], int(m["line"]), m["function"], root)
            frames.append({**f, "project": f["project"] and "gems" not in Path(f["file"]).parts})
        return i, _signed("ruby", h["type"], h["message"], frames)
    return None


def python_to_end(text: str, root: Path) -> dict | None:
    """The last Python traceback in ``text`` when its exception line is the text's last line (it runs to the end)."""
    lines = [s for s in text.splitlines() if s.strip()]
    got = _python(lines, root)
    if got is None:
        return None
    rest = [j for j in range(got[0] + 1, len(lines)) if not lines[j][:1].isspace()]
    return got[1] if rest == [len(lines) - 1] else None


def ends_in_python_exception(text: str) -> bool:
    """No Python header in ``text``, and its last line reads as a Python exception line."""
    lines = [s for s in text.splitlines() if s.strip()]
    return bool(lines) and bool(PY_END.match(lines[-1])) and not any(
        s.startswith("Traceback (most recent call last)") for s in lines)


def last(text: str, root: Path) -> dict | None:
    """The trace whose header line comes last in ``text``, of any language read; None when no header is there."""
    lines = text.splitlines()
    got = [t for parse in (_python, _node, _java, _go, _ruby) if (t := parse(lines, root)) is not None]
    return max(got, key=lambda t: t[0])[1] if got else None
