"""What an agent is, for its answer (``/api/agents/NAME``): its block as written (where, its YAML, its keys), the law the
Blocks drawing computes for it, the machine that fills it (its ``agents:`` entry), what it decided as a controller,
why its rung is what it is, and the files it runs (its prompt, its program), each named relative to the model folder.

The files' text is a route of its own (``/api/agents/NAME/files``): only a file under the model folder, the project
folder or a template folder (the owner's or ergostat's own library) is read, never one under the state directory
(its tokens), at most ``FILE_LIMIT`` each and ``MOST_FILES`` in all. A path outside is listed, not shown, never read.
ergostat's own modules (``-m ergostat.MODULE``) are named with their docstring under ``own``, never by the
interpreter's path."""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import os
import re
import shlex
import sys
import textwrap
from functools import lru_cache
from pathlib import Path

import ergostat

PKG = Path(ergostat.__file__).parent.resolve()
LIBRARY = PKG / "library" / "templates"            # ergostat's own templates: their prompts are shown
MOST_FILES = 8
OUTSIDE = "not shown: outside the project"
FORMATS = {".md": "markdown", ".py": "python", ".sh": "shell", ".bash": "shell", ".yaml": "yaml", ".yml": "yaml",
           ".json": "json", ".js": "javascript", ".toml": "toml", ".txt": "text"}
INTERPRETERS = {"sh", "bash", "zsh", "env", "node", "deno", "bun", "ruby", "perl", "uv", "uvx", "exec"}
OWN = "ergostat's own: "
_kept: list = [None, None, None]                    # the spec and the moment the diagram below was built for


def _interpreter(tok: str) -> bool:
    base = os.path.basename(tok)
    return tok == sys.executable or base in INTERPRETERS or re.fullmatch(r"(python|pypy)[0-9.]*", base) is not None


def _roots(project, spec) -> list[tuple[str, Path]]:
    """Where a file may be read from, each with the prefix its name is given: the model folder and the project's
    first, then the owner's template folders, then ergostat's own library."""
    m = project.model
    out = [("", Path(spec.root).resolve())]
    if getattr(m, "path", None):
        out.append(("", Path(m.path).parent.resolve()))
    out += [(f"template {Path(t).parent.name}: ", Path(t).parent.resolve()) for t in spec.template_files]
    return [*out, (OWN + "library/templates/", LIBRARY)]


def _name(f: Path, roots) -> str | None:
    for prefix, r in roots:
        if f == r or r in f.parents:
            return prefix + str(f.relative_to(r)) if f != r else prefix + "."
    return None


def _under_state(project, f: Path) -> bool:
    state = Path(project.dir).resolve()
    return f == state or state in f.parents


def _listed(project, spec, b) -> tuple[list[dict], dict | None]:
    """Its files (prompt, then each run token that is a file, interpreters skipped), each with its resolved path under
    ``_path`` (None: not to be read), and its own module when it runs one of ergostat's."""
    roots, root = _roots(project, spec), Path(spec.root)
    out: list[dict] = []
    seen: set[Path] = set()

    def add(tok: str, role: str, said: bool) -> None:
        f = (root / tok).resolve()
        name = _name(f, roots)
        if name is None or _under_state(project, f):
            if said:                       # a path written outside: said, never stat'ed or read
                out.append({"name": Path(tok).name if os.path.isabs(tok) else tok, "role": role, "format": None,
                            "why": OUTSIDE, "_path": None})
            return
        if f in seen or not f.is_file():
            return
        seen.add(f)
        out.append({"name": name, "role": role, "format": FORMATS.get(f.suffix.lower(), "text"), "_path": f})

    prompt = b.params.get("prompt") if b.type == "ai" else None
    if isinstance(prompt, str) and "\n" not in prompt and prompt.strip():
        add(prompt, "prompt", True)     # as the engine resolves it (spec/engine.py, program); outside: not inline
    dn = b.params.get("daemon")
    run = b.params.get("run") or (spec.daemons[dn].run if dn in spec.daemons else "")
    try:
        toks = shlex.split(str(run or ""))
    except ValueError:
        toks = str(run or "").split()
    own = None
    for i, t in enumerate(toks):
        if i and toks[i - 1] == "-m":
            if t == "ergostat" or t.startswith("ergostat."):
                own = {"module": t, "doc": _doc(t)}
            continue
        if t.startswith("-") or _interpreter(t) or (i == 0 and "=" in t) or t in ("|", "&&", "||", ";", ">", "<"):
            continue
        if "/" in t or Path(t).suffix.lower() in FORMATS:
            add(t, "wrapper" if b.type == "ai" else "program", "/" in t)
    return out[:MOST_FILES], own


@lru_cache(maxsize=64)
def _doc(module: str) -> str:
    """An ergostat module's docstring, its first paragraph, read from its source (not imported)."""
    try:
        sp = importlib.util.find_spec(module)
        src = Path(sp.origin).read_text(encoding="utf-8") if sp and sp.origin else ""
        doc = ast.get_docstring(ast.parse(src)) or ""
    except (ImportError, OSError, SyntaxError, ValueError):
        return ""
    return doc.split("\n\n")[0].replace("\n", " ")


def _source(b) -> tuple[str | None, dict]:
    """The block's YAML as written, from its line on, and its keys parsed from it ({} when the text written is not
    the block's own: a template's instance, whose ``use:`` entry is shown)."""
    w = b.where
    if b.implied or w is None:
        return None, {}
    try:
        lines = Path(w.file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, {}
    i = w.line - 1
    if not 0 <= i < len(lines):
        return None, {}
    ind = lambda s: len(s) - len(s.lstrip())            # noqa: E731
    named = re.compile(rf"\s*['\"]?{re.escape(b.name)}['\"]?\s*:")
    own = named.match(lines[i]) is not None              # flow style, on the name's line
    if not own and i and ind(lines[i - 1]) < ind(lines[i]) and re.match(r"\s*[^#\s][^:]*:\s*(#.*)?$", lines[i - 1]):
        own = named.match(lines[i - 1]) is not None
        i -= 1                                          # the name's line (or the template instance's)
    j = i + 1
    while j < len(lines) and j - i < 400 and (not lines[j].strip() or ind(lines[j]) > ind(lines[i])):
        j += 1
    text = textwrap.dedent("\n".join(lines[i:j]).rstrip("\n"))
    if not own:
        return text, {}
    import yaml

    from ..spec.load import _loader
    try:
        got = yaml.load(text, Loader=_loader(Path(w.file), []))
        written = got.get(b.name) if isinstance(got, dict) else None
    except yaml.YAMLError:
        written = None
    return text, {k: v for k, v in written.items() if k != "type"} if isinstance(written, dict) else {}


def _law(spec, snap: dict, name: str) -> dict:
    """What the Blocks drawing says the block computes: its diagram built once per snapshot."""
    from ..blockdiagram import _Diagram
    if _kept[0] is not spec or _kept[1] != snap.get("at"):
        _kept[:] = [spec, snap.get("at"), _Diagram(spec, snap)]
    try:
        f = _kept[2].block_fn(name)
    except Exception as e:                              # said, not left out as if it had none
        return {"error": f"{type(e).__name__}: {e}"}
    return {k: f.get(k) for k in ("says", "math", "rows")}


def _where(w, roots) -> dict | None:
    if w is None:
        return None
    return {"file": _name(Path(w.file).resolve(), roots) or Path(w.file).name, "line": w.line}


def _rung_why(spec, b) -> str:
    a = spec.agents.get(b.agent) if b.agent else None
    if a is not None and a.kind:
        return f"its agent {a.name} is declared {a.kind} (agents: {a.name})"
    if b.builtin:
        return f"a built-in {b.type} block, computed by ergostat: a {b.builtin_rung}"
    from ..spec.legacy import KIND
    return f"a {b.type} block with no agent of a declared kind: its type's rung, {KIND[b.type]}"


def _decisions(project, m, snap: dict, name: str) -> dict | None:
    from .. import state as st
    ctl = [c.name for c in m.controllers.values() if c.agent == name]
    if not ctl:
        return None
    count, kinds = 0, {}
    for c in ctl:
        d = st.decisions(project, c, snap["at"] - snap["window"], snap["at"])
        count += d["count"]
        for k, n in d["kinds"]:
            kinds[k] = kinds.get(k, 0) + n
    hint = next((h for h in snap.get("hints", []) if h.get("about") == "ladder" and h.get("agent") == name), None)
    return {"count": count, "kinds": sorted(kinds.items(), key=lambda kv: -kv[1]), "controllers": ctl, "hint": hint}


def _plain(x, subs: list[tuple[str, str]]):
    """Every string with the interpreter's, ergostat's and the model folder's absolute paths taken out."""
    if isinstance(x, str):
        for a, b in subs:
            x = x.replace(a, b)
        return x
    if isinstance(x, dict):
        return {k: _plain(v, subs) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v, subs) for v in x]
    return x


def _compiled(b) -> dict:
    """The keys the compiled block carries, for a block whose own text is not written (implied, or a template's)."""
    out = dict(b.params)
    for k in ("takes", "on"):
        if getattr(b, k) is not None:
            out[k] = dataclasses.asdict(getattr(b, k))
    if b.takes is not None:
        out["pool"] = b.pool
    return out


def spec(project, snap: dict, name: str) -> dict | None:
    """The ``spec`` of ``/api/agents/NAME``; None when no block is named so."""
    m = project.model
    s = getattr(m, "spec", None)
    b = s.blocks.get(name) if s is not None else None
    if b is None:
        return None
    roots = _roots(project, s)
    source, written = _source(b)
    files, own = _listed(project, s, b)
    prompt = b.params.get("prompt")
    a = s.agents.get(b.agent) if b.agent else None
    out = {"type": b.type, "implied": b.implied,
           "implied_by": next((r.name for r in b.outputs.get("out", []) if r.kind == "block"), None) if b.implied else None,
           "where": _where(b.where, roots), "source": source, "params": written or _compiled(b),
           "prompt_text": prompt if isinstance(prompt, str) and not any(f["role"] == "prompt" for f in files) else None,
           "law": _law(s, snap, name),
           "machine": {**{k: v for k, v in a.__dict__.items() if k != "where"}, "where": _where(a.where, roots)} if a else None,
           "decisions": _decisions(project, m, snap, name), "rung_why": _rung_why(s, b), "own": own,
           "files": [{k: v for k, v in f.items() if k != "_path"} for f in files]}
    py = shlex.quote(sys.executable)
    subs = [(py, "python"), (sys.executable, "python"), (str(PKG), "ergostat")]
    for r in dict.fromkeys([str(Path(s.root)), str(Path(s.root).resolve())]):
        subs += [(r + "/", ""), (r, ".")]
    return _plain(out, subs)


def files(project, name: str) -> dict | None:
    """``/api/agents/NAME/files``: each of its files with its text (``why`` instead, when it is not shown)."""
    from .server import FILE_LIMIT
    s = getattr(project.model, "spec", None)
    b = s.blocks.get(name) if s is not None else None
    if b is None:
        return None
    roots = _roots(project, s)
    out = []
    for f in _listed(project, s, b)[0]:
        p, row = f.pop("_path"), f
        if p is not None:                               # checked again where it is now, as it is read
            p = p.resolve()
            if _name(p, roots) is None or _under_state(project, p) or not p.is_file():
                row = {**row, "why": OUTSIDE}
            elif p.stat().st_size > FILE_LIMIT:
                row = {**row, "why": "not shown: too big"}
            else:
                row = {**row, "text": p.read_text(encoding="utf-8", errors="replace")}
        out.append(row)
    return {"name": name, "files": out}
