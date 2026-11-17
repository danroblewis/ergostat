"""Each kind of part of a recipe, rendered as Markdown within its budget (SPEC §12i). ``talk.py`` has the parts made
of what was said (``owner-words``, ``session``, and the sessions in an item's history)."""

from __future__ import annotations

import json
import subprocess

from ..decisions.kinds import CORRECTION, DECISION
from . import talk
from .fit import For, cut, demote, known, system_parts, when


def decisions(ctx: For, params: dict, budget: int) -> str:
    from ..decisions import context as cx
    return demote(cx.render(ctx.p, DECISION, ctx.fill(params.get("scope")) or None, budget, bool(params.get("proposed"))))


def corrections(ctx: For, params: dict, budget: int) -> str:
    from ..decisions import context as cx
    return demote(cx.render(ctx.p, CORRECTION, ctx.fill(params.get("kind")) or None, budget, bool(params.get("proposed"))))


def _short(v, n: int = 300) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + " [...]"


def item_history(ctx: For, params: dict, budget: int) -> str:
    if ctx.item is None:
        return "## The item\n\nNo item: this run was given none.\n"
    from ..spec import items as its
    from ..transcripts import FIELDS
    it = ctx.item
    d = its.detail(ctx.p.events, ctx.spec, it.id, history=None) or {}
    out = [f"## The item: {it.id}", ""]
    out.append(f"A {it.kind or 'item'}" + (f", {it.state} since {when(it.entered)}" if it.state else "") +
               f"; {it.n} events from {when(it.first)} to {when(it.last)}.")
    out.append("")
    fields = [(k, v) for k, v in it.fields.items() if k not in FIELDS]
    if fields:
        out += ["Its fields:", ""] + [f"- {k}: {_short(v)}" for k, v in fields] + [""]
    moves = d.get("moves") or []
    if len(moves) > 1:
        out += ["Its moves: " + " → ".join(f"{m['to']} ({when(m['time'])})" for m in moves), ""]
    n = int(params.get("events") or 20)
    rec = [e for e in d.get("record") or [] if not e["type"].startswith("claude.")][-n:]
    if rec:
        out += [f"Its latest {len(rec)} events:", ""]
        for e in rec:
            data = {k: v for k, v in (e.get("data") or {}).items() if k not in FIELDS}
            out.append(f"- {when(e['time'])} {e['type']} by {e.get('source') or '?'}" + (f": {_short(data, 240)}" if data else ""))
        out.append("")
    text = "\n".join(out)
    if params.get("sessions", True):
        ss = talk.linked_sessions(ctx)
        if ss:
            room = max(0, budget - len(text) - 100)
            per = room // max(1, min(len(ss), 3))
            parts = [talk.key_turns(ctx, s, int(params.get("turns") or 4), per) for s in ss[-3:]]
            text += "\n### The sessions that worked on it\n\n" + (f"({len(ss) - 3} earlier not shown)\n\n" if len(ss) > 3 else "") \
                + "\n".join(parts)
    return cut(text, budget)


def _git(repo, *args) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, (p.stdout if p.returncode == 0 else p.stderr).strip()


def running(ctx: For) -> list[str]:
    """Blocks whose run began and has not ended, and sessions still open."""
    out = []
    last: dict[str, dict] = {}
    for e in ctx.p.events.query(n=400, type="agent.started,agent.ran,agent.failed"):
        last[e["item"]] = e
    for b, e in sorted(last.items()):
        if e["type"] == "agent.started" and b != ctx.block:
            out.append(f"- block {b}: running since {when(e['time'])}" + (f" ({e['data'].get('trigger')})" if e.get("data") else ""))
    from ..spec import items as its
    for k in ctx.spec.items.values():
        if "claude-session" in k.formats.values() and k.states:
            for it in its.project(ctx.p.events, ctx.spec, k.name, transcript=False):
                if it.state == k.states[0] and ctx.now - it.last < 6 * 3600:
                    out.append(f"- session {it.id}: {it.state} since {when(it.entered)}" +
                               (f", {it.fields['role']}" if it.fields.get("role") else ""))
    return out


def findings(ctx: For, parts: list[str]) -> list[str]:
    from ..spec import watch
    try:
        found = [x for x in ctx.p.model.problems if x.level != "error"] + watch.find(ctx.p, ctx.spec, watch.WINDOW)
    except Exception as e:                                      # the record busy or the model broken: said, not fatal
        return [f"- (findings could not be read: {type(e).__name__}: {e})"]
    if parts:
        want = set(parts) | ({f"block.{ctx.block}"} if ctx.block else set())
        found = [f for f in found if f.about in want]
    out = [f"- {f.code}: {f.message}" for f in found[:12]]
    from ..claims import record
    week = ctx.now - 7 * 86400
    for c in record.stored(ctx.p, since=week).values():
        a = c.get("about") or {}
        if c["state"] == "contradicted" and (a.get("item") == ctx.item_id or a.get("part") in parts or
                                             (not parts and not ctx.item)):
            out.append(f"- contradicted claim by {c.get('block')}: \"{c.get('says')}\" ({c.get('why')})")
    return out


def state(ctx: For, params: dict, budget: int) -> str:
    out = ["## The state now", "", f"As of {when(ctx.now)}.", ""]
    repo = ctx.spec.root / str(params.get("repo") or ".")
    code, top = _git(repo, "rev-parse", "--show-toplevel")
    if code == 0:
        branch = params.get("branch")
        if not branch:
            branch = "main" if _git(repo, "rev-parse", "--verify", "-q", "main")[0] == 0 else "HEAD"
        since = float(params.get("since") or 86400)
        code, log = _git(repo, "log", f"-n{int(params.get('commits') or 15)}", f"--since={int(ctx.now - since)}",
                         "--date=format:%m-%d %H:%M", "--format=- %h %ad %s", branch)
        rel = str(params.get("repo") or ".")
        out += [f"What moved on {branch} ({rel}) in the last {since / 3600:g}h:", "", log or "- nothing", ""]
        code, st = _git(repo, "status", "--short")
        if code == 0 and st:
            lines = st.splitlines()
            out += [f"Uncommitted there: {len(lines)} files" + (f" ({', '.join(x[3:] for x in lines[:6])}"
                                                                 f"{', ...' if len(lines) > 6 else ''})" if lines else ""), ""]
    if params.get("running", True):
        r = running(ctx)
        out += ["What is running:", ""] + (r or ["- nothing else"]) + [""]
    if params.get("findings", True):
        parts = ctx.parts_of_item()
        f = findings(ctx, parts)
        about = f" on {', '.join(parts[:6])}{'...' if len(parts) > 6 else ''}" if parts else ""
        out += [f"Open findings{about}:", ""] + (f or ["- none"]) + [""]
    return cut("\n".join(out), budget)


def docs(ctx: For, params: dict, budget: int) -> str:
    out, used, missing = ["## Documents", ""], 0, []
    for pat in params.get("files") or []:
        files = sorted(ctx.spec.root.glob(pat)) or ([ctx.spec.root / pat] if (ctx.spec.root / pat).is_file() else [])
        if not files:
            missing.append(pat)
        for f in files:
            if not f.is_file():
                continue
            body = f"=== {f.relative_to(ctx.spec.root)} ===\n{f.read_text(encoding='utf-8', errors='replace').rstrip()}\n"
            room = budget - used - 100
            if room <= 200:
                missing.append(f"{f.relative_to(ctx.spec.root)} (did not fit)")
                continue
            body = cut(body, room)
            out.append(body)
            used += len(body)
    if missing:
        out.append("Not included: " + ", ".join(missing))
    return "\n".join(out) + "\n"


def _latest(ctx: For, x) -> str:
    best = None
    for s in getattr(x, "sensors", {}).values():
        got = ctx.p.measurements.latest(s.series)
        if got and (best is None or got[0] > best[0]):
            best = got
    return f"{best[1]:g}" + (f" {x.unit}" if getattr(x, "unit", "") else "") + f" ({when(best[0])})" if best else "not read yet"


def model(ctx: For, params: dict, budget: int) -> str:
    spec = ctx.spec
    want = []
    for r in params.get("parts") or []:
        r = ctx.fill(r)
        if r.startswith("system."):
            want += system_parts(spec, r[7:])
        elif known(spec, r):
            want.append(r)
    if not params.get("parts"):
        want = ctx.parts_of_item()
    if not want:
        return "## The model\n\n" + ("No parts: " + (f"{ctx.item_id} names none, and its kind is in no system.\n"
                                                    if ctx.item else "this run was given no item, and the part names none.\n"))
    status: dict[str, str] = {}
    for e in ctx.p.events.query(n=300, type="loop.off,loop.holding"):
        status[e["item"]] = e["type"].split(".", 1)[1]
    out = ["## The model", "", "The parts this work is about, as the model has them now.", ""]
    goals = set()
    for r in want:
        kind, _, name = r.partition(".")
        if kind == "goal":
            goals.add(name)
            continue
        x = {"stock": spec.stocks, "flow": spec.flows, "auxiliary": spec.auxiliaries}.get(kind, {}).get(name)
        if x is None:
            continue
        line = f"- {r}: {_latest(ctx, x)}"
        if kind == "flow":
            line += f" (from {x.source or 'outside'} to {x.target or 'outside'})"
        if x.description:
            line += f". {x.description}"
        out.append(line)
        if params.get("goals", True):
            goals |= {g for g, gl in spec.goals.items() if gl.of.kind == kind and gl.of.name == name}
    if goals:
        out += ["", "Their goals:", ""]
        for g in sorted(goals):
            gl = spec.goals[g]
            out.append(f"- goal {g}: {gl.of} {gl.hold.op} {gl.hold.value:g}, {status.get(g, 'not judged yet')}" +
                       (f". {gl.description}" if gl.description else ""))
    return cut("\n".join(out) + "\n", budget)


RENDER = {"decisions": decisions, "corrections": corrections, "owner-words": talk.owner_words,
          "item-history": item_history, "state": state, "session": talk.session, "docs": docs, "model": model}


def render(ctx: For, kind: str, params: dict, budget: int) -> str:
    try:
        text = RENDER[kind](ctx, params, budget)
    except Exception as e:                                          # one part that cannot be read leaves the others
        text = f"## {kind}\n\n(This part could not be rendered: {type(e).__name__}: {e})\n"
    return cut(text.rstrip("\n") + "\n", budget)
