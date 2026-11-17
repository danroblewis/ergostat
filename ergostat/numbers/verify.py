"""The prediction check (SPEC §12f): every change written to the model is scored again later, on the record that
came after it was written, which nothing that made, judged or accepted it has seen. The model as it is now is
replayed beside the same model with that change undone, over the whole of that record and its halves (the
forecast error: a free replay from each window's start, the inputs as measured).

- **verified** (``ergostat.model-change.verified``): the change still forecasts no worse than without it;
- **regressed** (``ergostat.model-change.regressed``): without it the forecast is better by the threshold, over
  the whole record since and in at least half the windows: flagged for revert, the edit that reverts it attached
  (and, with ``propose``, proposed as a change of its own, by this check, for the judge and the owner to decide).

A change is checked once, after ``AFTER`` hold-outs of record; one whose edit can no longer be undone (a later
change rewrote its lines) is said so and not judged. Run by a block (``ergostat verify``), like the judge: ergostat
adds no check of its own accord. The two verdicts are states of the change's ``ergostat.model-change`` item
(its status stays accepted)."""

from __future__ import annotations

import time

from ..bench import adapter as ad
from . import observe as ob
from . import trial as tr
from . import yamledit as ye

AFTER = 3.0               # hold-outs of record after a change was written before it is checked
SPLITS = (1, 2)


def revert(x: dict) -> list[ye.Edit]:
    """The edit that undoes a written change: each hunk's new lines back to its old ones, where they sit now."""
    out = []
    for f in (x.get("edit") or {}).get("files") or []:
        e = ye.Edit.from_dict(f)
        shift, hunks = 0, []
        for h in sorted(e.hunks, key=lambda h: h.line):
            hunks.append(ye.Hunk(h.line + shift, list(h.new), list(h.old)))
            shift += len(h.new) - len(h.old)
        out.append(ye.Edit(e.file, hunks))
    return out


def _nmse(p, spec, since: float, until: float) -> float | None:
    grid = ob.Grid(since, until, max(2, min(120, int((until - since) // ob.MIN_BUCKET))))
    run, got = tr.fit_of(spec, ob.measured(p, grid, spec))
    return (got.get("total") or {}).get("nmse") if run.valid else None


def checked(p) -> dict[str, str]:
    """The changes already checked: id → verified or regressed."""
    out = {}
    for t, state in ((ad.VERIFIED, "verified"), (ad.REGRESSED, "regressed")):
        for e in p.events.query(n=None, type=t):
            out[str((e.get("data") or {}).get("change") or str(e.get("item") or "").rsplit("/", 1)[-1])] = state
    return out


def check_one(p, x: dict, now: float, threshold: float) -> dict:
    """One written change, scored on the record since it was written: its verdict and the windows."""
    since = x["time"]
    try:
        texts = ye.apply_together(revert(x))
    except ye.EditError as e:
        return {"verdict": None, "why": f"it can no longer be undone ({e}): a later change rewrote its lines"}
    without, errors = tr.compiled(p.model.path, texts)
    if errors:
        return {"verdict": None, "why": "undone, the model would not compile: " + "; ".join(str(e) for e in errors[:2])}
    spec = p.model.spec
    wins = []
    for k in SPLITS:
        w = (now - since) / k
        for i in range(k):
            a, b = since + i * w, since + (i + 1) * w
            now_, was = _nmse(p, spec, a, b), _nmse(p, without, a, b)
            wins.append({"since": a, "until": b, "with": now_, "without": was,
                         "change": (was - now_) / was if was and now_ is not None else None})
    judged = [w for w in wins if w["change"] is not None]
    whole = wins[0]
    if whole["change"] is None:
        return {"verdict": None, "why": "too little record since it was written to replay", "windows": wins}
    worse = [w for w in judged if w["change"] <= -threshold]
    if whole["change"] <= -threshold and len(worse) * 2 >= len(judged):
        return {"verdict": "regressed", "windows": wins,
                "why": f"since it was written the model forecasts worse with it: the scaled error is {whole['with']:.3g} "
                       f"with it and {whole['without']:.3g} without, worse in {len(worse)} of {len(judged)} windows"}
    return {"verdict": "verified", "windows": wins,
            "why": f"since it was written it forecasts no worse: the scaled error is {whole['with']:.3g} with it, "
                   f"{whole['without']:.3g} without"}


def run(p, at: float | None = None, hold_out: float | None = None, threshold: float | None = None, by: str = "verify",
        propose: bool = False) -> dict:
    """One pass over the changes written: each checked once its record since is long enough."""
    from ..bench import clock
    with clock.at(at):
        return _run(p, at or time.time(), hold_out, threshold, by, propose)


def _run(p, now: float, hold_out, threshold, by: str, propose: bool) -> dict:
    pol = getattr(p.model.spec, "improve", None)
    hold = hold_out or getattr(pol, "hold_out", None) or 600.0
    thr = threshold or getattr(pol, "threshold", None) or 0.02
    loop = ad.Loop(p)
    done = checked(p)
    out = {"verified": [], "regressed": [], "waiting": [], "unjudged": []}
    for x in loop.accepted():
        if x["id"] in done:
            continue
        if now - x["time"] < AFTER * hold:
            out["waiting"].append({"id": x["id"], "since": x["time"], "needs": AFTER * hold})
            continue
        got = check_one(p, x, now, thr)
        if got["verdict"] is None:
            out["unjudged"].append({"id": x["id"], "why": got["why"]})
            continue
        data = {"change": x["id"], "title": x.get("title"), "why": got["why"], "windows": got["windows"], "by": by}
        if got["verdict"] == "regressed":
            data["revert"] = {"files": [e.as_dict() for e in revert(x)]}
        ad.event(p, x["id"], got["verdict"], data, source=by)
        out[got["verdict"]].append({"id": x["id"], "why": got["why"]})
        if got["verdict"] == "regressed" and propose:
            raw = {"kind": x.get("kind") or "structure", "title": f"undo: {x.get('title')}", "parts": [],
                   "edit": data["revert"], "confidence": 0.6,
                   "reasons": [{"says": got["why"], "evidence": "fit:total.nmse"},
                               {"says": "the model's behaviour should reproduce the record", "evidence": "rule:behaviour-reproduction"}]}
            out[got["verdict"]][-1]["proposed"] = loop.submit(by, raw, at=now)
    return out
