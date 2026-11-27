"""The AI tier of the modelling subsystem (SPEC §12e): an AI agent given the requests the rule tier could not answer
(``requests.py``), each with the neighbourhood of the model it touches (its part, every part one link from it, as
written in the YAML, and the programs their sensors and blocks run), and a prompt that is the author skill and the
modelling guides made short (``library/templates/modelling/modeller.md``). It proposes descriptions, units,
equations, structure, loops and collectors as ordinary model changes, with the request's finding as evidence.

Each proposal is tried first as ``try_change`` tries it (``improve.trial``: compiled, checked and replayed on a scratch
copy, nothing kept); what would be turned away goes back to the agent once, with why, and only what would be proposed is
printed. Every call says what it cost (``claude -p --output-format json``: dollars, tokens), recorded on the requests
it was given."""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path

from ..sensing import command
from ..spec.ir import Spec
from . import gate as gt
from . import improve as im
from .requests import evidence_of

GUIDE = Path(__file__).resolve().parent.parent / "library" / "templates" / "modelling" / "modeller.md"
MOST = 8                    # requests given to one call
FAILS = 3                   # failed calls (``call``'s ``error``) on one item before it waits for the owner (no try counted)
LINES = 40                  # lines of YAML shown for one part at most
CODE_LINES = 60             # lines of a program a part runs shown at most
TOOLS_OFF = "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"


def _text_of(spec: Spec, ref: str) -> str | None:
    """A part as the YAML writes it: its name line and everything under it (at most ``LINES`` lines)."""
    kind, _, name = ref.partition(".")
    try:
        x, path, at = im._part(spec, ref)
    except Exception:
        return None
    from . import yamledit as ye
    ls = ye.lines_of(path)
    end, _ = ye.children(ls, at)
    body = ls[at - 1:min(end, at - 1 + LINES)]
    rel = path.relative_to(Path(spec.root).resolve()) if path.is_relative_to(Path(spec.root).resolve()) else path.name
    return f"# {rel}:{at} ({kind} {name})\n" + "\n".join(body)


def _programs(spec: Spec, refs: set[str]) -> list[str]:
    """The project's own programs the parts run (a sensor's ``run:``, a block's), the first lines of each."""
    out, seen = [], set()
    cmds = []
    for r in refs:
        kind, _, name = r.partition(".")
        x = spec.measured(kind).get(name) if kind in ("stock", "flow", "auxiliary") else spec.blocks.get(name) if kind == "block" else None
        if x is None:
            continue
        cmds += [command(spec, s) for s in (getattr(x, "sensors", None) or {}).values() if s.commands]
        if kind == "block" and x.params.get("run"):
            cmds.append(str(x.params["run"]))
        elif kind == "block" and x.params.get("daemon") in spec.daemons:
            cmds.append(spec.daemons[x.params["daemon"]].run)
    root = Path(spec.root).resolve()
    for c in cmds:
        for w in re.findall(r"[\w./-]+\.(?:py|sh|js|rb)", c):
            f = (root / w).resolve()
            if f in seen or not f.is_file() or not f.is_relative_to(root):
                continue
            seen.add(f)
            ls = f.read_text(encoding="utf-8", errors="replace").split("\n")
            out.append(f"# {f.relative_to(root)} (first {min(len(ls), CODE_LINES)} of {len(ls)} lines)\n" + "\n".join(ls[:CODE_LINES]))
    return out[:3]


def neighbourhood(spec: Spec, refs: list[str]) -> list[str]:
    """The parts a request touches and every part one link from them, as written (each once)."""
    want = [r for r in refs if r and r != "model"]
    near = set(want)
    for r in want:
        if r.startswith("projections."):
            k = r.split(".", 1)[1]
            near |= {f"stock.{n}" for n, st in spec.stocks.items()
                     if any((s.items or {}).get("kind") == k for s in st.sensors.values())}
            near |= {f"flow.{n}" for n, f in spec.flows.items()
                     if any((s.items or {}).get("kind") == k for s in f.sensors.values())}
            near |= {f"block.{n}" for n, b in spec.blocks.items() if b.takes and b.takes.kind == k}
    near |= gt.neighbourhood(spec, [r for r in near if not r.startswith("projections.")])
    order = sorted(near, key=lambda r: (r not in want, r))
    return order


def prompt(p, spec: Spec, reqs: list[dict], feedback: list[str] | None = None) -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    lines = [guide, "", "## The model", "",
             f"Files: {', '.join(str(Path(f).resolve().relative_to(Path(spec.root).resolve())) for f in spec.files)}. "
             f"Projections: " + "; ".join(f"{k} ({', '.join(x.states)})" for k, x in spec.items.items()
                                          if not k.startswith("ergostat.")), "", "## The requests", ""]
    refs: list[str] = []
    for r in reqs:
        lines.append(json.dumps({"id": r["id"], "code": r["code"], "about": r["about"], "says": r.get("says"),
                                 "where": r.get("where"), "evidence": evidence_of(r),
                                 **({"fix": r["fix"]} if r.get("fix") else {}),
                                 **({"why held": r["why"]} if r.get("why") else {})}, ensure_ascii=False))
        refs.append(r["about"])
    lines += ["", "## The model near them, as written", ""]
    near = neighbourhood(spec, refs)
    shown = 0
    for ref in near:
        t = _text_of(spec, ref)
        if t and shown < 40:
            lines += ["```yaml", t, "```"]
            shown += 1
    progs = _programs(spec, set(near))
    if progs:
        lines += ["", "## Programs they run (read before you describe what they measure or do)", ""]
        for t in progs:
            lines += ["```", t, "```"]
    from . import reviewer as rv
    lines += rv.lines(p, os.environ.get("ERGOSTAT_BLOCK") or "modeller")
    if feedback:
        lines += ["", "## What ergostat said of your last answer (fix these, or say cannot)", ""] + [f"- {x}" for x in feedback]
    return "\n".join(lines)


def parse(text: str) -> tuple[list[dict], list[dict]]:
    """The propose lines and the cannot lines of an answer."""
    props, cannot = [], []
    for line in str(text or "").splitlines():
        line = line.strip().strip("`").strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("propose"), dict):
            props.append(obj["propose"])
        elif isinstance(obj, dict) and obj.get("cannot"):
            cannot.append(obj)
    return props, cannot


def call(text: str, model: str, timeout: float = 600.0) -> dict:
    """One ``claude -p`` call, tools off: ``{"result", "usd", "tokens_in", "tokens_out", "seconds"}`` (``ERGOSTAT_AI`` names
    another command that answers the same way, as the tests' stand-in does). One that fails (times out, exits non-zero,
    says ``is_error``, or says no cost that is a number) has an ``error`` saying what it said, and is charged its
    reservation (``unsaid``), or what it said if more."""
    cmd = [os.environ.get("ERGOSTAT_AI") or "claude", "-p", "--model", model, "--output-format", "json",
           "--disallowedTools", TOOLS_OFF]
    if Path(cmd[0]).name == "claude":              # its reservation as claude's budget (checked after a turn: no ceiling)
        cmd += ["--max-budget-usd", f"{unsaid(text, model)['usd']:.6f}"]
    t0 = time.perf_counter()
    try:
        got = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=timeout)
        try:
            out = json.loads(got.stdout)
        except ValueError:
            if not got.returncode:
                raise
            out = {"result": got.stdout}                              # a failed exit: what it printed is what it said
    except (subprocess.TimeoutExpired, ValueError, OSError) as e:      # what it cost is not said: charged as the most it
        return {"result": "", **unsaid(text, model), "seconds": time.perf_counter() - t0,   # could have (fail closed)
                "error": f"{type(e).__name__}: {e}"}
    out = out if isinstance(out, dict) else {"result": str(out)}
    usd = out.get("total_cost_usd")
    said = isinstance(usd, (int, float)) and not isinstance(usd, bool) and math.isfinite(usd) and usd >= 0
    if got.returncode or out.get("is_error") or not said:         # failed, or its cost unsaid:
        why = f"exit {got.returncode}" if got.returncode else "is_error" if out.get("is_error") else "no cost said"
        told = str(out.get("result") or got.stderr or "").strip()[:300]                      # charged its reservation,
        r = unsaid(text, model)                                                                # or more if it said more
        return {"result": "", **r, "usd": max(r["usd"], float(usd) if said else 0.0), "seconds": time.perf_counter() - t0,
                "error": f"the call failed ({why})" + (f": {told}" if told else "")}
    u = out.get("usage") or {}
    tin = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
    return {"result": str(out.get("result") or ""), "usd": float(usd), "tokens_in": tin,
            "tokens_out": int(u.get("output_tokens") or 0), "seconds": round(time.perf_counter() - t0, 1)}


def ask(p, text: str, model: str) -> dict | None:
    """The day's budget asked for one call (SPEC §9.9): it reserves the call's ``unsaid`` estimate. Returns its permit
    (None: no ``budget:``), or raises ``Capped`` (``budget: …``). Inside a run (``$ERGOSTAT_RUN``) the call is the
    run's own: every caller prints its cost as one of the run's result lines, so the run's end includes it."""
    from ..costs import budget as bg
    from .modeller_spend import Capped
    run = os.environ.get("ERGOSTAT_RUN")
    token = bg.WITHIN.set(bg.WITHIN.get() or ((run, True) if run else None))
    try:
        permit, no = bg.ask(p, p.model.spec, os.environ.get("ERGOSTAT_BLOCK") or "modeller", unsaid(text, model)["usd"])
    finally:
        bg.WITHIN.reset(token)
    if no:
        raise Capped(f"budget: {no}")
    return permit


def asked(p, text: str, model: str, timeout: float = 600.0, fn=None, permit=None) -> dict:
    """``fn`` (``call``) once ``ask`` allows it (or under ``permit``, asked already), its permit closed with the cost
    it said. A failed call is closed with null cost: charged its reserve (or what it said, if more)."""
    from ..costs import budget as bg
    from .modeller_spend import Capped
    permit, r, cost = permit or ask(p, text, model), unsaid(text, model)["usd"], None
    try:
        got = (fn or call)(text, model, timeout)
        cost = None if got.get("error") and got.get("usd") == r else got.get("usd")
    except Capped:                                  # (its own cap refused it: no process started, nothing spent)
        cost = 0.0
        raise
    finally:
        bg.done(permit, cost)
    return got


MOST_OUT = 16000            # output tokens a call that said nothing of its cost is charged for, besides its prompt
SYSTEM_IN = 20000           # input tokens of claude's own system prompt, read on every call besides ours


def unsaid(text: str, model: str) -> dict:
    """The cost charged for a call that never said its own (killed, timed out, or answered no JSON): its prompt read
    (with claude's own system prompt) and ``MOST_OUT`` written, at the model's price; dear rather than free. An
    estimate, not a bound: ``claude -p`` is given no output limit, so a call can cost more."""
    from ..costs import prices
    tin = len(text) // 3 + 1 + SYSTEM_IN
    usd = prices.estimate(model, {"input": tin, "output": MOST_OUT})
    return {"usd": round(usd if usd is not None else 1.0, 6), "tokens_in": tin, "tokens_out": MOST_OUT, "estimated": True}


def per_call(timeout: float | None, calls: int) -> float:
    """Each call's time limit, so ``calls`` of them (and the work between) fit in the block's ``timeout``."""
    if not timeout:
        return 600.0
    return max(30.0, min(600.0, (float(timeout) * 0.8) / max(1, calls)))


def answer(p, reqs: list[dict], model: str = "haiku", retry: bool = True, timeout: float = 600.0, on_call=None,
           within=None) -> dict:
    """The AI tier on these requests: ``{"proposals": [propose], "cannot": [{id, why}], "cost": {...}, "tried": [...]}``,
    each proposal one ``try_change`` would propose (the rest given back once, with why). ``within(prompt)``: the
    context each call is made in (``modeller_spend.held``), given a list for its cost; one that raises ``Capped``
    stops the run there (``cost["capped"]``), as a refusal by the day's budget (``asked``) does. A call that reports
    more than its reservation is in ``cost["over"]``."""
    from .modeller_spend import Capped
    spec: Spec = p.model.spec
    cost = {"usd": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": 0, "seconds": 0.0, "model": model}
    good, cannot, tried = [], [], []
    feedback: list[str] | None = None
    for attempt in range(2 if retry else 1):
        text = prompt(p, spec, reqs, feedback)

        def capped(text, model, timeout):          # the tier's own cap, asked once the day's budget has said yes
            with (within(text) if within else contextlib.nullcontext([])) as box:
                box.append(got := call(text, model, timeout))
            return got
        try:
            got = asked(p, text, model, timeout, capped)   # (refused by the day's budget: Capped, ``budget: …``)
        except Capped as e:
            cost["capped"] = str(e)
            break
        cost["calls"] += 1
        if (r := unsaid(text, model)["usd"]) < float(got.get("usd") or 0):
            cost.setdefault("over", []).append((round(float(got["usd"]) - r, 6), r))
        for k in ("usd", "tokens_in", "tokens_out", "seconds"):
            cost[k] = round(cost[k] + got.get(k, 0), 6)
        if on_call is not None:                     # each call's cost said as it is spent: a run cut short keeps it
            on_call(got)
        if got.get("error"):
            cost["error"] = got["error"]
            break
        props, cant = parse(got["result"])
        cannot += cant
        feedback = []
        for raw in props:
            t = im.trial(p, raw)
            tried.append({"title": raw.get("title"), "would": t["would"], "why": t.get("why"), "kind": t.get("kind"),
                          "attempt": attempt + 1})
            if t["would"] == "be proposed":
                if json.dumps(raw, sort_keys=True) not in {json.dumps(g, sort_keys=True) for g in good}:
                    good.append(raw)
            else:
                feedback.append(f"{raw.get('title') or 'a change'}: not proposed: {t.get('why')}"[:500])
        if not feedback:
            break
        answered = {e for raw in good for r in raw.get("reasons") or [] for e in
                    ([r.get("evidence")] if not isinstance(r.get("evidence"), list) else r.get("evidence"))}
        left = [r for r in reqs if evidence_of(r) not in answered and r["id"] not in {c.get("cannot") for c in cannot}]
        if not left:
            break
        reqs = left
    return {"proposals": good, "cannot": cannot, "cost": cost, "tried": tried}


def result_line(cost: dict) -> dict:
    """A call's (or run's) cost as a Claude Code result message, so the engine adds it to the run (``costs/ai.py``)."""
    return {"type": "result", "subtype": "success", "total_cost_usd": round(cost.get("usd") or 0.0, 6),
            "num_turns": cost.get("calls") or 1,
            "usage": {"input_tokens": cost.get("tokens_in") or 0, "output_tokens": cost.get("tokens_out") or 0},
            "modelUsage": {}}
