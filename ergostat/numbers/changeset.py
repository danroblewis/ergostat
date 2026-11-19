"""A change set (SPEC §12e, *Redesign*): one proposal holding many coordinated edits to the model, made in order on a
scratch copy of its files in memory (never on disk), as a modeller editing the whole model would make them: parts
added, removed and renamed (every reference with it), flows rewired, equations, descriptions, systems.

Each edit is one of the forms a propose line takes (``{"part", "set"}``, ``{"add", "name", "set"}``, ``{"file",
"replace", "with"}``), or:

- ``{"remove": "stock.x"}``: the part's entry and everything under it taken away;
- ``{"rename": "stock.x", "to": "y"}``: the part renamed, every reference to it with it (``stock.x``, ``+stock.x``, a
  flow's ``from:``/``to:``, a goal's ``stock:``, a block's ``goal:``, a parameter in an equation), and a stock, flow or
  auxiliary says ``formerly:`` its old name, so its history follows it;
- ``{"file": "ergostat.yaml", "write": "..."}``: a model file written whole.

Each may carry ``why``. The edits are made one after another, each on the text the ones before it left, so a later one
may name what an earlier one made; the model need not compile between them, only at the end. What the change set does
is then one diff from the files as they are (``edits``): applied atomically, to the scratch copy for judging and to the
files on acceptance, as every change is."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from ..spec.ir import Spec
from ..spec.load import texts as override
from . import improve as im
from . import trial as tr
from . import yamledit as ye

OPS = ("set", "add", "replace", "remove", "rename", "write")
SECTION_OF = {"stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries", "parameter": "parameters",
              "goal": "goals", "block": "blocks", "items": "items", "agent": "agents"}
NAME = re.compile(r"^[a-z][a-z0-9-]*$")


class ChangeSetError(Exception):
    pass


def op_of(e: dict) -> str:
    if not isinstance(e, dict):
        return "?"
    if "remove" in e:
        return "remove"
    if "rename" in e:
        return "rename"
    if "write" in e:
        return "write"
    if "replace" in e:
        return "replace"
    if "add" in e:
        return "add"
    if "set" in e:
        return "set"
    return "?"


def said(e: dict) -> str:
    """An edit in a few words, as the review page lists it."""
    op = op_of(e)
    if op == "remove":
        return f"remove {e['remove']}"
    if op == "rename":
        return f"rename {e['rename']} to {e.get('to')}"
    if op == "write":
        return f"write {e.get('file')} whole"
    if op == "replace":
        first = next((x.strip() for x in str(e.get("replace") or "").split("\n") if x.strip()), "")
        return f"replace in {e.get('file')}: {first[:60]}"
    if op == "add":
        return f"add {SECTION_OF_INV.get(str(e.get('add')), e.get('add'))} {e.get('name')}"
    if op == "set":
        keys = ", ".join(sorted((e.get("set") or {}).keys()))
        return f"set {keys} on {e.get('part')}" + (f" (sensor {e['sensor']})" if e.get("sensor") else "")
    return "an edit ergostat cannot read"


SECTION_OF_INV = {v: k for k, v in SECTION_OF.items()}


class Scratch:
    """The model's files, copied in memory and edited in order; compiled and checked on demand."""

    def __init__(self, p, spec: Spec | None = None):
        self.p = p
        self.base: Spec = spec or p.model.spec
        self.main = p.model.path
        self.files = [str(Path(f).resolve()) for f in self.base.files]
        self.original = {f: Path(f).read_text(encoding="utf-8") for f in self.files}
        self.texts = dict(self.original)
        self.done: list[dict] = []          # the edits made, each with what it was and why
        self._spec: tuple | None = None
        self._found: tuple | None = None

    # ---- the files as they are now
    def compiled(self) -> tuple[Spec | None, list]:
        """The scratch copy's spec and everything check finds in it (errors too); None when it does not compile."""
        if self._spec is None:
            try:
                spec, problems = tr.compiled(self.main, self.texts, findings=True)
            except Exception as e:                     # a file that is no longer YAML, a key that cannot be read
                spec, problems = None, [_Problem(f"{type(e).__name__}: {e}")]
            self._loose = spec                         # as far as it compiled: enough to find a part by its name
            if spec is not None and any(x.level == "error" for x in problems):
                self._spec = (None, problems)
            else:
                self._spec = (spec, problems)
        return self._spec

    def errors(self) -> list[str]:
        _, ps = self.compiled()
        return [str(x) for x in ps if x.level == "error"]

    def _now(self) -> Spec:
        """The scratch copy's spec, to find parts in: compiled without the findings (which run the extreme-conditions
        tests, seconds on a large model, and are wanted once a round, not once an edit), as far as it compiles (an error
        elsewhere, say a unit an edit still to come puts right, does not stop an edit to another part)."""
        if self._spec is not None:
            spec, ps = self._spec
            spec = spec or getattr(self, "_loose", None)
        else:
            if getattr(self, "_found", None) is None:
                try:
                    self._found = tr.compiled(self.main, self.texts, findings=False)
                except Exception as e:
                    self._found = (None, [_Problem(f"{type(e).__name__}: {e}")])
            spec, ps = self._found
        if spec is None:
            raise ChangeSetError("the model does not compile at this point (" + "; ".join(
                str(x) for x in ps if x.level == "error")[:300] + "): it cannot be read as YAML; only replace and write "
                "edits can be made until it can")
        return spec

    # ---- an edit
    def apply(self, e: dict) -> None:
        """One edit made on the scratch copy, or ``ChangeSetError`` with why (the copy is left as it was)."""
        op = op_of(e)
        if op not in OPS:
            raise ChangeSetError(f"an edit is one of: {{part, set}}, {{add, name, set}}, {{file, replace, with}}, {{remove}}, "
                                 f"{{rename, to}}, {{file, write}} (not {str(e)[:120]})")
        before = dict(self.texts)
        try:
            with override(self.texts):
                if op == "write":
                    self._write(e)
                elif op == "remove":
                    self._remove(e)
                elif op == "rename":
                    self._rename(e)
                else:
                    spec = self._now() if op in ("set", "add") else self._files_spec()
                    es_ = im.edits(spec, {k: v for k, v in e.items() if k != "why"})
                    self._take(es_)
        except (im.ProposeError, ye.EditError, ChangeSetError) as err:
            self.texts = before
            self._spec = self._found = None
            raise ChangeSetError(str(err)) from None
        self.done.append({"op": op, "said": said(e), "why": str(e.get("why") or "").strip()[:400],
                          "edit": {k: v for k, v in e.items() if k != "why"}})

    def _files_spec(self) -> Spec:
        """A spec that knows the model's files (for a replace, which finds lines, not parts)."""
        try:
            return self._now()
        except ChangeSetError:
            return self.base

    def _take(self, es_: list[ye.Edit]) -> None:
        got = ye.apply_together(es_, self.texts)
        for f, t in got.items():
            f = str(Path(f).resolve())
            if f not in self.texts:
                raise ChangeSetError(f"{Path(f).name}: not one of the model's files")
            self.texts[f] = t
        self._spec = self._found = None

    def _file(self, name: str) -> str:
        f = Path(name)
        f = str((f if f.is_absolute() else Path(self.base.root) / f).resolve())
        if f not in self.texts:
            raise ChangeSetError(f"{name}: not one of the model's files ({', '.join(self.rel(x) for x in self.files)})")
        return f

    def rel(self, f: str) -> str:
        try:
            return str(Path(f).relative_to(Path(self.base.root).resolve()))
        except ValueError:
            return Path(f).name

    def _write(self, e: dict) -> None:
        f = self._file(str(e.get("file") or self.rel(self.files[0])))
        text = str(e.get("write") or "")
        if not text.strip():
            raise ChangeSetError("write: the file's whole text")
        self.texts[f] = text if text.endswith("\n") else text + "\n"
        self._spec = self._found = None

    def _remove(self, e: dict) -> None:
        spec = self._now()
        ref = str(e.get("remove") or "")
        try:
            _, path, at = im._part(spec, ref)
        except im.ProposeError as err:
            raise ChangeSetError(str(err)) from None
        ls = ye.lines_of(path)
        rest = ls[at - 1].split("#")[0].split(":", 1)[1] if ":" in ls[at - 1] else ""
        if rest.strip():                               # written on one line: name: {...}, or name: value
            self._take([ye.Edit(str(path), [ye.Hunk(at, [ls[at - 1]], [])])])
            return
        self._take([ye.remove_entry(path, at)])

    def _rename(self, e: dict) -> None:
        spec = self._now()
        ref, new = str(e.get("rename") or ""), str(e.get("to") or "")
        kind, _, old = ref.partition(".")
        new = new.split(".", 1)[1] if new.startswith(kind + ".") else new
        if kind not in SECTION_OF or not NAME.match(new):
            raise ChangeSetError("rename: a part (stock.x, flow.y, auxiliary.z, parameter.p, goal.g, block.b) and to: its "
                                 "new name (lowercase letters, digits and -)")
        table = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries, "parameter": spec.parameters,
                 "goal": spec.goals, "block": spec.blocks, "items": spec.items, "agent": spec.agents}[kind]
        if old not in table:
            raise ChangeSetError(f"rename: {ref} is not a part of the model")
        if new in table:
            raise ChangeSetError(f"rename: {kind} {new} is there already")
        try:
            _, path, at = im._part(spec, ref)
        except im.ProposeError as err:
            raise ChangeSetError(str(err)) from None
        path = str(Path(path).resolve())
        ls = self.texts[path].split("\n")
        line = ls[at - 1]
        ls[at - 1] = re.sub(rf"^(\s*){re.escape(old)}(\s*:)", rf"\g<1>{new}\g<2>", line)
        if kind in ("stock", "flow", "auxiliary"):
            if re.search(r":\s*\{", ls[at - 1]):
                ls[at - 1] = re.sub(r"\{", "{formerly: [" + old + "], ", ls[at - 1], count=1)
            else:
                end, child = ye.children(ls, at)
                pad = " " * (child if child is not None else ye.indent(ls[at - 1]) + 2)
                k = ye.key_line(ls, at, "formerly")
                if k is None:
                    ls.insert(at, f"{pad}formerly: [{old}]")
                else:
                    was = ls[k - 1].split(":", 1)[1].strip().strip("[]")
                    names = [x.strip() for x in was.split(",") if x.strip()]
                    ls[k - 1] = f"{pad}formerly: [{', '.join([*names, old])}]"
        self.texts[path] = "\n".join(ls)
        word = rf"(?<![\w.-]){re.escape(old)}(?![\w-])"
        for f in self.files:
            t = self.texts[f]
            t = re.sub(rf"(?<![\w-]){kind}\.{re.escape(old)}(?![\w-])", f"{kind}.{new}", t)
            if kind == "stock":
                t = re.sub(rf"^(\s*(?:-\s+)?(?:from|to|stock|of)\s*:\s*){re.escape(old)}(\s*(?:#.*)?)$", rf"\g<1>{new}\g<2>", t,
                           flags=re.M)
                t = re.sub(rf"([{{,]\s*(?:from|to|stock)\s*:\s*){re.escape(old)}(?=\s*[,}}])", rf"\g<1>{new}", t)
            if kind == "goal":
                t = re.sub(rf"^(\s*goal\s*:\s*){re.escape(old)}(\s*(?:#.*)?)$", rf"\g<1>{new}\g<2>", t, flags=re.M)
            if kind == "parameter":
                t = "\n".join(re.sub(word, new, x) if re.match(r"^\s*(equation|value)\s*:", x) else x for x in t.split("\n"))
            if kind == "agent":
                t = re.sub(rf"^(\s*agent\s*:\s*){re.escape(old)}(\s*(?:#.*)?)$", rf"\g<1>{new}\g<2>", t, flags=re.M)
            self.texts[f] = t
        self._spec = self._found = None

    def keep_names(self) -> list[str]:
        """A part taken away and one added that reads exactly what it read (the same sensor) are the same part renamed
        (a file written whole names it anew): the new one says ``formerly:`` the old, so its history follows it, as a
        rename edit would have written. Returns what it joined, ``old → new``."""
        spec, _ = self.compiled()
        if spec is None:
            return []
        out = []
        for kind, attr in (("stock", "stocks"), ("flow", "flows"), ("auxiliary", "auxiliaries")):
            a, b = getattr(self.base, attr), getattr(spec, attr)
            gone = [n for n in a if n not in b]
            new = [n for n in b if n not in a and not (getattr(b[n], "formerly", None) or [])]
            sig_new: dict[str, list[str]] = {}
            for n in new:
                k = _signature(b[n])
                if k:
                    sig_new.setdefault(k, []).append(n)
            for o in gone:
                k = _signature(a[o])
                hit = sig_new.get(k) if k else None
                if not hit or len(hit) != 1 or sum(1 for g in gone if _signature(a[g]) == k) != 1:
                    continue
                n = hit[0]
                try:
                    with override(self.texts):
                        es_ = im.edits(spec, {"part": f"{kind}.{n}", "set": {"formerly": [o]}})
                        self._take(es_)
                    spec, _ = self.compiled()
                    if spec is None:
                        break
                    out.append(f"{kind}.{o} → {kind}.{n}")
                except (im.ProposeError, ye.EditError, ChangeSetError):
                    continue
        if out:
            self.done.append({"op": "rename", "said": "history kept: " + ", ".join(out), "edit": {"keep_names": out},
                              "why": "each reads what the part it replaces read: the same part under a new name (formerly:)"})
        return out

    # ---- what it does, from the files as they are
    def changed(self) -> bool:
        return any(self.texts[f] != self.original[f] for f in self.files)

    def edits(self) -> list[ye.Edit]:
        """The change set as one edit per file: the hunks that turn the files as they are into the scratch copy."""
        out = []
        for f in self.files:
            a, b = self.original[f].split("\n"), self.texts[f].split("\n")
            if a == b:
                continue
            hunks = [ye.Hunk(i1 + 1, a[i1:i2], b[j1:j2])
                     for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if tag != "equal"]
            out.append(ye.Edit(f, hunks))
        return out

    def unified(self) -> str:
        return "".join(ye.unified(self.original[f], self.texts[f], self.rel(f)) for f in self.files
                       if self.texts[f] != self.original[f])


def _signature(x) -> str | None:
    """What a part reads, as text: its sensors' sources (items and their state, a command, a query, a measure), not their
    names, schedules or words. None when it reads nothing."""
    import json

    from . import version as ver
    got = []
    for sn in sorted(getattr(x, "sensors", {}) or {}):
        d = ver._plain(x.sensors[sn])
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if k in ("items", "run", "query", "builtin", "changes", "parse", "averages")}
        got.append(d)
    return json.dumps(got, sort_keys=True, default=str) if got else None


class _Problem:
    level = "error"
    code = "unreadable"
    about = ""

    def __init__(self, message: str):
        self.message = message
        self.where = None

    def __str__(self) -> str:
        return self.message


def parts_changed(before: Spec, after: Spec) -> dict[str, list[str]]:
    """What a change set does to the parts: each added, removed, renamed (``old → new``, from ``formerly:``) or
    changed (its definition as compiled differs), as references."""
    from . import version as ver
    out = {"added": [], "removed": [], "renamed": [], "changed": []}
    tables = (("stock", "stocks"), ("flow", "flows"), ("auxiliary", "auxiliaries"), ("parameter", "parameters"),
              ("goal", "goals"), ("block", "blocks"), ("items", "items"))
    for kind, attr in tables:
        a, b = getattr(before, attr), getattr(after, attr)
        if kind == "block":
            a = {n: x for n, x in a.items() if not x.implied}
            b = {n: x for n, x in b.items() if not x.implied}
        if kind == "items":
            a = {n: x for n, x in a.items() if not n.startswith("ergostat.")}
            b = {n: x for n, x in b.items() if not n.startswith("ergostat.")}
        gone, new = set(a) - set(b), set(b) - set(a)
        renamed = {}
        for n in sorted(new):
            hit = [w for w in (getattr(b[n], "formerly", None) or []) if w in gone and isinstance(w, str)]
            if len(hit) == 1:
                renamed[hit[0]] = n
        out["renamed"] += [f"{kind}.{o} → {kind}.{n}" for o, n in sorted(renamed.items())]
        out["removed"] += [f"{kind}.{n}" for n in sorted(gone - set(renamed))]
        out["added"] += [f"{kind}.{n}" for n in sorted(new - set(renamed.values()))]
        for n in sorted(set(a) & set(b)):
            if _plain(a[n]) != _plain(b[n]):
                out["changed"].append(f"{kind}.{n}")
        for o, n in renamed.items():
            if _plain(a[o], o) != _plain(b[n], n):
                out["changed"].append(f"{kind}.{n}")
    _ = ver
    return out


def _plain(x, name: str | None = None) -> str:
    import json

    from . import version as ver
    d = ver._plain(x)
    if isinstance(d, dict):
        d = {k: v for k, v in d.items() if k not in ("where", "defined", "formerly", "inferred", "value_at", "name")}
        d["description"] = getattr(x, "description", None)
    return json.dumps(d, sort_keys=True, default=str)
