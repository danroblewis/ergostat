"""What the redesigner learns from (SPEC §12e, *Redesign*): its memory, the past change sets for a system with what
became of each (the judge's verdict and scorecard, refused, accepted, dismissed with the owner's reason), and the other
changes the owner dismissed with a reason about the system's parts; and the interventions (SPEC §12p) about the system,
each a person's time spent where a loop is missing, with their cause, how they were answered and the notes given, and
the interventions loop's requests (``ergostat inbox --requests``) with their state. Both are given in the prompt,
compact, bounded by count and characters, so it does not propose again what was turned away and reads what people did
by hand as evidence of the structure the model lacks."""

from __future__ import annotations

import re
import time

from ..spec.ir import MODEL_CHANGE, Spec

MEMORY_MOST, MEMORY_CHARS = 6, 3000              # past changes shown at most, and their characters together
INTERVENTIONS_MOST, INTERVENTIONS_CHARS = 8, 2500
ONE = 600                                        # characters of any one entry at most
BECAME = {"checked": "proposed, not judged yet", "testing": "being judged", "passed": "judged better, waiting for the owner",
          "accepted": "accepted by the owner (written)", "verified": "accepted, and its forecast held",
          "regressed": "accepted, then flagged: the model forecast better without it", "failed": "judged NOT better",
          "refused": "refused (never proposed)", "dismissed": "DISMISSED by the owner",
          "inconclusive": "inconclusive (too little record)"}


def _cut(text, n: int = 200) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _bounded(entries: list[str], most: int, chars: int, what: str) -> list[str]:
    out, used = [], 0
    for e in entries:
        e = _cut(e, ONE)
        if len(out) >= most or used + len(e) > chars:
            out.append(f"- ({len(entries) - len(out)} more {what} not shown)")
            break
        out.append(e)
        used += len(e)
    return out


def _in(spec: Spec, system: str, refs) -> bool:
    from . import redesign_due as due
    return system == "model" or any(due._in(spec, system, r) for r in refs or [])


def memory(p, spec: Spec, system: str, most: int = MEMORY_MOST, chars: int = MEMORY_CHARS) -> list[str]:
    """The past redesigns of this system (of any system, for the whole model), newest first, each with what became
    of it; then the other changes about its parts that the owner dismissed with a reason."""
    from . import proposals as pr
    xs = sorted(reversed(list(pr.stored(p).values())), key=lambda x: -float(x.get("decided") or x.get("made") or x.get("created") or 0))
    out = []
    for x in xs:
        mine = x.get("kind") == "redesign" and (system == "model" or (x.get("system") or "model") == system)
        if not mine and not (x.get("status") == "dismissed" and x.get("dismissed_because")
                             and _in(spec, system, x.get("parts") or [x.get("target")])):
            continue
        card = x.get("scorecard") or {}
        verdict = (x.get("verdict") or {}).get("why") or card.get("why")
        said = [f"- {'redesign' if mine else x.get('kind') or 'change'} \"{_cut(x.get('title'), 120)}\": "
                f"{BECAME.get(x.get('state'), x.get('state'))}"]
        if x.get("dismissed_because"):
            said.append(f"the owner's reason: \"{_cut(x['dismissed_because'], 300)}\"")
        if x.get("state") == "refused" and x.get("why"):
            said.append(f"why: {_cut(x['why'])}")
        if verdict:
            said.append(f"scorecard: {card.get('verdict') or (x.get('verdict') or {}).get('verdict') or ''} {_cut(verdict)}".strip())
        for k in ("note", "notes", "review"):
            if x.get(k):
                said.append(f"{k}: \"{_cut(x[k], 300)}\"")
        if x.get("summary"):
            said.append(f"it did: {_cut(x['summary'], 200)}")
        edits = [e.get("said") or "" for e in ((x.get("redesign") or {}).get("edits") or []) if isinstance(e, dict)]
        if edits:
            said.append("edits: " + "; ".join(_cut(e, 80) for e in edits[:5]) + (f" (+{len(edits) - 5})" if len(edits) > 5 else ""))
        out.append(". ".join(said))
    return _bounded(out, most, chars, "changes")


def _refs(p, cls: str, cause: str) -> list[str]:
    """The parts an intervention is about: its class's block, and what its cause names (a block, a goal, a part, or
    the parts of the change it was)."""
    kind, _, name = cls.partition(":")
    refs = [f"block.{name}"] if kind in ("person", "advise", "alarm") and name and ":" not in name else []
    refs += [f"{k}.{n}" for k, n in re.findall(r"\b(block|goal) ([\w-]+)", cause or "")]
    refs += [f"{k}.{n}" for k, n in re.findall(r"\b(stock|flow|auxiliary|goal|block)\.([\w-]+)", cause or "")]
    if str(cause or "").startswith(MODEL_CHANGE + "/"):
        from . import proposals as pr
        x = pr.stored(p).get(cause.split("/", 1)[1]) or {}
        refs += x.get("parts") or [x.get("target")]
    return [r for r in refs if r]


def interventions(p, spec: Spec, system: str, now: float | None = None, most: int = INTERVENTIONS_MOST,
                  chars: int = INTERVENTIONS_CHARS) -> list[str]:
    """The interventions about this system over the interventions loop's window, by class (the most hours blocked
    first): how many, their causes, how they were answered, the notes given; with the class's request, if any."""
    from ..inbox import interventions as iv
    now = time.time() if now is None else now
    try:
        xs = iv.read(p, spec, now - iv._settings(spec)["window"], now)
    except Exception:                                # a record it cannot read: no evidence, never a failed prompt
        xs = []
    reqs = iv.requests_now(p)
    by: dict[str, dict] = {}
    for x in xs:
        if x["class"] != "change:redesign":          # (the memory says those)
            g = by.setdefault(x["class"], {"n": 0, "hours": 0.0, "causes": {}, "answers": {}, "notes": []})
            g["n"] += 1
            g["hours"] += ((x["answered"] or now) - x["time"]) / 3600.0
            g["causes"][x["cause"]] = g["causes"].get(x["cause"], 0) + 1
            g["answers"][x["verdict"] or "waiting"] = g["answers"].get(x["verdict"] or "waiting", 0) + 1
            if x.get("note") and x["note"] not in g["notes"]:
                g["notes"].append(f"{x['verdict'] or 'said'}: {x['note']}")
    for cls, r in reqs.items():
        g = by.setdefault(cls, {"n": int(r.get("count") or 0), "hours": float(r.get("hours") or 0.0), "causes": {},
                                "answers": {}, "notes": []})
        if r.get("cause"):
            g["causes"].setdefault(r["cause"], 0)
        g["request"] = r
        if r.get("note") and r["note"] not in g["notes"]:
            g["notes"].append(r["note"])
    out = []
    for cls, g in sorted(by.items(), key=lambda kv: (-kv[1]["hours"], -kv[1]["n"])):
        if not _in(spec, system, [r for c in g["causes"] for r in _refs(p, cls, c)] + _refs(p, cls, "")):
            continue
        said = [f"- {cls}: {g['n']} time{'s' if g['n'] != 1 else ''}, {g['hours']:.1f}h blocked",
                "cause: " + ", ".join(_cut(c, 80) for c in sorted(g["causes"], key=lambda c: -g["causes"][c])[:3])]
        if g["answers"]:
            said.append("answered: " + ", ".join(f"{k} {n}" for k, n in g["answers"].items()))
        if g["notes"]:
            said.append("notes: " + "; ".join(f"\"{_cut(n, 200)}\"" for n in g["notes"][-3:]))
        r = g.get("request")
        if r:
            said.append(f"request {r.get('state')}")      # (its remedies are generic: measured, they led haiku to add a
            # goal and a controller for every class, and the change sets stopped compiling; docs/redesign-bench.md)
        out.append(". ".join(said))
    return _bounded(out, most, chars, "classes")
