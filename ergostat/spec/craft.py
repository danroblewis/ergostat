"""The craft of a model (docs/MODELLING-WELL.md's review checklists): what makes each diagram look the way a
professional in its discipline would have drawn it, beyond being correct. ``check`` says each as a **note** (level
``note``): never an error, never counted with the findings, but work for the modelling subsystem like any finding
(``numbers/requests.py``), each with the part it is about and why.

- ``no-description``: a stock, flow, auxiliary, parameter, goal, block, item kind or agent with no description (the
  diagrams show nothing when a reader clicks it);
- ``no-unit``: a stock with no unit (its flows have none either, and the dimensional checks pass it by);
- ``no-equation``: a flow between two stocks with no equation nor declared rate (replayed, never projected);
- ``collector-undescribed``: a sensor that reads the outside (``run:``, ``query:``) with no description (the Blocks
  view titles the collector with its command);
- ``event-names-mixed``: an item kind whose events are not all ``KIND.verb-past``;
- ``queue-goal-tolerance``: a goal served by a block that takes the items its stock counts, with a tolerance (or a
  setpoint above 0) that lets items wait unseen, since the block runs only while the goal is off;
- ``schedule-removed``: a block with ``every:`` or ``cron:`` and a ``goal:``: the goal's implied controller commands
  it, so the clock never starts it (the engine's ``_plan``): it runs only while the goal is off;
- ``process-not-identified``: a goal whose ``process:`` has no ``identified:``, a claim nobody measured.

Parts a template made are left out: they are changed only through the instance's ``with:`` or the template."""

from __future__ import annotations

import re

from .ir import Spec
from .ir import template_made as _made

CODES = ("no-description", "no-unit", "no-equation", "collector-undescribed", "event-names-mixed",
         "queue-goal-tolerance", "schedule-removed", "process-not-identified")
IRREGULAR = {"done", "sent", "made", "taken", "begun", "written", "given", "run", "set", "put", "read", "seen", "found",
             "held", "kept", "left", "lost", "met", "paid", "sold", "told", "won", "built", "bought", "brought", "caught",
             "chosen", "drawn", "driven", "fallen", "frozen", "got", "gotten", "grown", "hidden", "known", "led", "lit",
             "meant", "overridden", "proven", "quit", "risen", "shown", "shut", "spent", "split", "spread", "stood",
             "struck", "stuck", "swept", "thought", "thrown", "withdrawn", "cut", "hit", "shed", "dealt", "ran", "went", "broke",
             "came", "gave", "took", "wrote", "rose", "fell", "sat", "spoke", "chose", "drove", "began", "grew", "knew"}




def _said(x) -> bool:
    return bool((getattr(x, "description", "") or "").strip())


def past(verb: str) -> bool:
    """A verb (the last word of an event type) in the past tense, as far as its spelling says."""
    return any(w.endswith("ed") or w in IRREGULAR or (w.endswith("en") and len(w) > 5) for w in verb.lower().split("-"))


def canonical(kind: str, event: str, state: str) -> str:
    """The event type a move into ``state`` reads best as: the kind, then the state (when it reads as a past tense),
    else the event's own verb made the kind's."""
    tail = event.split(".")[-1]
    verb = state if past(state) else tail
    return f"{kind}.{verb}"


def event_forms(spec: Spec, kind: str) -> list[tuple[str, str, str]]:
    """The events of a kind not written ``KIND.verb-past``: ``(event, state, the name it reads best as)``."""
    k = spec.items[kind]
    out = []
    for ev, st in k.on.items():
        head, _, tail = ev.rpartition(".")
        if ev in getattr(k, "formerly", {}):
            continue                                        # kept for the record's sake: renamed already
        if head == kind and past(tail):
            continue
        out.append((ev, st, canonical(kind, ev, st)))
    return out


def notes(spec: Spec, say) -> None:
    """Every craft note: ``say(code, message, where, about)``."""
    for _sec, kind, table in (("stocks", "stock", spec.stocks), ("flows", "flow", spec.flows),
                             ("auxiliaries", "auxiliary", spec.auxiliaries), ("parameters", "parameter", spec.parameters),
                             ("goals", "goal", spec.goals), ("blocks", "block", spec.blocks),
                             ("items", "items", {n: k for n, k in spec.items.items() if not n.startswith("ergostat.")}),
                             ("agents", "agent", spec.agents)):
        for n, x in table.items():
            if _made(x) or _said(x) or getattr(x, "implied", False):
                continue
            say("no-description", f"{kind} {n}: no description, so the diagrams show nothing when a reader clicks it: "
                f"one line a newcomer can read without the YAML, in the world's words"
                + (" (for a flow, what decides it)" if kind == "flow" else ""), getattr(x, "where", None), f"{kind}.{n}")
    for n, st in spec.stocks.items():
        if _made(st) or (st.unit or "").strip():
            continue
        say("no-unit", f"stock {n}: no unit. Give it the natural unit of what it counts (alerts, tickets, GB), never a "
            f"generic one: its flows take it per hour, and the dimensional checks then hold them to it", st.where,
            f"stock.{n}")
    for n, f in spec.flows.items():
        if _made(f) or not (f.source and f.target) or f.equation is not None or f.rate is not None:
            continue
        say("no-equation", f"flow {n}: from {f.source} to {f.target} with no equation, so it is only what its sensor "
            f"reads: it can be replayed, never projected or asked what if, and the loops through it have a sign but no "
            f"size. Write the rate as the decision rule (a first-order outflow: stock.{f.source} / time-in-{f.source})",
            f.where, f"flow.{n}")
    for table, kind in ((spec.stocks, "stock"), (spec.flows, "flow"), (spec.auxiliaries, "auxiliary")):
        for n, x in table.items():
            if _made(x):
                continue
            for s in x.sensors.values():
                if (s.commands or s.query) and not (s.description or "").strip():
                    say("collector-undescribed", f"{kind} {n}: its sensor {s.name} reads the outside "
                        f"({'a command' if s.run else 'a daemon' if s.daemon else 'a query'}) with no description, so the "
                        f"Blocks view titles the "
                        f"collector with its command: say what it reads in 40 characters or fewer", s.where or x.where,
                        f"{kind}.{n}")
    for kind, k in spec.items.items():
        if kind.startswith("ergostat.") or _made(k) or not k.on:
            continue
        odd = event_forms(spec, kind)
        if odd:
            said = ", ".join(f"{e} → {c}" for e, _, c in odd[:6]) + ("…" if len(odd) > 6 else "")
            say("event-names-mixed", f"items {kind}: {len(odd)} of its {len(k.on)} event types are not {kind}.verb-past "
                f"(the kind, then what happened): {said}", k.where, f"items.{kind}")
    for n, b in spec.blocks.items():
        by = [c.name for c in spec.commanders_of(n) if c.implied]
        if _made(b) or not (b.every or b.cron) or not b.machine or not by or b.takes or b.on:
            continue
        say("schedule-removed", f"block {n}: its {'every: ' + format(b.every, 'g') + 's' if b.every else 'cron:'} is "
            f"no schedule: its goal: {b.goal} puts {by[0]} in front of it, and the clock never starts a commanded block, "
            f"so it runs only while {b.goal} is off. To run it on its clock whatever the goal reads, read the goal "
            f"instead (in: goal.{b.goal})", b.where, f"block.{n}")
    for n, g in spec.goals.items():
        if _made(g):
            continue
        proc = g.process or {}
        if proc and not proc.get("identified"):
            said = ", ".join(f"{a}: {b:g}" for a, b in proc.items() if a in ("gain", "tau", "theta") and isinstance(b, int | float))
            say("process-not-identified", f"goal {n}: its process ({said or 'as written'}) "
                f"was not identified from the record (no identified:), so a control engineer takes a guess at its word. "
                f"Leave it out until ergostat identify (or a step test) gives it", g.where, f"goal.{n}")
        st = spec.stocks.get(g.of.name) if g.of.kind == "stock" else None
        if st is None:
            continue
        counted = _states_counted(st)
        takers = [b for b in spec.blocks.values() if b.takes and b.goal == n and counted.get(b.takes.kind, set()) &
                  set(b.takes.at)]
        if not takers:
            continue
        above = g.hold.op in ("<=", "<") and g.hold.value > 0
        if g.tolerance > 0 or above:
            why = (f"a tolerance of {g.tolerance:g}" if g.tolerance > 0 else "") + \
                (" and " if g.tolerance > 0 and above else "") + (f"a setpoint of {g.hold.value:g}" if above else "")
            say("queue-goal-tolerance", f"goal {n}: {', '.join(b.name for b in takers)} take{'s' if len(takers) == 1 else ''} "
                f"the items {st.name} counts and run{'s' if len(takers) == 1 else ''} only while the goal is off, so with "
                f"{why} items wait unseen before anyone looks. Hold a queue at \"<= 0\" with tolerance: 0; a tolerance "
                f"belongs on a level", g.where, f"goal.{n}")


def _states_counted(st) -> dict[str, set[str]]:
    """The item kinds and states a stock's sensors count (``items: K, state: S``, a list of states too)."""
    out: dict[str, set[str]] = {}
    for s in st.sensors.values():
        it = s.items or {}
        if it.get("kind") and it.get("state") and it.get("measure", "count") == "count":
            states = it["state"] if isinstance(it["state"], list) else [it["state"]]
            out.setdefault(str(it["kind"]), set()).update(str(x) for x in states)
    return out


def plural(word: str) -> str:
    """A kind's name as the unit of what a stock of it counts: alert → alerts, inquiry → inquiries."""
    w = word.strip()
    if not w:
        return w
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", w):
        return w + "es"
    return w + "s"
