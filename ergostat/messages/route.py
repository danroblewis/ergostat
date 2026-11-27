"""Routing a message to the work it concerns (SPEC §12h).

In order, the first that finds anything:

1. **explicit**: what the sender said it is about (``--about``): an item (``review/2041``) or a part (``block.developer``,
   ``stock.inbox``, or a part's bare name);
2. **mention**: item ids and part names in its words (``hypothesis/3``, ``stock.queue``, a block's name as a word);
3. **classifier**: the block ``messages: {classifier: NAME}`` names (an ``ai`` block on a cheap model; it answers with
   ``route`` lines), else ergostat's **stand-in**, which scores the open items by the words they share with the
   message (their kind's name, the number in their id, the words of their shown fields) and takes the best.

What it matched becomes **targets**: each open item it concerns, with the block runs working on it now (a run is
working on an item when an event about the item was caused by the run, or its command named the item), and each block
it names, with its run when one is running. An item finished already is handled by the ``finished:`` policy
(``deliver.finished``). A message that matched nothing, or only parts nothing acts on, is **unrouted**."""

from __future__ import annotations

import re
import time

from ..spec.ir import ACTION, CLAIM, MESSAGE, MODEL_CHANGE, WORKSPACE, Spec
from . import record

PART = re.compile(r"\b(stock|flow|block|goal|auxiliary)\.([a-z][a-z0-9-]*)\b")
ID = re.compile(r"(?<![\w/.-])([a-z][a-z0-9_-]*(?:/[A-Za-z0-9_.:-]*[A-Za-z0-9])+)")
WORD = re.compile(r"[a-z0-9][a-z0-9'\u2019-]*")
STOP = set("""a an and are as at be been but by can could did do does done for from had has have how i if in into is it
its it's just me my no not now of on one or our please so some than that the their them then there these they this to too
up us was we were what when where which who why will with would you your can't don't won't first next later wait again
check look still also only before after more less want need needs""".split())
OWN_KINDS = (MESSAGE, CLAIM, MODEL_CHANGE, ACTION, WORKSPACE)
MOST = 3                      # the most items one message is routed to by the stand-in
RUN_FOR = 86400.0             # a run started longer ago than this (or its timeout) and never ended is not running


# ---- the work: items, and the runs working on them

def route_done_states(spec: Spec, kind, items=None, left=None, reached=None) -> set[str]:
    """The states in which a message about an item goes to the ``finished:`` policy, not to the work: as ``messages:
    {done:}`` says, else its last state and each state after the first that no item has left while some item reached
    a state written after it. Not ``finished.finish_of`` on purpose (SPEC §5a): a state items rest in while no item
    has gone on is waiting, not finished (a review briefed, waiting for its reviewer). What items left and reached:
    from ``items``' moves, unless given."""
    if kind.name in spec.messages.done:
        return set(spec.messages.done[kind.name])
    if not kind.states:
        return set()
    if left is None:
        left = {mv["from"] for it in items or [] for mv in it.moves if mv["from"]}
    if reached is None:
        reached = {mv["to"] for it in items or [] for mv in it.moves}
    out = {kind.states[-1]}
    for i, s in enumerate(kind.states[1:-1], 1):
        if s not in left and reached & set(kind.states[i + 1:]):
            out.add(s)
    return out


def work_items(p, spec: Spec, text: str | None = None, ids=None) -> list[dict]:
    """The items of the model's own projections a message can concern: its id, projection, state, fields, and whether it is
    finished. Every open one; a finished one only when ``text`` names it (its id, or the number in its id) or it is
    among ``ids``. (Every item at all when ``text`` and ``ids`` are both None and there is no item index.) Read from
    the item index: a record of half a million finished items reads only the few it names."""
    from ..spec.itemindex import index_for
    from ..spec.items import asks_transcript
    if index_for(p.events, spec, False) is None:
        return _every_work_item(p, spec)
    named = set(ids or ()) | set(ID.findall(text or ""))
    nums = set(re.findall(r"\b\d{2,}\b", text or ""))
    out, seen = [], {}

    def add(it, k, done) -> None:
        fin = bool(it.state and it.state in done)
        if it.id in seen:              # an id several projections see: finished only when finished in each of them
            seen[it.id]["finished"] = seen[it.id]["finished"] and fin
            return
        seen[it.id] = {"id": it.id, "projection": k.name, "state": it.state, "fields": it.fields, "last": it.last,
                       "entered": it.entered, "finished": fin}
        out.append(seen[it.id])
    for name, k in spec.items.items():
        if name in OWN_KINDS:
            continue
        ix = index_for(p.events, spec, asks_transcript([k]))
        with ix.lock:
            done = route_done_states(spec, k, left=ix.left(name), reached=ix.reached(name))
            still = None if not k.states else [s for s in k.states if s not in done] + [""]
            for it in ix.items(name, states=still, moves=False):
                add(it, k, done)
            for it in ix.items(name, ids=[i for i in named if k.matches(i)], moves=False):
                add(it, k, done)
            for n in nums:
                for it in ix.items(name, has=n, moves=False):
                    tail = it.id.rsplit("/", 1)[-1]
                    if tail == n or n in re.findall(r"\d+", tail):
                        add(it, k, done)
    return out


def _every_work_item(p, spec: Spec) -> list[dict]:
    from ..spec import items as its
    out: dict[str, dict] = {}
    for name, k in spec.items.items():
        if name in OWN_KINDS:
            continue
        got = its.project(p.events, spec, name)
        done = route_done_states(spec, k, got)
        for it in got:
            fin = bool(it.state and it.state in done)
            if it.id in out:           # (as ``work_items``: finished only when finished in each projection)
                out[it.id]["finished"] = out[it.id]["finished"] and fin
                continue
            out[it.id] = {"id": it.id, "projection": name, "state": it.state, "fields": it.fields, "last": it.last,
                          "entered": it.entered, "finished": fin}
    return list(out.values())


def running(p, spec: Spec, now: float | None = None) -> list[dict]:
    """The block runs going now (``agent.started`` with no ``agent.ran`` or ``agent.failed`` after it, within its
    timeout): each with its block, the items it is working on, and its session when it runs one. A run of a block
    the model no longer has is still going until it ends: a model change lets it finish (SPEC §9.1)."""
    now = time.time() if now is None else now
    started = p.events.query(n=500, type="agent.started", since=now - RUN_FOR)
    if not started:
        return []
    ended = {e["causedby"] for e in p.events.query(n=None, type="agent.ran,agent.failed", since=started[0]["time"])}
    out = []
    for s in started:
        b = spec.blocks.get(s.get("item") or "")
        if s["id"] in ended or (b is not None and not b.machine) or not s.get("item") or \
                now - s["time"] > ((b.timeout if b else (s.get("data") or {}).get("timeout")) or RUN_FOR) + 60:
            continue
        r = {"run": s["id"], "block": s["item"], "started": s["time"], "items": [], "session": None, "session_id": None,
             "live": False}
        cmd = (s.get("data") or {}).get("command") or {}
        if isinstance(cmd, dict) and isinstance(cmd.get("item"), str):
            r["items"].append(cmd["item"])
        leased = (s.get("data") or {}).get("item")              # the item it holds a lease on (SPEC §9.5)
        if isinstance(leased, str) and leased not in r["items"]:
            r["items"].append(leased)
        for e in p.events.caused_by(s["id"]):
            it = e.get("item") or ""
            if "/" not in it or it.startswith("ergostat."):
                continue
            d = e.get("data") or {}
            if d.get("session_id"):                       # the run's own session, not the work it does
                r["session"], r["session_id"], r["live"] = it, d["session_id"], bool(d.get("live"))
            elif it not in r["items"]:
                r["items"].append(it)
        out.append(r)
    return out


def acting_on(spec: Spec, ref: str) -> list[str]:
    """The machine blocks that act on a part: a block itself; a goal's actuators; the block setting a flow; the blocks
    setting a stock's flows."""
    kind, _, name = ref.partition(".")
    if kind == "block":
        b = spec.blocks.get(name)
        return [b.name] if b and b.machine else []
    if kind == "goal" and name in spec.goals:
        try:
            return [x for x in spec.loop(name).actuators if spec.blocks[x].machine]
        except Exception:
            return []
    flows = []
    if kind == "flow" and name in spec.flows:
        flows = [name]
    elif kind == "stock" and name in spec.stocks:
        flows = [f.name for f in spec.flows.values() if name in (f.source, f.target)]
    return [b.name for b in spec.blocks.values() if b.machine and any(t.kind == "flow" and t.name in flows
                                                                       for t in b.targets())]


def part_of(spec: Spec, raw: str) -> str | None:
    """A part, written as a reference (``block.developer``) or by its bare name (blocks first)."""
    m = PART.fullmatch(raw)
    if m:
        table = {"stock": spec.stocks, "flow": spec.flows, "block": spec.blocks, "goal": spec.goals,
                 "auxiliary": spec.auxiliaries}[m.group(1)]
        return raw if m.group(2) in table else None
    for kind, table in (("block", spec.blocks), ("goal", spec.goals), ("stock", spec.stocks), ("flow", spec.flows),
                        ("auxiliary", spec.auxiliaries)):
        if raw in table:
            return f"{kind}.{raw}"
    return None


# ---- matching

def explicit(spec: Spec, about: list[str], items: dict[str, dict]) -> tuple[list[str], list[str], list[str]]:
    """What the sender named: (items, parts, what could not be read)."""
    its, parts, bad = [], [], []
    for a in about:
        if a in items or ("/" in a and any(k.matches(a) for k in spec.items.values())):
            its.append(a)
        elif part_of(spec, a):
            parts.append(part_of(spec, a))
        else:
            bad.append(a)
    return its, parts, bad


def mentions(spec: Spec, text: str, items: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Item ids and part names in the words: (items, parts)."""
    its = [m for m in dict.fromkeys(ID.findall(text)) if m in items]
    parts = [r for r in dict.fromkeys(f"{a}.{b}" for a, b in PART.findall(text)) if part_of(spec, r)]
    low = text.lower()
    for b in spec.blocks.values():                    # a machine block's name, as a word ("the developer")
        if b.machine and not b.name.startswith("keep-") and re.search(rf"(?<![\w.-]){re.escape(b.name)}(?![\w-])", low):
            if f"block.{b.name}" not in parts:
                parts.append(f"block.{b.name}")
    return its, parts


def words_of(text: str) -> set[str]:
    """Its words, lowercased, a possessive's "'s" left off (Ben's: ben)."""
    return {w.removesuffix("'s").removesuffix("\u2019s").strip("'-") for w in WORD.findall(text.lower())}


def _words(v) -> set[str]:
    if isinstance(v, str):
        if v.startswith("file:"):
            return set()
        return words_of(v) - STOP
    if isinstance(v, list):
        return set().union(*(_words(x) for x in v[:20])) if v else set()
    return set()


def standin(spec: Spec, text: str, items: list[dict], runs: list[dict]) -> tuple[list[str], str]:
    """ergostat's free classifier: the open items scored by the words they share with the message. Their kind's name
    (or its plural, or each of its words) +2; the number in their id +3; each word of their shown fields (and title)
    +1, at most 3, other projections' names aside (a note that says "review" is not a review). Finished items only when
    their number is said. The best scores of 2 or more win, open items first, then those being worked on now, then
    the newest; at most ``MOST``. Returns the items and why."""
    words = words_of(text)
    nums = set(re.findall(r"\b\d{2,}\b", text))
    busy = {i for r in runs for i in r["items"]}
    kind_words = {w for k in spec.items for w in (k, k + "s", *k.split("-"))}   # a projection's name counts for its own items
    scored = []
    for it in items:
        if it["projection"] in OWN_KINDS:
            continue
        k = spec.items[it["projection"]]
        tail = it["id"].rsplit("/", 1)[-1]
        numbered = tail in nums or any(n in re.findall(r"\d+", tail) for n in nums)
        if it["finished"] and not numbered:             # finished work only when its number is said
            continue
        score, why = 0, []
        names = {k.name, k.name + "s", *k.name.split("-")} - STOP
        if names & words:
            score += 2
            why.append(f"its projection, {k.name}")
        if numbered:
            score += 3
            why.append(f"its number, {tail}")
        shown = set()
        for f in [*k.show, "title"]:
            shown |= _words(it["fields"].get(f))
        common = sorted((shown & words) - names - kind_words)[:3]
        if common:
            score += len(common)
            why.append("the words " + ", ".join(common))
        if score >= 2:
            scored.append((score, not it["finished"], it["id"] in busy, it["last"], it["id"], why))
    if not scored:
        return [], "no open item shares its words (its projection's name, its number, its fields)"
    scored.sort(reverse=True)
    best = scored[0][0]
    top = [x for x in scored if x[0] == best][:MOST]
    return [x[4] for x in top], "; ".join(f"{x[4]}: {', '.join(x[5])}" for x in top)


# ---- targets

def targets(p, spec: Spec, its: list[str], parts: list[str], items: dict[str, dict], runs: list[dict]) -> tuple[list, list]:
    """What a message goes to: (targets, the finished items it is about). An open item: with each run working on it
    now (and that run's session); a part: each block acting on it, with its run when one is running."""
    out, finished = [], []
    for i in its:
        it = items.get(i)
        if it is not None and it["finished"]:
            finished.append(i)
            continue
        on = [r for r in runs if i in r["items"] or r["session"] == i]   # the work on it, or the session it is
        if not on:
            out.append({"item": i})
        for r in on:
            out.append({"item": i, "block": r["block"], "run": r["run"],
                        **({"session": r["session"], "session_id": r["session_id"], "live": r["live"]} if r["session"] else {})})
    for ref in parts:
        blocks = acting_on(spec, ref)
        for b in blocks:
            on = [r for r in runs if r["block"] == b]
            if not on:
                out.append({"part": ref, "block": b})
            for r in on:
                out.append({"part": ref, "block": b, "run": r["run"],
                            **({"session": r["session"], "session_id": r["session_id"], "live": r["live"]} if r["session"] else {})})
    return out, finished


def classify(p, spec: Spec, msg: dict, items: list[dict], runs: list[dict]) -> tuple[list[str], list[str], str, str]:
    """The classifier the model names, else the stand-in: (items, parts, how, why)."""
    name = spec.messages.classifier
    if name:
        from . import classifier
        got = classifier.ask(p, spec, name, msg, items, runs)
        if got is not None:
            return got
    its, why = standin(spec, msg["text"], items, runs)
    return its, [], "classifier:standin", why


def route(p, spec: Spec, mid: str, about=None, by: str = "ergostat", now: float | None = None,
          finished_policy: str | None = None) -> dict:
    """Route a message (again, with ``about``: the owner routing it by hand). Records ``routed`` or ``unrouted``, and,
    for finished work, what its policy does (``finished_policy`` in place of the model's). Returns the message,
    folded."""
    from . import deliver
    msg = record.get(p, mid)
    if msg is None:
        raise record.MessageError(f"no message {mid!r} (ergostat messages lists them)")
    mid = msg["id"]
    named = record.about_list(about) if about is not None else list(msg.get("about") or [])
    work = work_items(p, spec, text=msg.get("text") or "", ids=named)
    items = {x["id"]: x for x in work}
    runs = running(p, spec, now)
    its, parts, how, why = [], [], "", ""
    bad: list[str] = []
    if named:
        its, parts, bad = explicit(spec, named, items)
        how, why = "explicit", f"the sender named {', '.join(named)}"
    if not its and not parts:
        its, parts = mentions(spec, msg["text"], items)
        if its or parts:
            how, why = "mention", f"its words name {', '.join([*its, *parts])}"
    if not its and not parts and not named:
        its, parts, how, why = classify(p, spec, msg, work, runs)
    to, finished = targets(p, spec, its, parts, items, runs)
    if bad:
        why += f" (not an item or a part: {', '.join(bad)})"
    if not to and not finished:
        reason = (why + ": but nothing acts on " + ", ".join(parts)) if parts else (why or "nothing in it names work")
        record.step(p, mid, "unrouted", {"matched": how or "none", "routed_to": [], "why": reason,
                                         "outcome": f"unrouted: {reason}"}, by=by)
        return record.get(p, mid)
    to += [{"item": i, "finished": items[i]["state"]} for i in finished]
    names = ", ".join(dict.fromkeys(t.get("item") or t.get("block") or "" for t in to))
    record.step(p, mid, "routed", {"matched": how, "routed_to": to, "why": why,
                                   "outcome": f"routed to {names} ({how})"}, by=by)
    for i in finished:                                   # about finished work: a follow-up, a reopening, or the owner
        deliver.finished(p, spec, record.get(p, mid), items[i], by=by, policy=finished_policy)
    return record.get(p, mid)


def send(p, spec: Spec, text: str, by: str = "owner", about=None, via: str = "cli", reopen: bool = False) -> dict:
    """A message received and routed at once: what ``ergostat message``, MCP's ``message`` and the page do. With
    ``reopen``, each finished item it is about is reopened, whatever the policy."""
    ev = record.received(p, text, by=by, about=about, via=via)
    if spec is None:
        return record.get(p, ev["item"])
    return route(p, spec, ev["item"], finished_policy="reopen" if reopen else None)
