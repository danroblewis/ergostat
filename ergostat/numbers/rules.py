"""The rule tier of the modelling subsystem (SPEC §12e): the cheapest tier, a program on the rule rung. For each request
it can answer (``requests.py``, ``tier: rule``), a mechanical change that is safe and certain, proposed like any
block's (checked on a scratch copy, judged, written as the judge's policy allows):

- **a stock's unit** (``no-unit``), carried along its flows from the stocks they join, or, for a stock that counts the
  items of a kind, that kind's name in the plural, when exactly one unit is said;
- **a queue's goal held at 0** (``queue-goal-tolerance``) and **a process nobody identified taken out**
  (``process-not-identified``): control changes, which wait for the owner whatever the policy.

A kind's chain and the structure tests are answered by ergostat's own finders (``structural.py``), whose changes say
``rewires``. Each proposal cites the request's finding and every other finding it answers (worked out on the model it
leaves), so the requests it answers are all marked proposed. What it cannot answer is said, and the request goes to the
ai tier."""

from __future__ import annotations

from pathlib import Path

from ..spec import craft
from ..spec.ir import Spec
from . import trial as tr
from . import yamledit as ye
from .requests import evidence_of

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


def propose(p, requests: list[dict], most: int = 8) -> tuple[list[tuple[dict, dict]], list[tuple[dict, str]]]:
    """What the rule tier proposes for these requests (each ``(request, propose)``), at most ``most``, and the ones it
    has no change for (``(request, why)``). A proposal that answers several requests cites them all, and is made once."""
    spec: Spec = p.model.spec
    rules = {"no-unit": unit, "queue-goal-tolerance": goal_queue, "process-not-identified": process}
    made, none, covered = [], [], set()
    for r in sorted(requests, key=lambda r: r.get("raised") or 0.0):
        if r["id"] in covered:
            continue
        if len(made) >= most:
            break
        try:
            rule = rules.get(r["code"])
            if rule is None:
                raise NoFix(f"{r['code']}: the rule tier has no rule for it")
            raw = rule(spec, r)
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
