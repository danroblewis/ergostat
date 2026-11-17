"""A claim, recorded (SPEC §12g): an ``ergostat.claim`` item, made by the block whose run printed it.

Its id is ``ergostat.claim/<short hash>``. Every step is an event about it: ``ergostat.claim.made`` (from the block,
caused by its run), then one verdict from ergostat, ``.verified``, ``.contradicted`` or ``.unchecked``, caused by
the made event, carrying the evidence. The item, folded from them, is the claim; the record is the only store."""

from __future__ import annotations

import hashlib
import json
import re
import time

from ..spec.ir import CLAIM, CLAIM_STATES, Spec

SAYS_MAX = 500
ABOUT_KEYS = ("item", "file", "part", "commit", "dir", "run", "suite")
PART = re.compile(r"^(stock|flow|auxiliary|goal|block|parameter)\.[a-z][a-z0-9-]*$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
VERDICTS = tuple(s for s in CLAIM_STATES if s != "made")


class ClaimError(ValueError):
    """A claim line that cannot be recorded (it says nothing, or its ``about`` is not one ergostat reads)."""


def item_of(cid: str) -> str:
    return cid if cid.startswith(CLAIM + "/") else f"{CLAIM}/{cid}"


def rung_of(spec: Spec, block: str) -> str | None:
    """The block's rung: its agent's kind when it has one, else its type's."""
    b = spec.blocks.get(block)
    if b is None:
        return None
    if b.agent in spec.agents and spec.agents[b.agent].kind:
        return spec.agents[b.agent].kind
    return {"ai": "ai", "program": "program", "person": "person", "external": "external"}.get(b.type, "rule")


def model_of(spec: Spec, block: str, raw: dict) -> str | None:
    """The AI model behind the block: as the model writes it (the block's ``model``, its agent's), else as the claim
    says it (a wrapper that picks its model at run time, image-squeeze's ``bin/ai.sh``)."""
    b = spec.blocks.get(block)
    m = b.params.get("model") if b else None
    if not m and b and b.agent in spec.agents:
        m = spec.agents[b.agent].model
    return str(m or raw.get("model") or "") or None


def about_of(spec: Spec, raw) -> dict:
    """What a claim is about, as one of ``item``, ``file``, ``part``, ``commit`` (with an optional ``repo``), ``dir``,
    ``run`` or ``suite``. Written as a map, or as text: ``hypothesis/3`` (an id a kind of item matches), ``stock.x``
    (a part), a commit's hash, a file in the project, or any of them with its key first (``file:docs/a.md``)."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        out = {k: str(v) for k, v in raw.items() if k in (*ABOUT_KEYS, "repo") and v not in (None, "")}
        if not set(out) - {"repo"}:
            raise ClaimError(f"about: one of {', '.join(ABOUT_KEYS)}")
        return out
    if not isinstance(raw, str):
        raise ClaimError("about: text (hypothesis/3, stock.x, a file, a commit) or a map ({\"item\": ...})")
    s = raw.strip()
    for k in ABOUT_KEYS:
        if s.startswith(k + ":"):
            return {k: s[len(k) + 1:].strip()}
    if PART.match(s):
        return {"part": s}
    if "/" in s and any(k.matches(s) for k in spec.items.values()):
        return {"item": s}
    if COMMIT.match(s):
        return {"commit": s}
    if not s.startswith("/") and ".." not in s.split("/") and (spec.root / s).exists():
        return {"file": s}
    return {"text": s}


def made(p, spec: Spec, by: str, raw, run: str | None = None, n: int = 0, at: float | None = None) -> dict:
    """A block's claim line, recorded as made. Returns the claim (its fields, with ``id``). Raises ClaimError for a
    line that cannot be one: the block is told, in ``agent.refused``, as for any line it got wrong."""
    from . import checks
    if not isinstance(raw, dict):
        raise ClaimError("a claim is a map: {\"says\": \"tests pass\", \"about\": ..., \"check\": ...}")
    says = raw.get("says")
    if not isinstance(says, str) or not says.strip():
        raise ClaimError("a claim says what was done: {\"says\": \"tests pass\"}")
    says = says.strip()[:SAYS_MAX]
    about = about_of(spec, raw.get("about"))
    check = raw.get("check")
    if check is not None and not isinstance(check, str | dict):
        raise ClaimError("check: the name of a check (tests, changed, state, exit, level, or one the model declares "
                         "under claims:) or a map ({\"state\": \"done\"}, {\"level\": \">= 3\"}, {\"exit\": 0})")
    now = at or time.time()
    kind, params = checks.kind_of(spec, {"says": says, "about": about, "check": check})
    cid = hashlib.sha1(json.dumps([run, n, by, says, about, now], default=str).encode()).hexdigest()[:10]
    c = {"says": says, "about": about, "check": check, "kind": kind, "block": by, "rung": rung_of(spec, by),
         "model": model_of(spec, by, raw), "run": run, "made": now,
         **({"session": str(raw["session"])} if raw.get("session") else {}),
         **({"params": params} if params else {}),
         **({"evidence_given": raw["evidence"]} if raw.get("evidence") is not None else {})}
    ev = p.events.add(f"{CLAIM}.made", item=item_of(cid), source=by, causedby=run, data=c, at=now)
    return {**c, "id": item_of(cid), "made_event": ev["id"], "state": "made"}


def verdict(p, claim: dict, state: str, evidence: dict, why: str, seconds: float | None = None) -> dict:
    """ergostat's verdict on a claim, with what it found."""
    assert state in VERDICTS
    data = {"verdict": state, "why": why, "evidence": evidence, "kind": claim.get("kind"), "block": claim.get("block"),
            "rung": claim.get("rung"), "model": claim.get("model"), "checked": time.time(),
            **({"seconds": round(seconds, 3)} if seconds is not None else {})}
    return p.events.add(f"{CLAIM}.{state}", item=claim["id"], source="ergostat", causedby=claim.get("made_event"), data=data)


def stored(p, since: float | None = None, until: float | None = None) -> dict[str, dict]:
    """Every claim made since then, folded from its events (each field replaced, as the kind folds them), with its
    ``state`` and the time of its verdict."""
    out: dict[str, dict] = {}
    for e in p.events.query(n=None, type=f"{CLAIM}.*", since=since, until=until):   # (a verdict comes after its claim)
        x = out.get(e["item"])
        st = e["type"].rsplit(".", 1)[1]
        if st == "made":
            out[e["item"]] = {**e["data"], "id": e["item"], "state": "made", "made_event": e["id"], "time": e["time"]}
        elif x is not None and st in VERDICTS:
            x.update({k: v for k, v in e["data"].items() if k in ("verdict", "why", "evidence", "seconds", "checked")})
            x.update(state=st, verdict_event=e["id"], verdict_time=e["time"])
    return out


def of_run(p, run: str) -> list[dict]:
    """The claims a run made, oldest first."""
    made_ = [e for e in p.events.caused_by(run) if e["type"] == f"{CLAIM}.made"]
    got = stored(p, since=min((e["time"] for e in made_), default=None)) if made_ else {}
    return [got[e["item"]] for e in made_ if e["item"] in got]
