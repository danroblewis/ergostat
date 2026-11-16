"""The smallest edit to a YAML file, made on its text so every comment, blank line and key order
stays as it was: a value changed on its own line, a key put into a map, entries added to a section.
An edit is a list of hunks; each says the lines it expects to find, so a file changed since the edit
was proposed is never written over blindly."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


class EditError(Exception):
    pass


@dataclass
class Hunk:
    line: int                    # 1-based: where the old lines start (for an insertion, the line it goes before)
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)


@dataclass
class Edit:
    file: str
    hunks: list[Hunk]

    def as_dict(self) -> dict:
        return {"file": self.file, "hunks": [asdict(h) for h in self.hunks], "diff": self.diff()}

    @staticmethod
    def from_dict(d: dict) -> Edit:
        return Edit(d["file"], [Hunk(**h) for h in d["hunks"]])

    def diff(self) -> str:
        """As a reviewer reads it: each hunk's line, then what goes (−) and what comes (+)."""
        out = []
        for h in self.hunks:
            out.append(f"@@ {Path(self.file).name}:{h.line}")
            out += [f"- {x}" for x in h.old] + [f"+ {x}" for x in h.new]
        return "\n".join(out)


def number(v: float) -> str:
    """A value as YAML reads it back as the same float: four significant figures, never an exponent
    (YAML 1.1 readers take 1e-05 for a string)."""
    if v == 0:
        return "0"
    r = float(f"{v:.4g}")
    if r == int(r) and abs(r) < 1e15:
        return str(int(r))
    text = f"{r:.12f}".rstrip("0").rstrip(".")
    return text if float(text) == r else repr(r)


def duration(hours: float) -> str:
    """Hours written back as a duration, in the unit that reads best: 12.4s, 7.5m, 2.25h."""
    secs = hours * 3600.0
    for unit, size in (("d", 86400.0), ("h", 3600.0), ("m", 60.0), ("s", 1.0)):
        if secs >= size or unit == "s":
            return f"{number(secs / size)}{unit}"
    return f"{number(secs)}s"


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


SCALAR = r"(?P<v>\"[^\"]*\"|'[^']*'|[^\s,}#][^,}#]*?)"


def set_value(path: Path, line: int, key: str, value: str) -> Edit:
    """``key: <old>`` on that line becomes ``key: value``, whatever else the line holds (a comment
    after it, a map written on one line)."""
    ls = lines_of(path)
    if not 1 <= line <= len(ls):
        raise EditError(f"{path.name}:{line}: no such line")
    old = ls[line - 1]
    m = re.search(rf"(?<![\w-]){re.escape(key)}\s*:\s*{SCALAR}(?=\s*(?:[,}}]|#|$))", old)
    if m is None:
        raise EditError(f"{path.name}:{line}: {key}: is not on this line ({old.strip()})")
    new = old[:m.start("v")] + value + old[m.end("v"):]
    return Edit(str(path), [Hunk(line, [old], [new])])


def indent(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


def _blank(s: str) -> bool:
    t = s.strip()
    return not t or t.startswith("#")


def add_key(path: Path, name_line: int, key: str, value: str) -> Edit:
    """``key: value`` put into the map whose name is on ``name_line`` (``alerts-fired:``), as its last
    key, at its keys' indentation (two more than the name when it has none)."""
    ls = lines_of(path)
    head = ls[name_line - 1]
    if re.search(r":\s*\{", head):
        raise EditError(f"{path.name}:{name_line}: the map is written on one line ({{...}}); write it out a key a line first")
    base = indent(head)
    end, child = name_line, None
    for i in range(name_line, len(ls)):
        s = ls[i]
        if _blank(s):
            continue
        if indent(s) <= base:
            break
        child = indent(s) if child is None else child
        end = i + 1
    at = end + 1
    pad = " " * (child if child is not None else base + 2)
    return Edit(str(path), [Hunk(at, [], [f"{pad}{key}: {value}"])])


def add_entries(path: Path, section: str, entries: list[list[str]]) -> Edit:
    """Entries (each its lines, indented as children of the section) added at the end of a
    top-level section, or a new section at the end of the file."""
    ls = lines_of(path)
    start = next((i for i, s in enumerate(ls) if re.match(rf"^{re.escape(section)}\s*:\s*(#.*)?$", s)), None)
    if start is None:
        at = len(ls) if ls and ls[-1] == "" else len(ls) + 1      # before the newline the file ends with
        before = [""] if any(x.strip() for x in ls) else []
        return Edit(str(path), [Hunk(at, [], before + [f"{section}:"] + [x for e in entries for x in e])])
    end, child = start + 1, None
    for i in range(start + 1, len(ls)):
        s = ls[i]
        if _blank(s):
            continue
        if indent(s) == 0:
            break
        child = indent(s) if child is None else child
        end = i + 1
    shift = (child or 2) - 2
    body = [(" " * shift + x) if x.strip() else x for e in entries for x in e]
    return Edit(str(path), [Hunk(end + 1, [], body)])


def merge(edits: list[Edit]) -> Edit:
    files = {e.file for e in edits}
    if len(files) != 1:
        raise EditError("one file at a time")
    return Edit(edits[0].file, [h for e in edits for h in e.hunks])


def apply(edit: Edit) -> str:
    """The file's new text, every hunk checked against what is there now; the last hunks first, so
    each line number still means what it meant."""
    path = Path(edit.file)
    ls = lines_of(path)
    for h in sorted(edit.hunks, key=lambda h: h.line, reverse=True):
        i = h.line - 1
        if ls[i:i + len(h.old)] != h.old:
            raise EditError(f"{path.name}:{h.line} has changed since this was proposed; ask for proposals again")
        ls[i:i + len(h.old)] = h.new
    return "\n".join(ls)
