"""The rule tier of the modelling subsystem (SPEC §12e): the cheapest tier, a program on the rule rung. For each request
it can answer (``requests.py``, ``tier: rule``), a mechanical change that is safe and certain, proposed like any
block's (a propose line, checked on a scratch copy, judged, written as the judge's policy allows):

- **a kind's chain** (``outflow-not-chained``, ``inflow-not-chained``, ``state-stock-without-inflow``,
  ``move-without-flow``, ``state-stocks-disconnected``): the chain's exact rewiring (``spec/chains.py``'s fixes, as
  ``structural.chain_edits`` writes them); the whole kind at once when its stocks are in pieces;
- **the structure tests** (``rate-driven-by-rate``, ``stock-without-outflow``, ``units-mismatch``,
  ``auxiliary-without-causes``, ``equation-sign``, ``extreme-conditions``): ergostat's own fixes (``structural.py``);
- **a stock's unit** (``no-unit``), carried along its flows from the stocks they join, or, for a stock that counts the
  items of a kind, that kind's name in the plural, when exactly one unit is said;
- **an equation of standard form** (``no-equation``) for a flow between two stocks that names no other cause: a
  first-order outflow, ``stock.S / time-in-S`` (each outflow its own time when there are several), the time from Little's
  law on the record (the stock's mean level over the flow's mean rate), marked ``estimate: true``;
- **an event type named the kind's way** (``event-names-mixed``): ``KIND.verb-past``, the verb the state it moves the
  item to when that reads as a past tense; the old name kept (``formerly:``), so the record's events still fold, and
  each program in the project that writes it as a literal written with the new one;
- **a queue's goal held at 0** (``queue-goal-tolerance``) and **a process nobody identified taken out**
  (``process-not-identified``): control changes, which wait for the owner whatever the policy.

Each proposal cites the request's finding and every other finding it answers (worked out on the model it leaves), so
the requests it answers are all marked proposed. What it cannot answer is said, and the request goes to the ai tier."""

from __future__ import annotations

import re
from pathlib import Path

from ..spec import craft
from ..spec.ir import Spec
from . import observe as ob
from . import structural as stc
from . import trial as tr
from . import yamledit as ye
from .requests import evidence_of

CHAIN = set(stc.CHAIN_CODES) - {"loops-not-connected"}
STRUCTURE = {"rate-driven-by-rate", "stock-without-outflow", "units-mismatch", "auxiliary-without-causes",
             "equation-sign", "extreme-conditions"}
CONFIDENCE = 0.9


class NoFix(Exception):
    """The rule tier has no change it is sure of: why."""


def _raw(kind: str, title: str, parts: list[str], edits: list[ye.Edit], r: dict, says: str, **more) -> dict:
    files = {}
    for e in edits:
        files.setdefault(e.file, []).append(e)
    merged = [ye.merge(xs).as_dict() for xs in files.values()]
    return {"kind": kind, "title": title[:200], "parts": parts, "edit": {"files": merged},
            "reasons": [{"says": says, "evidence": evidence_of(r)}], "confidence": CONFIDENCE, **more}


# ---- each rule

def chain(spec: Spec, r: dict, found: list) -> dict:
    hit = next((x for x in found if x.code == r["code"] and x.about == r["about"]), None)
    if hit is None or not hit.fixes:
        raise NoFix(f"{r['code']} on {r['about']}: the chain names no change for it now")
    try:
        edits = stc.chain_edits(spec, hit.fixes)
    except (KeyError, ye.EditError) as e:
        raise NoFix(str(e)) from None
    parts = sorted({f"stock.{s}" for f in hit.fixes for s in (f.source, f.target, f.stock) if s} |
                   {f"flow.{f.flow}" for f in hit.fixes if f.op == "retarget"})
    whole = r["code"] == "state-stocks-disconnected"
    kind = hit.message.split(":", 1)[0].removeprefix("items ") if whole else ""
    title = f"Chain the state stocks of {kind}" if whole else "; ".join(f.said() for f in hit.fixes)
    return _raw("structure", title, parts, edits, r, hit.message.split(". ")[0][:300])


def structure(p, spec: Spec, r: dict, ctx_out: list[dict]) -> dict:
    hit = next((x for x in ctx_out if x.get("code") == r["code"] and x.get("target") == r["about"]), None)
    if hit is None:
        raise NoFix(f"{r['code']} on {r['about']}: ergostat's own fix for it cannot be made here")
    edits = [ye.Edit.from_dict({k: v for k, v in d.items() if k != "diff"}) for d in hit["edit"]["files"]]
    return _raw("structure", hit["title"], hit.get("parts") or [r["about"]], edits, r, hit.get("reason", r["says"])[:300])


def unit(spec: Spec, r: dict) -> dict:
    name = r["about"].split(".", 1)[1]
    st = spec.stocks.get(name)
    if st is None:
        raise NoFix(f"no stock {name}")
    said = set()
    for f in spec.flows_of(name):
        for end in (f.source, f.target):
            u = (spec.stocks[end].unit or "").strip() if end and end != name and end in spec.stocks else ""
            if u:
                said.add(u)
        if f.unit and "/" in f.unit:
            said.add(f.unit.split("/")[0].strip())
    counts = {it["kind"] for s in st.sensors.values() if (it := s.items) and it.get("measure", "count") == "count"}
    measure = {it.get("measure") for s in st.sensors.values() if (it := s.items)}
    if not said and len(counts) == 1:
        said.add(craft.plural(next(iter(counts)).split(".")[-1]))
    if not said and measure & {"oldest", "age"}:
        said.add("hours")
    if len(said) != 1:
        raise NoFix(f"stock {name}: " + ("nothing says its unit (no stock it joins has one, and it counts no one kind)"
                                         if not said else f"its neighbours say {', '.join(sorted(said))}"))
    u = next(iter(said))
    from .improve import _set
    edits = _set(spec, {"part": f"stock.{name}", "set": {"unit": u}})
    how = "the kind it counts" if counts and u == craft.plural(next(iter(counts)).split(".")[-1]) else "the stocks its flows join"
    return _raw("unit", f"{name}: unit {u}", [f"stock.{name}"], edits, r, f"stock {name} has no unit; {how} say {u}")


def equation(p, spec: Spec, r: dict, data: ob.Data | None) -> dict:
    name = r["about"].split(".", 1)[1]
    f = spec.flows.get(name)
    if f is None or not f.source or f.equation is not None:
        raise NoFix(f"flow {name}: not a flow from a stock with no equation")
    st = spec.stocks.get(f.source)
    if st is None or st.cumulative or f.two_way:
        raise NoFix(f"flow {name}: its source is a running total, or it runs both ways: no standard form fits")
    others = [str(c) for c in f.driven_by if not (c.kind == "stock" and c.name == f.source)]
    if others:
        raise NoFix(f"flow {name}: it is driven by {', '.join(others)} too, so its equation needs judgement")
    outs = [g for g in spec.flows_of(f.source) if g.source == f.source]
    taken = set(spec.parameters) | set(spec.stocks) | set(spec.flows) | set(spec.auxiliaries)
    base = f"time-in-{f.source}" if len(outs) == 1 else f"time-to-{name}"
    tn = stc._free(base, taken)
    hours, how = 1.0, "a first guess (no record of both yet), refitted as the record grows"
    if data is not None:
        lv = [v for v in data.values.get(f"stock.{f.source}") or [] if v is not None]
        rt = [v for v in data.values.get(f"flow.{name}") or [] if v is not None]
        if len(lv) >= 5 and len(rt) >= 5 and sum(rt) > 0:
            m, q = sum(lv) / len(lv), sum(rt) / len(rt)
            if m > 0 and q > 0:
                hours = m / q
                how = f"Little's law on the record: its mean level {ye.number(m)} over what left an hour, {ye.number(q)}"
    hours = min(max(hours, 1 / 3600.0), 24 * 30.0)
    from .improve import _set
    eq_text = f"stock.{f.source} / {tn}"
    sets = {"equation": eq_text}
    if not any(c.kind == "stock" and c.name == f.source for c in f.driven_by):
        sets["driven-by"] = f"+stock.{f.source}"
    edits = _set(spec, {"part": f"flow.{name}", "set": sets})
    path = Path((f.defined or f.where).file)
    edits.append(ye.add_entries(path, "parameters", [[f"  {tn}:", f"    value: {ye.duration(hours)}",
                                                      f"    description: how long things stay in {f.source} before {name} takes them",
                                                      "    estimate: true          # refitted as the record grows",
                                                      f"    inferred: {stc.PENDING}"]]))
    return _raw("equation", f"{name} = {eq_text}", [f"flow.{name}", f"stock.{f.source}"], edits, r,
                f"flow {name} has no equation: a first-order outflow takes what is in {f.source} over the time things stay "
                f"there ({how})")


def events(p, spec: Spec, r: dict) -> dict:
    kind = r["about"].split(".", 1)[1]
    k = spec.items.get(kind)
    if k is None:
        raise NoFix(f"no item kind {kind}")
    if getattr(getattr(k, "where", None), "template", None):
        raise NoFix(f"items {kind} is made by a template")
    renames = {}
    for ev, st, new in craft.event_forms(spec, kind):
        if new == ev or not craft.past(new.split(".")[-1]):
            continue
        if new in k.on and k.on[new] != st or new in renames.values():
            continue
        renames[ev] = new
    if not renames:
        raise NoFix(f"items {kind}: no event's state reads as a past tense to name it by: its names need judgement")
    path = Path(k.where.file)
    ls = ye.lines_of(path)
    at = next((i + 1 for i in range(min(k.where.line, len(ls)) - 1, -1, -1) if re.match(rf"^\s*{re.escape(kind)}\s*:", ls[i])), None)
    if at is None:
        raise NoFix(f"items {kind}: its name is not found in {path.name}")
    end, _ = ye.children(ls, at)
    edits = []
    for i in range(at, end):
        line = ls[i]
        for old, new in renames.items():
            line = re.sub(rf"(?<![\w.-]){re.escape(old)}(?=\s*:)", new, line)
        if line != ls[i]:
            edits.append(ye.Edit(str(path), [ye.Hunk(i + 1, [ls[i]], [line])]))
    if not edits:
        raise NoFix(f"items {kind}: its on: is not written a line an event (write it out a key a line first)")
    was = dict(getattr(k, "formerly", {}) or {})
    was.update(renames)
    from .improve import _value
    edits.append(ye.set_key(path, at, "formerly", _value(was)))
    edits += _code(spec, renames)
    said = ", ".join(f"{a} → {b}" for a, b in renames.items())
    return _raw("rename", f"Event types of {kind} named {kind}.verb-past: {said}", [f"items.{kind}"], _one_per_line(edits), r,
                f"items {kind}: its event types are in mixed forms; each named for the kind and the state it moves the item "
                f"to ({said}), the old names kept so the record's events still fold")


CODE = (".py", ".sh", ".js", ".ts", ".rb", ".pl", ".md", ".yaml", ".yml", ".json", ".toml")


def _code(spec: Spec, renames: dict[str, str]) -> list[ye.Edit]:
    """Each quoted literal of an old event type in the project's own text files (not the model's, not hidden ones),
    written with the new name."""
    root = Path(spec.root)
    model = {Path(f).resolve() for f in spec.files}
    out = []
    for f in sorted(root.rglob("*")):
        rel = f.relative_to(root)
        if not f.is_file() or f.suffix not in CODE or any(x.startswith(".") for x in rel.parts) or f.resolve() in model:
            continue
        try:
            ls = f.read_text(encoding="utf-8").split("\n")
        except (OSError, UnicodeDecodeError):
            continue
        hunks = []
        for i, line in enumerate(ls):
            new = line
            for old, nm in renames.items():
                new = re.sub(rf"([\"']){re.escape(old)}\1", lambda m, nm=nm: f"{m.group(1)}{nm}{m.group(1)}", new)
            if new != line:
                hunks.append(ye.Hunk(i + 1, [line], [new]))
        if hunks:
            out.append(ye.Edit(str(f), hunks))
    return out


def _one_per_line(edits: list[ye.Edit]) -> list[ye.Edit]:
    return edits


def goal_queue(spec: Spec, r: dict) -> dict:
    name = r["about"].split(".", 1)[1]
    g = spec.goals.get(name)
    if g is None:
        raise NoFix(f"no goal {name}")
    from .improve import _set
    sets = {"tolerance": 0}
    if g.hold.op in ("<=", "<") and g.hold.value > 0:
        sets["hold"] = "<= 0"
    edits = _set(spec, {"part": f"goal.{name}", "set": sets})
    return _raw("control", f"{name}: held at 0, tolerance 0", [f"goal.{name}"], edits, r,
                f"goal {name} holds a queue its block takes items from: held at \"<= 0\" with tolerance 0, items are worked "
                f"as they come")


def process(spec: Spec, r: dict) -> dict:
    name = r["about"].split(".", 1)[1]
    g = spec.goals.get(name)
    if g is None or g.where is None:
        raise NoFix(f"no goal {name}")
    path = Path(g.where.file)
    at = ye.name_line(path, g.where.line, name)
    e = ye.remove_key(path, at, "process")
    if e is None:
        raise NoFix(f"goal {name}: its process: is not written a key a line")
    return _raw("control", f"{name}: the process nobody identified taken out", [f"goal.{name}"], [e], r,
                f"goal {name}'s process was not identified from the record: drawn as not identified until it is")


def measurable(p, spec: Spec, r: dict, data, requests: list[dict]) -> dict:
    """The fit cannot be worked out because no flow moves the stocks the sensors read: a first-order outflow for the
    first outflow of a read stock that has no equation and no sensor (one a run, so each is judged alone)."""
    read = [n for n, st in spec.stocks.items() if st.sensors]
    asked = {r2["about"] for r2 in requests if r2["code"] == "no-equation"}     # those have their own request
    flows = [f for n in read for f in spec.flows_of(n) if f.source == n and f"flow.{f.name}" not in asked]
    for f in sorted(flows, key=lambda f: f.target is not None):
        if f.equation is None and not f.sensors and f.rate is None and not f.two_way:
            try:
                raw = equation(p, spec, {**r, "about": f"flow.{f.name}"}, data)
            except NoFix:
                continue
            raw["reasons"] = [{"says": f"the fit cannot be worked out ({r['says'][:160]}); {f.name} moving {f.source} by "
                                       f"an equation makes it measurable", "evidence": evidence_of(r)}]
            return raw
    raise NoFix("no outflow of a stock a sensor reads is left without an equation or a sensor: the fit needs the owner "
                "(a sensor on a stock, or more record)")


# ---- all of them

def _answered(p, spec: Spec, raw: dict, requests: list[dict]) -> list[dict]:
    """The other requests a change answers: check no longer finds them in the model it leaves."""
    from ..spec.findings import find
    try:
        edits = [ye.Edit.from_dict({k: v for k, v in d.items() if k != "diff"}) for d in raw["edit"]["files"]]
        after, errors = tr.compiled(p.model.path, ye.apply_together(edits))
    except (ye.EditError, tr.TrialError, KeyError):
        return []
    if errors:
        return []
    left = {f"{x.code}@{x.about}" for x in find(after, extremes=False)}
    return [r for r in requests if r.get('source') not in ('coherence', 'fit') and f"{r['code']}@{r['about']}" not in left]


def propose(p, requests: list[dict], most: int = 8, data: ob.Data | None = None) -> tuple[list[tuple[dict, dict]], list[tuple[dict, str]]]:
    """What the rule tier proposes for these requests (each ``(request, propose)``), at most ``most``, and the ones it
    has no change for (``(request, why)``). A proposal that answers several requests cites them all, and is made once."""
    spec: Spec = p.model.spec
    from ..spec import chains as ch
    found = ch.analyse(spec) if any(r["code"] in CHAIN for r in requests) else []
    ctx_out: list[dict] = []
    if any(r["code"] in STRUCTURE for r in requests):
        if data is None:
            try:
                data = ob.measured(p, ob.reference(p))
            except Exception:
                data = None
        c = stc.Ctx(p, spec, data)
        stc.from_findings(c)
        ctx_out = c.out
    if data is None and any(r["code"] == "no-equation" for r in requests):
        try:
            data = ob.measured(p, ob.reference(p))
        except Exception:
            data = None
    order = sorted(requests, key=lambda r: (r["code"] != "state-stocks-disconnected", r["code"] not in CHAIN,
                                            r.get("raised") or 0.0))
    made, none, covered = [], [], set()
    for r in order:
        if r["id"] in covered:
            continue
        if len(made) >= most:
            break
        code = r["code"]
        try:
            if code in CHAIN:
                raw = chain(spec, r, found)
            elif code in STRUCTURE:
                raw = structure(p, spec, r, ctx_out)
            elif code == "no-unit":
                raw = unit(spec, r)
            elif code == "no-equation":
                raw = equation(p, spec, r, data)
            elif code == "event-names-mixed":
                raw = events(p, spec, r)
            elif code == "queue-goal-tolerance":
                raw = goal_queue(spec, r)
            elif code == "process-not-identified":
                raw = process(spec, r)
            elif code == "fit-unknown":
                if data is None:
                    try:
                        data = ob.measured(p, ob.reference(p))
                    except Exception:
                        data = None
                raw = measurable(p, spec, r, data, requests)
            else:
                raise NoFix(f"{code}: the rule tier has no rule for it")
        except NoFix as e:
            none.append((r, str(e)))
            continue
        except Exception as e:                      # a rule that cannot be applied here says why, and the next goes on
            none.append((r, f"{type(e).__name__}: {e}"))
            continue
        more = [x for x in _answered(p, spec, raw, requests) if x["id"] != r["id"]]
        for x in more:
            raw["reasons"].append({"says": f"it also answers {x['code']} on {x['about']}", "evidence": evidence_of(x)})
            covered.add(x["id"])
        covered.add(r["id"])
        made.append((r, raw))
    return made, none
