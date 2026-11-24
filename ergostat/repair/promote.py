"""Promotion down the ladder for ``apply-fix`` (SPEC §12r, ``promote: true``): the rung a block's fix is answered at,
worked out from the record each time a fix is tested, never stored. It starts at the owner's ``approver`` and moves
down one rung (person, ai, program only with ``approve-with``, rule) once the last ``EARN`` answers given at the
current rung, by seq, were all approved and ran. A ``regressed`` or ``reverted`` failure of the block, or a denial,
sends it back to the owner's rung: only answers after that seq count again. An unreadable record is the owner's rung."""

from __future__ import annotations

from ..actions import record as rec
from ..inbox import stats
from ..spec.ir import ACTION
from . import FAILURE
from . import fix as fx

LADDER = ("person", "ai", "program", "rule")
EARN = 10


def ladder(a) -> list[str]:
    """The rungs a block may be answered at, from the owner's down (``program`` only with ``approve-with``)."""
    own = getattr(a, "approver", "person")
    down = LADDER[LADDER.index(own):] if own in LADDER else (own,)
    return [r for r in down if r != "program" or r == own or getattr(a, "approve_with", None)]


def rung_of(by) -> str | None:
    """The rung that gave an approval, from its ``approved_by``; the person's only for the owner's own answers, and None
    (no rung's evidence) for an agent's through the MCP or the gate's own (SPEC §12r)."""
    got = next((r for r in ("ai", "program", "rule") if str(by or "").startswith(f"{r} approver")), None)
    return got or ("person" if stats.by_person(by) else None)


def answers(p, block: str) -> tuple[list[dict], int | None, int]:
    """The block's ``apply-fix`` answers (each action's first ``approved`` or ``denied``) as ``{seq, rung, state}``; the
    seq of its newest answer, run, regression or revert; and the seq of its latest denial, regression or revert (only
    answers after it count). Raises when the record cannot be read."""
    by: dict[str, list[dict]] = {}
    for e in p.events.query(n=None, type=f"{ACTION}.*"):
        by.setdefault(e["item"], []).append(e)
    rows, seen, cut = [], [], [0]
    for item, es in by.items():
        d = es[0].get("data") or {}
        m = fx.ID.match(str(d.get("item") or ""))
        if es[0]["type"] != f"{ACTION}.requested" or d.get("action") != "apply-fix" or not m or m[1] != block:
            continue
        said = [e for e in es if e["type"].rsplit(".", 1)[1] in ("approved", "denied", "ran", "failed")]
        seen += [e["seq"] for e in said]
        cut += [e["seq"] for e in said if e["type"] == f"{ACTION}.denied"]
        first = next((e for e in said if e["type"].rsplit(".", 1)[1] in ("approved", "denied")), None)
        if first:
            rows.append({"seq": first["seq"], "rung": rung_of((first.get("data") or {}).get("approved_by")),
                         "state": rec.fold(item, es)["state"]})
    for e in p.events.query(n=None, type=f"{FAILURE}.*"):
        m = fx.ID.match(str(e.get("item") or ""))
        if m and m[1] == block and e["type"] in (f"{FAILURE}.regressed", f"{FAILURE}.reverted"):
            seen.append(e["seq"])
            cut.append(e["seq"])
    return sorted(rows, key=lambda r: r["seq"]), max(seen, default=None), max(cut)


def rung(p, a, block: str) -> dict:
    """``{rung, earned, newest}``: the rung the block's next fix is answered at, the seqs of the answers that earned
    its last step down (None at the owner's rung), and the newest seq read."""
    steps, (rows, newest, cut) = ladder(a), answers(p, block)
    i, at, earned = 0, [], None
    for r in rows:
        if i + 1 >= len(steps):                              # never below the rule (the ladder's end)
            break
        if r["seq"] <= cut or r["rung"] != steps[i]:
            continue
        at.append(r)
        if len(at) >= EARN and all(x["state"] == "ran" for x in at[-EARN:]):
            i, earned, at = i + 1, [x["seq"] for x in at[-EARN:]], []
    return {"rung": steps[i], "earned": earned, "newest": newest}


def read(p, a, block: str) -> dict:
    """``rung``, or the owner's rung when the record cannot be read (lesson-3: never a lower one)."""
    try:
        return rung(p, a, block)
    except Exception as e:
        return {"rung": getattr(a, "approver", "person"), "earned": None, "newest": None,
                "why": f"the record cannot be read: {str(e)[:300]}"}


def still(p, a, block: str, was: dict) -> bool:
    """Read again under the failure's lock: the same rung, and the block's newest answered seq unmoved (an unreadable
    record both times is the owner's rung both times)."""
    again = read(p, a, block)
    return again["rung"] == was["rung"] and again["newest"] == was["newest"]
