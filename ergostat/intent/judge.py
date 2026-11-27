"""The intent judge's pass (SPEC §12i): ergostat's own, on the judge block's clock (``type: judge``, ``judge: intent``).

Each pass, for every projection the judge holds (``projections:``), every item that entered its judged state (``at``) within
``within`` and has no verdict for that moment is judged: its brief made (``brief.py``), recorded as asked, judged by
the stand-in or, with ``model:``, by a model (``ai.py``), and the verdict recorded with its evidence, on a verdict item
and on the work (its field ``intent``). A verdict that the work is not done as meant (unmet, contradicted) is held:
by default it needs the owner's attention (and the work's own programs may read its ``intent``), and with ``held:
reopen`` the work is moved back, with the verdict as its reason. Then the verdicts that passed work the owner later
reopened, followed up or corrected are marked **missed**: the judge's own errors, counted."""

from __future__ import annotations

import time

from ..costs import budget
from ..spec import items as its
from ..spec.ir import INTENT_PORTS, IntentKind, Spec
from . import ai, brief, record, standin
from .outcomes import owner_found

WEEK = 7 * 86400.0


def entry(it, kk: IntentKind) -> dict | None:
    """Its latest move into the judged state."""
    ms = [m for m in it.moves if m.get("to") == kk.at]
    return ms[-1] if ms else None


def judge_one(p, spec: Spec, block: str, kk: IntentKind, it, at: dict, model: str | None, cap: float | None,
              held: str = "attention", instructions: str | None = None) -> dict:
    rung = "narrow-ai" if model else "program"          # a judge is a program; on a model, a narrow AI
    br = brief.build(p, spec, kk, it, at)
    permit, no = budget.ask(p, spec, block, cap or spec.budget.max_cost) if model and spec.budget else (None, None)
    if no:                          # (before it is asked: refused, the work stays due, SPEC §9.9)
        return {"refused": f"budget: {no}"}
    try:
        v = record.asked(p, block, br, "ai" if model else "standin", model, rung)
        t0 = time.time()
        if model:
            verdict, why, ev, spent = ai.judge(br, model, cap, instructions, permit)
        else:
            (verdict, why, ev), spent = standin.judge(br), {}
    finally:
        budget.done(permit, None)   # (closed by its call; else, raised before it, charged its reserve)
    got = record.given(p, v, verdict, why, ev, spent, time.time() - t0)
    if verdict in record.HELD and held == "reopen":
        record.reopen(p, spec, it.id, f"the intent judge ({block}): {why}", by=block, to=kk.reopen_to, verdict=v["id"])
    return got


def due(p, spec: Spec, block: str, now: float | None = None, only: str | None = None, again: bool = False) -> list:
    """(kind policy, item, entry) for each piece of work waiting for a verdict."""
    b = spec.blocks[block]
    pol = b.params["intent"]
    now = time.time() if now is None else now
    done = {(v["work"], v.get("entry_event")) for v in record.stored(p, since=now - max(pol.within, WEEK)).values()}
    out = []
    for kk in pol.kinds.values():
        if kk.kind not in spec.items:
            continue
        for it in its.project(p.events, spec, kk.kind):
            if only and it.id != only:
                continue
            e = entry(it, kk)
            if e is None or (not only and e["time"] < now - pol.within):
                continue
            if (it.id, e["event"]) in done and not again:
                continue
            out.append((kk, it, e))
    return sorted(out, key=lambda x: x[2]["time"])


def sweep_missed(p, spec: Spec, block: str, now: float | None = None) -> int:
    """Mark the verdicts that passed work the owner later found not done as meant."""
    now = time.time() if now is None else now
    pol = spec.blocks[block].params["intent"]
    n = 0
    vs = [v for v in record.stored(p, since=now - WEEK).values() if v["state"] in ("met", "unjudged")]
    for v in vs:
        kk = pol.kinds.get(v.get("projection") or "")
        if kk is None:
            continue
        it = its.one(p.events, spec, v["work"])
        if it is None:
            continue
        hit = owner_found(p, spec, it, kk, v.get("entered") or 0)
        if hit:
            record.missed(p, v, hit["how"], hit["event"])
            n += 1
    return n


def run(p, spec: Spec, by: str, model: str | None = None, only: str | None = None, again: bool = False,
        most: int = 20) -> dict:
    """One pass of the intent judge ``by``. ``model`` judges with that model in place of the block's; ``only`` judges
    that item (whenever it entered its judged state); ``again`` judges what has a verdict already."""
    b = spec.blocks[by]
    pol = b.params["intent"]
    model = model or pol.model
    out = {p_: 0 for p_ in INTENT_PORTS} | {"verdicts": [], "missed": 0, "cost_usd": 0.0}
    for kk, it, e in due(p, spec, by, only=only, again=again)[:most]:
        v = judge_one(p, spec, by, kk, it, e, model, pol.max_cost, pol.held, instructions_of(spec, b))
        if v.get("refused"):        # the pass stops; the next with room judges it
            out["refused"] = v["refused"]
            break
        out["judged"] += 1
        if v["verdict"] == "met":
            out["met"] += 1
        elif v["verdict"] in record.HELD:
            out["held"] += 1
        out["cost_usd"] += float(v.get("cost_usd") or 0)
        out["verdicts"].append({k: v.get(k) for k in ("id", "work", "verdict", "why", "cost_usd")})
    out["missed"] = sweep_missed(p, spec, by)
    return out


def instructions_of(spec: Spec, b) -> str | None:
    """The judge's instructions: ``prompt:`` is not a judge's key; a project improves them by replacing
    ``prompts/intent-judge.md`` in its own folder when it has one."""
    f = spec.root / "prompts" / "intent-judge.md"
    return f.read_text(encoding="utf-8") if f.is_file() else None


def lines(spec: Spec, block: str | None, got: dict) -> list[dict]:
    """What its block reports: what it moved on each port it has."""
    b = spec.blocks.get(block or "")
    if b is None:
        return []
    return [{"out": port, "moved": got[port]} for port in INTENT_PORTS if port in b.outputs]
