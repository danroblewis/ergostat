"""What the MCP authoring tools do (``templates``, ``add_use``, ``scaffold``, ``try_use``, ``where_drawn``): an AI
agent turns a request in plain words into a template instance, tries it on a copy, and shows the owner where it
is drawn and what changed before it is written. Writing it is the owner's own change to the model, made by the
author on the owner's behalf: it is not a proposal, and nothing is changed until the owner says so."""

from __future__ import annotations

import difflib
import fnmatch
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from ..spec.load import FILE, texts
from . import templates as tp
from . import untrusted as ut

SKIP = (".git", "__pycache__", ".venv", "node_modules", "run", "outbox", "reports", ".ergostat-scratch")


class AuthorError(Exception):
    pass


def _doc(root: Path):
    from ..spec.load import load
    return load(root / FILE)


def library(root: Path | None, name: str | None = None) -> dict:
    """Every template (name, what it is, its parameters), or one in full (its reading in control theory and
    system dynamics, its example, its parameters)."""
    doc = _doc(root) if root is not None and (root / FILE).is_file() else None
    extra = doc.library if doc is not None else []
    got, notes = tp.find_all(extra, getattr(doc, "untrusted_library", set()))
    if name:
        t = got.get(name)
        if t is None:
            raise AuthorError(f"no template {name!r} (there are: {', '.join(sorted(got))})")
        return marked(t, {**t.summary(), "reading": t.reading, "example": t.example})
    out = {"templates": [marked(t, {"template": t.name, "description": t.description, "from": t.summary()["from"],
                                    "params": list(t.params)}) for t in got.values()],
           "folders": [str(f) for f in tp.folders(extra)], **({"notes": notes} if notes else {}),
           "next": "templates with name: NAME for its parameters and its reading; add_use to try one"}
    shown = any(t.untrusted for t in got.values()) or any(n.startswith("untrusted library folder") for n in notes)
    return {**out, "markers": ut.SAYS} if shown else out


TEXT = ("description", "reading", "example", "from")               # an untrusted template's text, marked (SPEC §2a)
PARAM_TEXT = ("description", "stand-in", "default", "choices")


def marked(t: tp.Template, entry: dict) -> dict:
    """An untrusted template's entry with its library text marked (a string; a list or map as JSON, then marked; a
    number or a bool as it is): never its name, its parameters' names or their types. A trusted one's, as it is."""
    if not t.untrusted:
        return entry
    label = ut.LABEL.format(t.name)                                 # (its name matched tp.SAFE when it was read)
    out = {k: ut.mark_all(v, label) if k in TEXT else v for k, v in entry.items()}
    if isinstance(out.get("params"), dict):
        out["params"] = {n: {k: ut.mark_all(v, label) if k in PARAM_TEXT else v for k, v in p.items()}
                         for n, p in out["params"].items()}
    return {**out, "untrusted": True, **({"markers": ut.SAYS} if "reading" in entry else {})}


# ---- writing an instance

def entry_text(instance: str, template: str, given: dict, within: str | None, description: str | None) -> list[str]:
    body: dict = {"use": template}
    if within:
        body["within"] = within
    if description:
        body["description"] = description
    if given:
        body["with"] = given
    text = yaml.safe_dump({instance: body}, sort_keys=False, default_flow_style=False, allow_unicode=True, width=110)
    return ["  " + x if x else x for x in text.rstrip("\n").split("\n")]


def _block_end(lines: list[str], start: int) -> int:
    """The index after the last line of the top-level section starting at ``start``."""
    end = start + 1
    last = start + 1
    while end < len(lines):
        x = lines[end]
        if x.strip() and not x.startswith((" ", "\t", "#")):
            break
        if x.strip() and not x.lstrip().startswith("#"):
            last = end + 1
        end += 1
    return last


def placed(text: str, instance: str, entry: list[str], replace: bool) -> str:
    lines = text.split("\n") if text else []
    at = next((i for i, x in enumerate(lines) if x.rstrip() == "uses:" or x.startswith("uses:")), None)
    if at is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + ["uses:"] + entry
        return "\n".join(lines) + "\n"
    end = _block_end(lines, at)
    mine = next((i for i in range(at + 1, end) if lines[i].rstrip() == f"  {instance}:"), None)
    if mine is not None:
        if not replace:
            raise AuthorError(f"uses: already has {instance} in this file; replace: true writes it again")
        stop = mine + 1
        while stop < end and (not lines[stop].strip() or lines[stop].startswith("    ")):
            stop += 1
        while stop > mine + 1 and not lines[stop - 1].strip():
            stop -= 1
        lines[mine:stop] = entry
    else:
        lines[end:end] = entry
    return "\n".join(lines).rstrip("\n") + "\n"


def _included(root: Path, path: Path) -> bool:
    """Read already, or matched by one of the main file's include: patterns (a new file in job/ for job/*.yaml)."""
    if path.is_file() and path.resolve() in {f.resolve() for f in _doc(root).files}:
        return True
    try:
        data = yaml.safe_load((root / FILE).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return False
    pats = data.get("include") if isinstance(data, dict) else None
    pats = [pats] if isinstance(pats, str) else pats or []
    rel = os.path.relpath(path, root)
    return any(isinstance(p, str) and fnmatch.fnmatch(rel, p) for p in pats)


def _include_line(main: Path, rel: str) -> str:
    text = main.read_text(encoding="utf-8")
    lines = text.split("\n")
    at = next((i for i, x in enumerate(lines) if x.startswith("include:")), None)
    if at is None:
        top = next((i + 1 for i, x in enumerate(lines) if x.startswith("name:")), 0)
        lines[top:top] = ["include:", f"  - {rel}"]
    elif lines[at].strip() == "include:":
        end = at + 1
        while end < len(lines) and lines[end].startswith((" ", "\t")):
            end += 1
        lines[end:end] = [f"  - {rel}"]
    else:
        was = lines[at].split(":", 1)[1].strip()
        items = [x.strip() for x in was.strip("[]").split(",") if x.strip()] if was else []
        lines[at:at + 1] = ["include:"] + [f"  - {x}" for x in items + [rel]]
    return "\n".join(lines)


def change(root: Path, instance: str, template: str, given: dict | None = None, file: str | None = None,
           within: str | None = None, description: str | None = None, replace: bool = False) -> dict[Path, str]:
    """The files as they would be: path → new text (the instance in ``file``, and the main file including it)."""
    root = root.resolve()
    main = root / FILE
    target = (root / (file or FILE)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise AuthorError(f"file: {file} is outside the model's folder; templates may live anywhere (library:), the model's files may not")
    old = target.read_text(encoding="utf-8") if target.is_file() else ""
    new = {target: placed(old, instance, entry_text(instance, template, given or {}, within, description), replace)}
    if target != main.resolve() and not _included(root, target):
        rel = os.path.relpath(target, root)
        new[main.resolve()] = _include_line(main, rel)
    return new


def diff(root: Path, new: dict[Path, str]) -> str:
    out = []
    for path, text in new.items():
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        rel = os.path.relpath(path, root)
        out += difflib.unified_diff(old.splitlines(), text.splitlines(), f"a/{rel}", f"b/{rel}", lineterm="")
    return "\n".join(out)


def checked(root: Path, new: dict[Path, str] | None = None) -> dict:
    from ..spec import read
    made = []
    for k in new or {}:                         # a file that is not there yet: there, empty, while it is read from the change
        if not Path(k).exists():
            Path(k).parent.mkdir(parents=True, exist_ok=True)
            Path(k).write_text("")
            made.append(Path(k))
    try:
        with texts({str(k): v for k, v in (new or {}).items()}):
            spec, problems = read(root / FILE)
    finally:
        for k in made:
            k.unlink(missing_ok=True)
    return {"ok": not any(p.level == "error" for p in problems),
            "errors": [{"message": p.message, "where": str(p.where) if p.where else None, "code": p.code}
                       for p in problems if p.level == "error"],
            "findings": [{"message": p.message, "where": str(p.where) if p.where else None, "code": p.code, "about": p.about}
                         for p in problems if p.level != "error"],
            "spec": spec}


def add(root: Path, instance: str, template: str, given: dict | None = None, file: str | None = None,
        within: str | None = None, description: str | None = None, replace: bool = False, write: bool = False) -> dict:
    """The instance, written into ``file`` (or only shown, without ``write``): the diff, and what check says."""
    root = root.resolve()
    new = change(root, instance, template, given, file, within, description, replace)
    got = checked(root, new)
    spec = got.pop("spec")
    mine = [f for f in got["findings"] if instance in (f.get("about") or "") or instance in (f.get("where") or "")]
    out = {"diff": diff(root, new), "ok": got["ok"], "errors": got["errors"], "findings_for_it": mine[:12],
           "other_findings": len(got["findings"]) - len(mine)}
    if got["ok"] and instance in spec.uses:
        out["parts"] = parts_of(spec, instance)
    if write:
        if not got["ok"]:
            out["written"] = False
            out["why_not"] = "check has errors: fix them first (nothing was written)"
            return out
        for path, text in new.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        out["written"] = [os.path.relpath(p, root) for p in new]
    else:
        out["written"] = False
        out["next"] = "try_use to run it on a copy; show the owner the diff and where_drawn; then add_use with write: true"
    return out


def parts_of(spec, system: str) -> dict:
    inside = lambda x: x.system and system in spec.chain(x.system)          # noqa: E731
    return {"system": system, "template": (spec.uses.get(system) or {}).get("template"),
            "items": [k for k, v in spec.items.items() if inside(v)],
            "stocks": [n for n, x in spec.stocks.items() if inside(x)], "flows": [n for n, x in spec.flows.items() if inside(x)],
            "auxiliaries": [n for n, x in spec.auxiliaries.items() if inside(x)],
            "goals": {n: f"{x.of} {x.hold}" for n, x in spec.goals.items() if inside(x)},
            "blocks": {n: x.type for n, x in spec.blocks.items() if inside(x)},
            "stand_ins": (spec.uses.get(system) or {}).get("standins") or []}


# ---- scripts

SCRIPTS = {
    "source": ('''"""A source for ergostat's collector: print the records it should see, as JSON, one object a line (or an array).
Each needs an id; anything else becomes the item's fields. $ERGOSTAT_CURSOR is the greatest cursor seen so far
(when the template was given cursor-field). Read only: never change the system you read."""
import json
import os
import sys

cursor = os.environ.get("ERGOSTAT_CURSOR") or None

# TODO: read the real source here (an API, a CLI, a file) instead of these stand-in records.
records = [
    {"id": "1", "title": "a stand-in record", "from": "someone"},
]
for r in records:
    print(json.dumps(r))
''', "command"),
    "answer": ('''"""Work on one item: ergostat gives it on standard input ({"id", "kind", "state", "fields"}) and in $ITEM_ID and
$ITEM_FIELDS. Exit 0 when it is done (the item moves on); any other exit says it failed (it is tried again, then
set aside). The last JSON object printed is folded into the item's fields."""
import json
import sys

item = json.load(sys.stdin)
fields = item.get("fields") or {}

# TODO: do the work here (draft a reply, call an API, write a file). Keep anything it writes outside under the
# owner's approval: write a draft into a folder rather than sending it.
result = f"done: {fields.get('title') or item['id']}"

print(json.dumps({"result": result}))
''', "answer"),
    "measure": ('''"""A sensor: print one number, the level now (a bare number, or {"value": n}). Measure only: never act."""
import shutil

# TODO: measure the real thing. This stand-in prints the disk's used share, in percent.
total, used, free = shutil.disk_usage("/")
print(round(used * 100 / total, 2))
''', "measure"),
    "act": ('''"""A corrective action, run while the goal is off: do one step of the correction and print what it moved, as
{"moved": n} in the level's unit. ergostat gives the block's input on standard input (its goal, the error)."""
import json
import sys

given = json.load(sys.stdin) if not sys.stdin.isatty() else {}

# TODO: correct the real thing (clean, scale, archive) and measure how much it moved.
moved = 0

print(json.dumps({"moved": moved}))
''', "act"),
    "render": ('''"""A report: print it as Markdown. ergostat keeps what it prints as the report's file, and records the item."""
import datetime

# TODO: gather what the report says (from your systems, or `$ERGOSTAT_CMD item --kind K --json`).
print(f"# Report, {datetime.date.today():%A %d %B %Y}")
print()
print("- nothing to report yet")
''', "render"),
    "ping": ('''"""A reminder about one unanswered item, sent by re-ping: the item on standard input, the ping's number in
$PING_N. Exit 0 when sent. Keep it within what the owner allowed: write the reminder into a folder for the owner to
send, unless sending it was approved."""
import json
import os
import sys
from pathlib import Path

item = json.load(sys.stdin)
n = os.environ.get("PING_N", "1")

# TODO: send the reminder (or leave it as a draft, as here).
out = Path("outbox")
out.mkdir(exist_ok=True)
(out / f"ping-{item['id'].replace('/', '-')}-{n}.md").write_text(f"Reminder {n} about {item['id']}\\n")
print(json.dumps({"reminded": n}))
''', "ping"),
}
SCRIPTS["step"] = SCRIPTS["answer"]


def scaffold(root: Path, role: str, path: str, overwrite: bool = False) -> dict:
    """A script for one of a template's commands, written where the owner keeps scripts (inside the project, or a
    private folder outside any repository), runnable as it is (a stand-in), with its TODO."""
    if role not in SCRIPTS:
        raise AuthorError(f"role: one of {', '.join(sorted(SCRIPTS))}")
    p = Path(path).expanduser()
    p = p if p.is_absolute() else root / p
    if p.exists() and not overwrite:
        raise AuthorError(f"{p} is there already; overwrite: true replaces it")
    p.parent.mkdir(parents=True, exist_ok=True)
    text, param = SCRIPTS[role]
    p.write_text("#!/usr/bin/env python3\n" + text, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    inside = p.resolve().is_relative_to(root.resolve())
    where = os.path.relpath(p, root) if inside else str(p)
    cmd = f"python3 {where}" if p.suffix == ".py" else (f"./{where}" if inside else where)   # (else its shebang runs it)
    return {"written": str(p), "command": cmd, "with": {param: cmd},
            "note": "a Python script, runnable as it is (a stand-in); fill in its TODO, then run it by hand once: " + cmd}


# ---- trying it

def scratch_copy(root: Path) -> Path:
    base = Path(tempfile.mkdtemp(prefix="ergostat-try-"))
    dst = base / root.name
    shutil.copytree(root, dst, ignore=shutil.ignore_patterns(*SKIP), symlinks=True)
    return dst


def trial(root: Path, system: str | None = None, seconds: float = 30.0, change_args: dict | None = None,
          blocks: bool = True, standins: bool = False) -> dict:
    """A copy of the project (with the change, when given), checked, then run for ``seconds`` with a record of its
    own: what moved in the system, what each block did, what failed and why."""
    root = root.resolve()
    copy = scratch_copy(root)
    if change_args:
        new = change(copy, **change_args)
        for path, text in new.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        system = system or change_args["instance"]
    if not system:
        raise AuthorError("say which system to watch (an instance's name)")
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "home")}
    if standins:
        env["ERGOSTAT_STANDINS"] = "1"
    from ..spec import read
    old = os.environ.get("ERGOSTAT_STANDINS")
    try:
        if standins:
            os.environ["ERGOSTAT_STANDINS"] = "1"
        spec, problems = read(copy / FILE, extremes=False)   # its errors only: no extremes run, nothing kept
    finally:
        if standins and old is None:
            os.environ.pop("ERGOSTAT_STANDINS", None)
    errors = [{"message": p.message, "where": str(p.where) if p.where else None} for p in problems if p.level == "error"]
    out: dict = {"scratch": str(copy), "check": {"ok": not errors, "errors": errors[:20]}}
    if errors:
        out["ran"] = False
        return out
    if system not in spec.systems:
        raise AuthorError(f"no system {system!r} in the model (systems: {', '.join(sorted(spec.systems))})")
    out["parts"] = parts_of(spec, system)
    began = time.time()
    p = run_trial([sys.executable, "-m", "ergostat.library.trial", str(copy), str(seconds), system,
                   *(["--blocks"] if blocks else [])], env, copy, seconds + 120)
    lines = [x for x in p.stdout.splitlines() if x.startswith("{")]
    if p.returncode != 0 or not lines:
        out["ran"] = False
        out["error"] = (p.stderr or p.stdout).strip()[-1500:]
        return out
    out["ran"] = json.loads(lines[-1])
    out["took"] = round(time.time() - began, 1)
    out["verdict"] = verdict(out["ran"])
    return out


def run_trial(cmd: list[str], env: dict, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    """The trial in a session of its own: it stops what it started on its way out; when it overruns, it is asked to
    (SIGTERM), then it and everything under it is stopped, so no run, and no Claude session, outlives it."""
    from .reap import stop
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=cwd,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(proc.pid, grace=10.0, also_group=True)
        proc.kill()
        out, err = proc.communicate()
        err = (err or "") + f"\nthe trial overran {timeout:g}s and was stopped, with everything it started"
    finally:
        if proc.poll() is None:
            proc.kill()
    try:                                                   # anything left in its session, should it have left any
        if os.getpgid(0) != proc.pid:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def verdict(ran: dict) -> list[str]:
    """What the run shows, in a few sentences: what moved, what failed."""
    says = []
    for k, v in ran.get("items", {}).items():
        says.append(f"items {k}: " + ", ".join(f"{n} {s}" for s, n in v["by_state"].items()))
    if not ran.get("items"):
        says.append("no items were recorded")
    for b, v in ran.get("blocks", {}).items():
        if v["type"] not in ("program", "ai", "person"):
            continue
        if v["failed"]:
            says.append(f"block {b} failed: {v['failed'][0]}")
        elif v["runs"]:
            says.append(f"block {b} ran {v['runs']} times, moved {v['moved'] or 'nothing'}")
        elif v.get("asked_a_person"):
            says.append(f"block {b} asked a person {v['asked_a_person']} times")
        else:
            says.append(f"block {b} did not run (its goal held, or nothing commanded it)")
    for f in ran.get("sensor_failures", []):
        says.append(f"sensor {f['sensor']} failed: {f['why']}")
    for f in ran.get("refused", []):
        says.append(f"refused from {f['sensor']}: {f['why']}")
    for g, v in ran.get("goals", {}).items():
        says.append(f"goal {g} ({v['hold']}): {', '.join(v['crossings']) or 'never off'}")
    return says


# ---- where it is drawn

def pieces(nodes: list[dict], edges: list[dict]) -> int:
    """How many parts a drawing falls into: nodes joined by any line."""
    parent = {n["id"]: n["id"] for n in nodes}

    def root(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for e in edges:
        a, b = e.get("from") or e.get("source"), e.get("target") or e.get("to")
        if a in parent and b in parent:
            parent[root(a)] = root(b)
    return len({root(x) for x in parent})


def shape(p, system: str) -> dict:
    """What the two drawings of a system look like, in numbers: the pieces each falls into (one connected chain per
    item kind draws as one), and check's findings about the chain of its kinds' state stocks (spec/chains.py)."""
    from ..spec import chains
    from ..web.server import Live, api
    out: dict = {}
    try:
        live = Live(p)
        for view in ("dynamics", "blocks"):
            g = api(live, "graph", {"view": [view], "system": [system], "open": ["*"]})
            out[f"{view}_pieces"] = pieces(g.get("nodes") or [], g.get("edges") or [])
    except Exception as e:                          # the drawing is the page's; this is a summary of it
        out["error"] = str(e)[:300]
    ps = parts_of(p.model.spec, system)
    mine = {f"stock.{n}" for n in ps["stocks"]} | {f"flow.{n}" for n in ps["flows"]}
    out["chain_findings"] = [f"{x.code} ({x.about}): {x.message}" for x in chains.analyse(p.model.spec) if x.about in mine]
    out["looks_right"] = ("one piece in each view per item kind (an arrival chain, each step's loop sharing its stocks), "
                          "and no chain findings")
    return out


def where(root: Path, system: str) -> dict:
    from .. import model as mdl
    from ..runner import running_pid, web_url
    from ..store import Project
    m = mdl.load(root)
    spec = m.spec
    if system not in spec.systems:
        raise AuthorError(f"no system {system!r} (systems: {', '.join(sorted(spec.systems))})")
    u = spec.uses.get(system) or {}
    p = Project(m)
    url = web_url(p) if running_pid(p, wait=False) else None
    q = f"system={system}"
    out = {"system": system, "within": spec.within.get(system), "template": u.get("template"),
           "written_at": str(u["where"]) if u.get("where") else None, "parts": parts_of(spec, system),
           "pages": {"dynamics": f"/diagram?view=dynamics&{q}", "blocks": f"/diagram?view=blocks&{q}"}}
    if url:
        out["pages"] = {k: url + v for k, v in out["pages"].items()}
    else:
        out["to_see_it"] = f"ergostat -C {root} web (or run), then open the pages above on the address it prints"
    out["shape"] = shape(p, system)
    for flag in ([], ["--blocks"]):
        r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(root), "system", system, *flag], capture_output=True,
                           text=True, timeout=60, env={**os.environ, "NO_COLOR": "1"})
        out["drawn" if not flag else "as_blocks"] = (r.stdout or r.stderr).strip()[-4000:]
    return out
