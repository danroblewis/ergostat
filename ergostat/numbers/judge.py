"""The judge of candidate changes to the model (SPEC §12e), as image-squeeze's rollout judges a build: each
candidate (a proposal a block made, ``improve.py``) is replayed beside the model as it is on the record that
came **after** it was proposed, which neither its maker nor the estimates it may rest on have seen, over
several windows of several durations (the whole of that record, its halves and its quarters). It is kept
only when it improves the model consistently: the scaled error falls by the threshold or more in every window
judged, or, for a change the fit cannot see, it is no worse in any window and answers findings ``check``
reported. It is dropped when it is worse by the threshold in any window, or better only in some, with the
windows as its evidence. A candidate is tested until its record held out is ``improve.hold-out`` long.

What happens to a kept change is the model's policy (``improve.accept``, by kind): ``owner`` (the default)
leaves it in the review queue with the judge's verdict beside it; ``auto`` writes it, as Accept does (the
smallest edit, ``check`` must still pass, recorded as ``model.accepted`` with its reason and effect), one a run.
The owner commits what was written.

Run by a block (``run: $ERGOSTAT_CMD judge``): ergostat adds no judge of its own accord. Its output lines say
how many candidates it moved, on the ports its block has: ``testing``, ``kept``, ``dropped``, ``accepted``."""

from __future__ import annotations

import time

from .. import series
from ..durations import human as dur
from ..spec.ir import Spec
from . import improve as im
from . import observe as ob
from . import proposals as pr
from . import trial as tr
from . import version as ver

SPLITS = (1, 2, 4)            # the record held out, whole, in halves and in quarters
MIN_WINDOW = 60.0             # a window shorter than this (s) is not judged
MIN_JUDGED = 3                # windows judged before a verdict
GIVE_UP = 3.0                 # after this many hold-outs with too few windows judged: dropped, too little record
MOST = 3                      # candidates judged in one run
PORTS = ("testing", "kept", "dropped", "accepted")


def windows(since: float, until: float) -> list[tuple[float, float]]:
    out = []
    span = until - since
    for k in SPLITS:
        w = span / k
        if w < MIN_WINDOW:
            continue
        out += [(since + i * w, since + (i + 1) * w) for i in range(k)]
    return out


def _grid(since: float, until: float) -> ob.Grid:
    return ob.Grid(since, until, max(2, min(series.POINTS, int((until - since) // ob.MIN_BUCKET))))


def compare(p, spec: Spec, after: Spec, since: float, until: float) -> dict:
    """The model as it is and with the change, replayed on one window: each one's scaled error, and the share by
    which the change lowers it (negative: raises it)."""
    grid = _grid(since, until)
    _, fb = tr.fit_of(spec, ob.measured(p, grid))
    _, fa = tr.fit_of(after, ob.measured(p, grid, after))
    b, a = im._nmse(fb), im._nmse(fa)
    change = (b - a) / b if b and a is not None else (0.0 if b == 0 and a == 0 else None)
    return {"since": since, "until": until, "before": b, "after": a, "change": change}


def decide(results: list[dict], threshold: float, answers: int, new: int, held: float, hold_out: float) -> tuple[str, str] | None:
    """The verdict, kept or dropped, with why; or None: keep testing."""
    judged = [r for r in results if r["change"] is not None]
    n = len(judged)
    if n < MIN_JUDGED:
        if held < GIVE_UP * hold_out:
            return None
        if answers and not new and not judged:
            return "kept", (f"nothing it changes is fitted, so the record cannot judge it; it answers {answers} finding"
                            f"{'s' if answers > 1 else ''} check reported, and makes none")
        return "dropped", (f"too little record to judge it: {n} window{'s' if n != 1 else ''} with a fit in "
                           f"{dur(held)} held out (at least {MIN_JUDGED} are needed)")
    pct = lambda v: f"{v * 100:.0f}%"                       # noqa: E731
    worse = [r for r in judged if r["change"] <= -threshold]
    better = [r for r in judged if r["change"] >= threshold]
    lo, hi = min(r["change"] for r in judged), max(r["change"] for r in judged)
    if worse:
        w = min(worse, key=lambda r: r["change"])
        return "dropped", (f"worse in {len(worse)} of {n} windows held out: the scaled error rises by up to "
                           f"{pct(-w['change'])} ({w['before']:.3g} → {w['after']:.3g} over {dur(w['until'] - w['since'])})")
    if len(better) == n:
        return "kept", (f"better in every one of {n} windows held out: the scaled error falls by {pct(lo)} to {pct(hi)} "
                        f"(the threshold is {pct(threshold)})")
    if not better and answers and not new:
        return "kept", (f"no worse in any of {n} windows held out (within {pct(threshold)}), and it answers {answers} "
                        f"finding{'s' if answers > 1 else ''} check reported, making none")
    return "dropped", (f"not consistently better: by {pct(threshold)} or more in {len(better)} of {n} windows held out "
                       f"(from {pct(lo)} to {pct(hi)})" + (f"; it makes {new} new finding{'s' if new > 1 else ''}" if new else ""))


def _event(p, x: dict, what: str, by: str, data: dict) -> None:
    p.events.add(f"model.{what}", item=f"proposal/{x['id']}", source=by, data={"title": x["title"], **data})


def run(p, by: str = "judge", at: float | None = None, most: int = MOST) -> dict:
    """One pass of the judge over the candidates waiting: start testing the new ones, judge those whose record
    held out is long enough, and write one kept change the policy lets it write. Returns what it moved."""
    spec: Spec = p.model.spec
    pol = spec.improve
    now = at or time.time()
    out = {p_: 0 for p_ in PORTS} | {"verdicts": [], "waiting": []}
    st = ver.structure(spec)
    judged = 0
    with pr.locked(p):
        props = pr.stored(p)
        for x in sorted((x for x in props.values() if pr.candidate(x) and x["status"] == "pending"), key=lambda x: x["created"]):
            if x.get("verdict"):
                continue
            stale = x.get("structure") != st or not pr.current(x, spec)
            if not stale:
                try:
                    after = tr.spec_after(p, tr.edits_of(x))
                except tr.TrialError as e:
                    stale, why = True, f"its edit no longer applies ({e})"
                else:
                    why = None
            else:
                why = "the model changed since it was proposed (another change was written)"
            if stale:
                x["status"], x["verdict"] = "dropped", {"verdict": "dropped", "why": why, "at": now, "windows": []}
                _event(p, x, "dropped", by, {"why": why, "verdict": "dropped"})
                out["dropped"] += 1
                out["verdicts"].append({"id": x["id"], "verdict": "dropped", "why": why})
                continue
            if not x.get("testing"):
                x["testing"] = now
                _event(p, x, "testing", by, {"hold_out": pol.hold_out})
                out["testing"] += 1
            since = x.get("proposed") or x["created"]
            held = now - since
            if held < pol.hold_out or judged >= most:
                out["waiting"].append({"id": x["id"], "held": held, "needs": pol.hold_out})
                continue
            judged += 1
            results = [compare(p, spec, after, a, b) for a, b in windows(since, now)]
            f = x.get("findings") or {}
            got = decide(results, pol.threshold, len(f.get("answered") or []), len(f.get("new") or []), held, pol.hold_out)
            if got is None:
                out["waiting"].append({"id": x["id"], "held": held, "needs": pol.hold_out, "judged": len(results)})
                continue
            verdict, why = got
            x["verdict"] = {"verdict": verdict, "why": why, "at": now, "threshold": pol.threshold, "windows": results,
                            "held": held, "by": by}
            if verdict == "dropped":
                x["status"] = "dropped"
            _event(p, x, verdict, by, {"why": why, "verdict": verdict, "windows": len(results),
                                       "scaled_error": [[r["before"], r["after"]] for r in results]})
            out[verdict] += 1
            out["verdicts"].append({"id": x["id"], "verdict": verdict, "why": why})
        pr.save(p, props)
    for x in sorted(pr.pending(p, spec), key=lambda x: x["created"]):      # one written a run, the oldest kept first
        v = x.get("verdict") or {}
        if not pr.candidate(x) or v.get("verdict") != "kept" or pol.accept.get(x["kind"]) != "auto":
            continue
        snap = {"at": now, "window": ob.reference(p, now).until - ob.reference(p, now).since}
        try:
            pr.accept(p, x["id"], snap, by=by, why=f"the judge kept it: {v['why']}", policy=f"improve.accept.{x['kind']}: auto")
        except pr.ProposalError as e:
            out["verdicts"].append({"id": x["id"], "verdict": "kept", "why": f"not written: {e}"})
            continue
        out["accepted"] += 1
        break
    return out


def lines(spec: Spec, block: str | None, got: dict) -> list[dict]:
    """What its block reports: what it moved on each port it has."""
    b = spec.blocks.get(block or "")
    if b is None:
        return []
    return [{"out": port, "moved": got[port]} for port in PORTS if port in b.outputs]
