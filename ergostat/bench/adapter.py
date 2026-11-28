"""The verification's handle on the improvement loop (SPEC §12e): the real modules (``numbers/improve.py``,
``numbers/judge.py``, ``numbers/proposals.py``), driven at a moment of a record and with a policy given:

- ``submit``: a block's ``propose`` line, checked and queued, or refused with why;
- ``judge``: one pass of the built-in judge at a moment, with the acceptance policy given (a judge block reads the
  model's ``improve:``; the benchmark sets it in memory, so the models it damages stay as written);
- ``accept``: Accept, writing exactly the diff shown (``expect``: its hash, ``review.diff_of``);
- ``changes``, ``pending``, ``accepted``: the ``ergostat.model-change`` items, folded from the record.

Every call made ``at`` a moment runs on the benchmark's clock (``clock.py``), so what it records is stamped then."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..numbers import improve as im
from ..numbers import judge as jd
from ..numbers import proposals as pr
from ..spec.ir import MODEL_CHANGE as ITEM
from ..spec.ir import MODEL_CHANGE_STATES as STATES  # noqa: F401  (re-exported for the tests)
from . import clock

VERIFIED, REGRESSED = f"{ITEM}.verified", f"{ITEM}.regressed"   # the prediction check's events (numbers/verify.py)


@dataclass
class Policy:
    accept: dict[str, str] = field(default_factory=lambda: {"parameter": "owner", "equation": "owner", "structure": "owner"})
    threshold: float = 0.02
    hold_out: float = 600.0

    @classmethod
    def auto(cls, threshold: float = 0.02, hold_out: float = 600.0) -> Policy:
        return cls(dict.fromkeys(("parameter", "equation", "structure"), "auto"), threshold, hold_out)


class Loop:
    """The improvement loop of one project."""

    def __init__(self, p, policy: Policy | None = None):
        self.p = p
        self.policy = policy or Policy()

    def submit(self, by: str, raw, data=None, at: float | None = None) -> dict:
        """``{"status": "proposed" | "refused", "id", "why"}``."""
        with clock.at(at):
            got = im.submit(self.p, by, raw, data=data, at=at)
        return {**got, "status": "proposed" if got["status"] == "proposed" else "refused"}

    def judge(self, at: float | None = None, by: str = "judge") -> dict:
        """One pass: ``{"verdicts": [{"id", "verdict": passed|failed|inconclusive|superseded, "why"}], "accepted": [ids]}``."""
        now = at or time.time()
        before = {x["id"] for x in self.accepted()}
        pol = self.p.model.spec.improve
        pol.accept, pol.threshold, pol.hold_out = dict(self.policy.accept), self.policy.threshold, self.policy.hold_out
        with clock.at(at):
            got = jd.run(self.p, by=by, at=now)
        return {"verdicts": got.get("verdicts") or [], "waiting": got.get("waiting") or [],
                "accepted": [x["id"] for x in self.accepted() if x["id"] not in before]}

    def accept(self, pid: str, at: float | None = None, by: str = "owner", expect: str | None = None) -> dict:
        from ..numbers import observe as ob
        now = at or time.time()
        with clock.at(at):
            g = ob.reference(self.p, now)
            return pr.accept(self.p, pid, {"at": now, "window": g.until - g.since}, by=by, expect=expect)

    def changes(self) -> dict[str, dict]:
        """Every change in the record with its ``state`` and ``status``, a superseded one too (``stored`` leaves it out)."""
        return {pid: {**f, "id": pid, "state": st, "status": pr.STATUS[st]} for pid, (st, f) in pr.changes(self.p).items()}

    def pending(self) -> list[dict]:
        return [x for x in self.changes().values() if x["state"] in pr.OPEN]

    def accepted(self) -> list[dict]:
        """The changes written, oldest first: ``id``, ``time``, ``kind``, ``title``, ``made_by``, the edit, the fit."""
        xs = [x for x in self.changes().values() if x["status"] in pr.WRITTEN]
        return sorted(({"id": x["id"], "time": x.get("decided") or 0.0, "kind": x.get("kind"), "title": x.get("title"),
                        "made_by": x.get("made_by"), "edit": x.get("edit") or {}, "applied": x.get("applied") or {},
                        "state": x["state"]} for x in xs), key=lambda x: x["time"])


def event(p, pid: str, state: str, data: dict | None = None, source: str = "ergostat", at: float | None = None) -> dict:
    """``ergostat.model-change.<state>`` about one change's item."""
    return p.events.add(f"{ITEM}.{state}", item=f"{ITEM}/{pid}", source=source, data=data or {}, at=at)
