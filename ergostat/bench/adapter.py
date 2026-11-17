"""The one place that knows the improvement loop's interface (SPEC §12e), so the verification merges with the
improver whichever lands first. Everything in ``ergostat/bench`` (and the live checks, ``numbers/verify.py`` and
``numbers/meta.py``) goes through ``Loop``:

- ``submit``: a block's ``propose`` line, checked and queued, or refused with why;
- ``judge``: one pass of the judge at a moment, with the acceptance policy given (``accept``: ``owner`` or ``auto``,
  by kind; ``threshold``; ``hold_out``);
- ``accept``: Accept, writing exactly the diff shown (``expect``: its hash, ``review.diff_of``);
- ``changes``: every change with its state, as one of ``STATES``;
- ``accepted``: the changes written, oldest first.

The backend is the improver's own modules (``ergostat.numbers.improve`` and ``judge``) when they can be imported,
else ``shim.py``, which keeps the same contract on main's code. Names that differ between the improver's versions
(``kept``/``passed``, ``dropped``/``failed``, ``proposed_by``/``made_by``) are normalised here and nowhere else."""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field

from . import clock

ITEM = "ergostat.model-change"                 # the built-in item kind; each change is ``ergostat.model-change/ID``
STATES = ("checked", "testing", "passed", "accepted", "refused", "failed", "dismissed", "superseded")
VERIFIED, REGRESSED = f"{ITEM}.verified", f"{ITEM}.regressed"   # the prediction check's events (numbers/verify.py)
VERIFIED_OUT, REGRESSED_OUT = "ergostat.model.verified", "ergostat.model.regressed"   # the same, outside the item, while
#                                 the improver's fold of ergostat.model-change has no such states (see verdict_event)
_VERDICT = {"kept": "passed", "dropped": "failed", "passed": "passed", "failed": "failed", "superseded": "superseded"}
_STATUS = {"pending": None, "accepted": "accepted", "dismissed": "dismissed", "dropped": "failed", "failed": "failed",
           "refused": "refused", "superseded": "superseded"}


def _module(name: str):
    try:
        return importlib.import_module(f"ergostat.numbers.{name}")
    except ImportError:
        return None


def backend() -> str:
    """``improver`` when its modules are here, else ``shim``."""
    im, jd = _module("improve"), _module("judge")
    return "improver" if im is not None and jd is not None and hasattr(im, "submit") and hasattr(jd, "run") else "shim"


@dataclass
class Policy:
    accept: dict[str, str] = field(default_factory=lambda: {"parameter": "owner", "equation": "owner", "structure": "owner"})
    threshold: float = 0.02
    hold_out: float = 600.0

    @classmethod
    def auto(cls, threshold: float = 0.02, hold_out: float = 600.0) -> Policy:
        return cls(dict.fromkeys(("parameter", "equation", "structure"), "auto"), threshold, hold_out)


def maker(x: dict) -> str | None:
    return x.get("made_by") or x.get("proposed_by")


class Loop:
    """The improvement loop of one project, through whichever backend is here."""

    def __init__(self, p, policy: Policy | None = None, force: str | None = None):
        self.p = p
        self.policy = policy or Policy()
        self.backend = force or backend()

    # ---- what changes the record

    def submit(self, by: str, raw, data=None, at: float | None = None) -> dict:
        """``{"status": "proposed" | "refused", "id", "why"}``: a change the queue already holds is refused, said so."""
        if self.backend == "shim":
            from . import shim
            with clock.at(at):
                return shim.submit(self.p, by, raw, data=data, at=at)
        with clock.at(at):
            got = _module("improve").submit(self.p, by, raw, data=data, at=at)
        if got["status"] == "also":
            return {**got, "status": "refused", "why": got.get("why") or "already waiting"}
        return {**got, "status": "proposed" if got["status"] == "proposed" else "refused"}

    def trial(self, raw, data=None) -> dict:
        if self.backend == "shim":
            from . import shim
            return shim.trial(self.p, raw, data)
        return _module("improve").trial(self.p, raw)

    def judge(self, at: float | None = None, by: str = "judge") -> dict:
        """One pass: ``{"verdicts": [{"id", "verdict": passed|failed|superseded, "why"}], "accepted": [ids]}``."""
        now = at or time.time()
        pol = {"accept": dict(self.policy.accept), "threshold": self.policy.threshold, "hold_out": self.policy.hold_out}
        if self.backend == "shim":
            from . import shim
            with clock.at(at):
                return shim.judge(self.p, pol, by=by, at=now)
        before = {x["id"] for x in self.accepted()}
        spec = self.p.model.spec
        for k in ("accept", "threshold", "hold_out"):      # the policy is the model's (improve:); the bench sets it here
            setattr(spec.improve, k, pol[k])
        with clock.at(at):
            got = _module("judge").run(self.p, by=by, at=now)
        verdicts = [{**v, "verdict": _VERDICT.get(v["verdict"], v["verdict"])} for v in got.get("verdicts") or []]
        return {"verdicts": verdicts, "waiting": got.get("waiting") or [],
                "accepted": [x["id"] for x in self.accepted() if x["id"] not in before]}

    def accept(self, pid: str, at: float | None = None, by: str = "owner", expect: str | None = None) -> dict:
        from ..numbers import observe as ob
        now = at or time.time()
        g = ob.reference(self.p, now)
        snap = {"at": now, "window": g.until - g.since}
        with clock.at(at):
            if self.backend == "shim":
                from . import shim
                return shim.accept(self.p, pid, snap, by=by, expect=expect)
            from ..numbers import proposals as pr
            return pr.accept(self.p, pid, snap, by=by, expect=expect)

    # ---- what it reads

    def changes(self) -> dict[str, dict]:
        """Every change kept in the queue, each with ``state`` (one of ``STATES``) and ``made_by``."""
        from ..numbers import proposals as pr
        out = {}
        for pid, x in pr.stored(self.p).items():
            st = x.get("state")
            if st not in STATES:
                st = _STATUS.get(x.get("status")) or ("passed" if (x.get("verdict") or {}).get("verdict") == "kept" else
                                                      "testing" if x.get("testing") else "checked")
            out[pid] = {**x, "id": pid, "state": st, "made_by": maker(x)}
        return out

    def pending(self) -> list[dict]:
        return [x for x in self.changes().values() if x["state"] in ("checked", "testing", "passed")]

    def accepted(self) -> list[dict]:
        """The changes written, oldest first: ``id``, ``time``, ``kind``, ``title``, ``made_by``, the edit's files."""
        xs = [x for x in self.changes().values() if x["state"] == "accepted"]
        return sorted(({"id": x["id"], "time": x.get("decided") or 0.0, "kind": x.get("kind"), "title": x.get("title"),
                        "made_by": x.get("made_by"), "edit": x.get("edit") or {}, "applied": x.get("applied") or {}}
                       for x in xs), key=lambda x: x["time"])

    def diff_hash(self, pid: str) -> str | None:
        """The hash of exactly what Accept would write (``review.diff_of``), as the owner is shown it."""
        from ..numbers import review as rv
        return rv.diff_of(self.changes()[pid], self.p.model.path.parent).get("hash")


def event(p, pid: str, state: str, data: dict | None = None, source: str = "ergostat", at: float | None = None) -> dict:
    """``ergostat.model-change.<state>`` about one change's item."""
    return p.events.add(f"{ITEM}.{state}", item=f"{ITEM}/{pid}", source=source, data=data or {}, at=at)


def verdict_event(loop: Loop, pid: str, state: str, data: dict, source: str = "verify") -> dict:
    """The prediction check's verdict on a written change (``verified`` or ``regressed``): an event about the change's
    item, so its fold shows it; or, where the improver's fold of ``ergostat.model-change`` does not know these states
    yet (``proposals.STATUS``), the same under ``ergostat.model.verified`` / ``.regressed``, about the model, so the fold
    is never broken."""
    if loop.backend == "improver":
        from ..numbers import proposals as pr
        if state not in getattr(pr, "STATUS", {}):
            return loop.p.events.add(VERIFIED_OUT if state == "verified" else REGRESSED_OUT, item=loop.p.model.name,
                                     source=source, data={"item": f"{ITEM}/{pid}", **data})
    return event(loop.p, pid, state, data, source=source)
