"""Redesign beside refinement (SPEC §12e, *Redesign*): one change set (``changeset.py``), many coordinated edits
proposed together, judged as a whole by a scorecard (``scorecard.py``), kept as one ``ergostat.model-change`` item of
kind ``redesign``.

A change set is written ``{"title", "system", "summary", "edits": [...], "confidence"}``: the edits are made in order on
a scratch copy, it must compile, and it is measured against the record as it is; what it adds says ``inferred:`` (the
change's own id once recorded). Its verdict is the scorecard's, said again by the judge on the record when it takes it
up. It is never written by the judge unless the owner promoted the class by name (``accept: {redesign: auto}``).

When one is made: the owner asks (``ergostat improve --redesign [SYSTEM]``, the Model page's button), and the
redesigner block takes the ask up on its next run. At most one waits for each system, and its runs stop for the day
once they have spent the daily cap (``spent``)."""

from __future__ import annotations

import json
import time

from ..spec.ir import Spec
from . import changeset as cs
from . import improve as im
from . import proposals as pr
from . import version as ver

KIND = "redesign"
ASKED = "ergostat.model.redesign-asked"
RAN = "ergostat.model.redesign-ran"


def settings(spec: Spec) -> dict:
    """The redesigner's settings, as the model's ``use: modelling`` gave them (``redesign: {when, model, budget, rounds,
    daily}``), else the defaults."""
    out = {"when": "auto", "model": "haiku", "budget": 0.5, "rounds": 3, "daily": 2.0}
    for u in (spec.uses or {}).values():
        got = (u.get("values") or {}).get("redesign") if u.get("template") == "modelling" else None
        if isinstance(got, dict):
            out.update({k: got[k] for k in out if got.get(k) is not None})
    return out


def system_of(spec: Spec, system: str | None) -> str:
    s = (system or "").strip()
    if s and s not in ("model", "all") and s not in spec.systems:
        raise ValueError(f"no system {s} (the model's: {', '.join(sorted(spec.systems)) or 'none: the whole model'})")
    return s if s and s not in ("all",) else "model"


def members(spec: Spec, system: str) -> list[str]:
    """The parts of a system (every part of the model for ``model``)."""
    if system == "model":
        return [f"{k}.{n}" for k, t in (("stock", spec.stocks), ("flow", spec.flows), ("auxiliary", spec.auxiliaries),
                                       ("parameter", spec.parameters), ("goal", spec.goals), ("block", spec.blocks))
                for n in t]
    from ..correspond import inside
    return [x for x in inside(spec, system) if not x.startswith("system.")]


# ---- made and recorded

def validate(p, spec: Spec, by: str, raw: dict, scratch: cs.Scratch | None = None) -> dict:
    """A change set checked and scored: its record to keep, or ``ProposeError`` with why it is not proposed."""
    from . import scorecard as sc
    if not isinstance(raw, dict):
        raise im.ProposeError("a change set: {title, system, summary, edits: [...]}")
    edits = raw.get("edits")
    if not isinstance(edits, list) or not edits:
        raise im.ProposeError("edits: a list of edits, made in order")
    system = system_of(spec, raw.get("system"))
    s = scratch
    if s is None:
        s = cs.Scratch(p, spec)
        for i, e in enumerate(edits):
            try:
                s.apply(e)
            except cs.ChangeSetError as err:
                raise im.ProposeError(f"edit {i + 1} ({cs.said(e) if isinstance(e, dict) else e!r}): {err}") from None
    s.keep_names()
    if not s.changed():
        raise im.ProposeError("it changes nothing")
    after, problems = s.compiled()
    if after is None:
        raise im.ProposeError("the model it leaves does not compile: " + "; ".join(s.errors()[:3]))
    im._governed(spec, after)
    es_ = s.edits()
    marked = _renamed_unmarked(im.mark_new(es_, spec, after), spec, after)   # what it adds says inferred: (its id when
    # recorded); a part renamed is not new: it keeps what it said (formerly: its old name)
    if marked is not None:
        try:
            after2, problems2 = s_compiled(p, marked)
            if after2 is not None and not [x for x in problems2 if x.level == "error"]:
                es_, after, problems = marked, after2, problems2
        except Exception:
            pass
    from ..spec import read
    _, before_problems = read(p.model.path)
    card = sc.score(p, spec, before_problems, after, problems)
    parts = card["parts"]
    beyond = outside(spec, after, system, parts)
    if beyond:
        raise im.ProposeError(f"it changes parts outside system {system} ({', '.join(beyond[:6])}): a redesign of a system "
                              f"changes that system, and other systems only by the names it renames")
    refs = [*parts["added"], *parts["changed"], *(x.split(" → ")[1] for x in parts["renamed"])]
    j = im.joined(es_)
    conf = raw.get("confidence")
    from . import redesign_due as due
    return {"kind": KIND, "said_kind": KIND, "made_by": by, "system": system, **owners(spec, after),
            "unit_sig": due.signature(spec, system),
            "title": str(raw.get("title") or f"A redesign of {system}")[:200],
            "summary": str(raw.get("summary") or "")[:2000], "reason": str(raw.get("summary") or raw.get("title") or "")[:500],
            "confidence": conf if isinstance(conf, int | float) and 0 <= conf <= 1 else None,
            "parts": refs[:60], "touched": [r for r in refs if r.split(".")[0] in ("stock", "flow", "auxiliary")][:60],
            "target": system, "new_parts": parts["added"], "gone_parts": parts["removed"],
            "redesign": {"edits": s.done, "parts": parts, "rounds": raw.get("rounds"), "cost": raw.get("cost")},
            "scorecard": card, "findings": {"answered": card["findings"]["resolved"], "new": card["findings"]["introduced"],
                                            "notes_answered": card["craft"]["closed"], "notes_new": card["craft"]["opened"]},
            "edit": j, "change": "a redesign: many edits judged together by a scorecard",
            "renames": {o: n for o, n in (x.split(" → ") for x in parts["renamed"])
                        if o.split(".")[0] in ("stock", "flow", "auxiliary")}}


def outside(before: Spec, after: Spec, system: str, parts: dict) -> list[str]:
    """The parts a change set changes that are not in ``system`` (none for the whole model): added, taken away,
    renamed or changed, but for a part whose only change is a name it refers to that the change set renames."""
    import json
    import re

    from ..spec.ir import Ref
    if system == "model":
        return []
    renames = dict(x.split(" → ") for x in parts.get("renamed") or [])

    def inside(spec: Spec, ref: str) -> bool:
        kind, _, name = ref.partition(".")
        if kind == "parameter":                       # a parameter is the system's when its parts use it
            from .proposals import users_of
            return any(inside(spec, u) for u in users_of(spec, name))
        return kind not in ("stock", "flow", "auxiliary", "goal", "block") or spec.inside(Ref(kind, name), system)

    def same_but_names(ref: str) -> bool:
        from .changeset import _plain
        kind, _, name = ref.partition(".")
        table = {"stock": "stocks", "flow": "flows", "auxiliary": "auxiliaries", "goal": "goals", "block": "blocks"}.get(kind)
        if table is None or name not in getattr(before, table) or name not in getattr(after, table):
            return False
        names = {o.split(".", 1)[1]: n.split(".", 1)[1] for o, n in renames.items()}

        def follow(x, key=None):                      # the names it refers to, renamed: reference fields only
            if key in NOT_REFERENCES:                 # (its words, its sensors' selectors, labels and commands as written)
                return x
            if isinstance(x, dict):
                return {k: follow(v, k) for k, v in x.items()}
            if isinstance(x, list):
                return [follow(v, key) for v in x]
            if isinstance(x, str):
                for o, n in names.items():
                    x = re.sub(rf'(?<![\w-]){re.escape(o)}(?![\w-])', n, x)
            return x
        was = follow(json.loads(_plain(getattr(before, table)[name])))
        return was == json.loads(_plain(getattr(after, table)[name]))
    out = [r for r in parts.get("added") or [] if not inside(after, r) and _system_of(after, r)]   # (a new part
    # placed in no system is the redesign's to place: taken as the system's)
    out += [r for r in parts.get("removed") or [] if not inside(before, r)]
    out += [o for o in renames if not inside(before, o)]
    out += [r for r in parts.get("changed") or [] if r not in renames.values() and not inside(before, r)
            and not same_but_names(r)]
    return out


NOT_REFERENCES = {"description", "sensors", "sensor", "run", "query", "items", "label", "labels", "title", "ask", "prompt",
                  "where", "parse", "builtin"}


def _system_of(spec: Spec, ref: str) -> str | None:
    from ..spec.ir import Ref
    kind, _, name = ref.partition(".")
    return spec.owner(Ref(kind, name))


def owners(before: Spec, after: Spec) -> dict:
    """What makes a redesign the owner's to write, whatever the policy (SPEC §12e, the judge's ``accept``): it rewires
    a kind's chain (``rewires``: a flow between two state stocks re-pointed or added), or changes control
    (``control``: a goal, a block or an agent). A part it takes away is said by ``gone_parts``."""
    from . import structural as stc
    out = {}
    if stc.rewired(before, after):
        out["rewires"] = True
    if ver.control(before) != ver.control(after):
        out["control"] = True
    return out


def _renamed_unmarked(es_, before: Spec, after: Spec):
    """``mark_new``'s edits without the ``inferred:`` it wrote under a part that says ``formerly:`` a part taken away."""
    import re

    from . import structural as stc
    from . import yamledit as ye
    if es_ is None:
        return None
    renamed = set()
    for attr in ("stocks", "flows", "auxiliaries"):
        a, b = getattr(before, attr), getattr(after, attr)
        renamed |= {n for n in b if n not in a and any(w in a for w in (getattr(b[n], "formerly", None) or []))}
    out = []
    for e in es_:
        hunks = []
        for h in e.hunks:
            new, name = [], None
            for line in h.new:
                m = re.match(r"^\s*([a-z][a-z0-9-]*):\s*(#.*)?$", line)
                if m:
                    name = m.group(1)
                if line.strip() == f"inferred: {stc.PENDING}" and name in renamed:
                    continue
                new.append(line)
            hunks.append(ye.Hunk(h.line, list(h.old), new))
        out.append(ye.Edit(e.file, hunks))
    return out


def s_compiled(p, es_):
    from . import trial as tr
    return tr.compiled(p.model.path, tr.texts_after(es_), findings=True)


def submit(p, by: str, raw: dict, run: str | None = None, scratch: cs.Scratch | None = None, at: float | None = None) -> dict:
    """A change set recorded as made (``ergostat.model-change.made``, from its maker), then checked and scored, or
    refused with why. Returns ``{"status", "id", "title", "why", "scorecard"}``."""
    spec: Spec = p.model.spec
    now = at or time.time()
    title = str((raw or {}).get("title") or "a redesign")[:200]
    pid = im._id("redesign", by, run, now, json.dumps(raw, sort_keys=True, default=str))
    made = {"title": title, "made_by": by, "made_by_rung": im._rung(spec, by), "made": now, "created": now, "kind": KIND,
            "version": ver.version(spec), "structure": ver.structure(spec), "run": run,
            "system": (raw or {}).get("system") or "model"}
    with pr.locked(p):
        try:
            x = validate(p, spec, by, raw, scratch)
            from . import reviewer as rv
            x.update(rv.asked(p, by, [], x["system"]))      # sent back by the reviewer: this is its next round
            if x.get("review_held"):
                raise im.ProposeError(x["review_held"])
            same = waiting(p, spec, x["system"])
            if same is not None:
                raise im.ProposeError(f"a redesign of {x['system']} is waiting already: {pr.item_of(same['id'])}")
        except (im.ProposeError, ValueError) as e:
            pr.event(p, pid, "made", made, source=by, causedby=run)
            pr.event(p, pid, "refused", {"why": str(e)})
            return {"status": "not-proposed", "id": pid, "title": title, "why": str(e)}
        pr.event(p, pid, "made", made, source=by, causedby=run)
        x["edit"] = im.stamped(x["edit"], pid)
        x["method"] = (f"made by {by} ({im._rung(spec, by) or 'a block'}): {len(x['redesign']['edits'])} edits made in order on "
                       f"a scratch copy, compiled, checked, and scored on the record as it is")
        pr.event(p, pid, "checked", x)
    return {"status": "proposed", "id": pid, "title": x["title"], "why": None, "scorecard": x["scorecard"]}


def waiting(p, spec: Spec, system: str) -> dict | None:
    """The redesign of this system waiting (checked, under test or passed), if there is one."""
    for x in pr.stored(p).values():
        if x.get("kind") == KIND and x["state"] in pr.OPEN and (x.get("system") or "model") == system:
            return x
    return None


def judged(p, x: dict, at: float | None = None) -> tuple[str, str, dict]:
    """The judge's verdict on a redesign: its scorecard worked out again on the record as it is now; passed when it
    is better, failed otherwise (the scorecard kept either way)."""
    from ..spec import read
    from . import scorecard as sc
    from . import trial as tr
    spec = p.model.spec
    after, problems = tr.compiled(p.model.path, tr.texts_after(tr.edits_of(x)), findings=True)
    if any(e.level == "error" for e in problems):
        return "failed", "the model it leaves no longer compiles: " + "; ".join(str(e) for e in problems if e.level == "error")[:300], {}
    _, before = read(p.model.path)
    card = sc.score(p, spec, before, after, problems, at=at)
    return ("passed" if card["verdict"] == "better" else "failed"), card["why"], card


# ---- when one is made

def ask(p, system: str | None = None, by: str = "owner", why: str | None = None) -> dict:
    """The owner asks for a redesign of a system (or the whole model): recorded, for the redesigner to take up."""
    spec = p.model.spec
    s = system_of(spec, system)
    e = p.events.add(ASKED, item=p.model.name, source=by, data={"system": s, **({"why": why} if why else {})})
    return {"asked": s, "event": e.get("id") if isinstance(e, dict) else None}


def asked(p, now: float | None = None) -> list[str]:
    """The systems the owner asked a redesign of that no run has taken up since."""
    now = now or time.time()
    asks = p.events.query(n=None, type=ASKED, since=now - WEEK)          # (an ask unanswered a week is let go)
    ran = p.events.query(n=None, type=RAN, since=now - WEEK)
    last = {}
    for e in ran:
        s = (e.get("data") or {}).get("system") or "model"
        last[s] = max(last.get(s, 0.0), e["time"])
    out = []
    for e in asks:
        s = (e.get("data") or {}).get("system") or "model"
        if e["time"] > last.get(s, 0.0) and s not in out:
            out.append(s)
    return out


def ran(p, system: str, data: dict) -> None:
    p.events.add(RAN, item=p.model.name, source=data.get("by") or "redesigner", data={"system": system, **data})


WEEK = 7 * 86400.0
RUNNING_FOR = 15 * 60.0      # a run started and not ended this long ago is taken as gone (the block's timeout)
HOLD_FOR = 5 * 60.0          # the judge holds its own writes for a run this long at most: refinement is never frozen


def running(p, now: float | None = None, within: float = RUNNING_FOR) -> bool:
    """A redesigner run is under way (started ``within`` seconds ago and not ended)."""
    now = now or time.time()
    last: dict = {}
    for e in p.events.query(n=None, type=RAN, since=now - within):
        if (e.get("data") or {}).get("result") != "call":           # (a call charged: the run goes on)
            last[(e.get("data") or {}).get("system") or "model"] = (e.get("data") or {}).get("result")
    return any(r == "started" for r in last.values())


def plan(p, when: str = "auto") -> dict:
    """What a run of the redesigner should do now: ``{"system", "why"}`` or ``{"system": None, "why"}`` (nothing).
    It takes up what the owner asked, the oldest first, one a run; with ``when: auto``, else the first system that is
    due (``redesign_due``)."""
    spec = p.model.spec
    for s in asked(p):
        w = waiting(p, spec, s)
        if w is not None:
            ran(p, s, {"result": "waiting", "why": f"asked, but a redesign of {s} is waiting already ({w['id']})"})
            continue
        return {"system": s, "why": ["the owner asked"], "asked": True}
    if when == "auto":
        from . import redesign_due as due
        return due.next_due(p)
    return {"system": None, "why": [f"when: {when}, and nothing asked"]}


DAY = 24 * 3600.0


def charge(p, system: str, got: dict) -> None:
    """One of the redesigner's calls charged as it is spent (``result: call``); a call that never said its cost is
    charged the most it could have cost (``modeller.unsaid``)."""
    ran(p, system, {"result": "call", "cost": {"usd": float(got.get("usd") or 0.0)},
                    **({"estimated": True} if got.get("estimated") else {})})


def spent(p, now: float | None = None, reviewer: bool = True) -> float:
    """What the template's AI calls cost over the last day, in dollars (each charged as it was spent): the redesigner's
    and (unless ``reviewer=False``) the reviewer's, under one daily cap."""
    from . import reviewer as rv
    now = now or time.time()
    return round(sum(float(((e.get("data") or {}).get("cost") or {}).get("usd") or 0.0)
                     for e in p.events.query(n=None, type=RAN, since=now - DAY)) + (rv.spent(p, now) if reviewer else 0.0), 6)


def last(p) -> dict | None:
    """The redesigner's last run that ended: its system, result, change and why (for the Model page's line)."""
    for e in reversed(p.events.query(n=50, type=RAN)):
        d = e.get("data") or {}
        if d.get("result") not in (None, "started", "call"):
            trigger = d.get("why")
            return {"system": d.get("system") or "model", "result": d.get("result"), "id": d.get("id"),
                    "why": d.get("why_not"), "trigger": "; ".join(trigger) if isinstance(trigger, list) else trigger,
                    "at": e["time"]}
    return None
