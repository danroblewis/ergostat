"""Interface stability over the model's recorded history: each ``model.changed`` of a YAML model carries a signature
of every system's interface (``Spec.interface``), and ``stability`` counts how often one system's changed. Only
versions ergostat loaded are seen; anything it cannot read starts the count over, never "unchanged"."""

from __future__ import annotations

import hashlib
import json
import time


def signature(ports: list[dict]) -> str:
    """A short hash of a system's ports: their direction, kind, part and peers, in no particular order. A port
    without one of these fields raises."""
    enc = json.dumps(sorted([p["dir"], p["kind"], p["part"], sorted(p["peers"])] for p in ports), separators=(",", ":"))
    return hashlib.sha256(enc.encode()).hexdigest()[:16]


def signatures(spec) -> dict[str, str]:
    """Each system's signature, an empty interface hashed like any other."""
    return {s: signature(spec.interface(s)) for s in spec.systems}


def recorded(interfaces) -> bool:
    """Whether a ``model.changed`` event's ``interfaces`` can be read: a dict of strings."""
    return isinstance(interfaces, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in interfaces.items())


def stability(events: list[dict], system: str, now_sig: str) -> dict:
    """How often ``system``'s interface changed over the trailing run of ``model.changed`` events (in seq order) that
    record it. An event without it starts the run over; consecutive equal (version, signature) entries are one
    version. ``{"recorded": False}`` when the run is empty or does not end at ``now_sig``."""
    run: list[tuple] = []
    for e in sorted(events, key=lambda e: e["seq"]):
        d = e.get("data")
        ifs = d.get("interfaces") if isinstance(d, dict) else None
        sig = ifs.get(system) if isinstance(ifs, dict) else None
        if not isinstance(sig, str):
            run = []
            continue
        if run and run[-1][:2] == (d.get("version"), sig):
            continue
        run.append((d.get("version"), sig, e["time"]))
    if not run or run[-1][1] != now_sig:
        return {"recorded": False}
    unchanged = next((i for i, x in enumerate(reversed(run)) if x[1] != now_sig), len(run))
    changed = sum(run[i][1] != run[i + 1][1] for i in range(len(run) - 1))
    return {"recorded": True, "versions": len(run), "changed": changed, "unchanged": unchanged, "since": run[-unchanged][2]}


def said(project, spec, system: str) -> str:
    """The line ``explain system.NAME`` gives with a project."""
    st = stability(project.events.query(n=None, type="model.changed"), system, signature(spec.interface(system)))
    head = "Interface over the model's recorded history: "
    if not st["recorded"]:
        return head + "the interface as it is now is not recorded yet."
    u, v, c = st["unchanged"], st["versions"], st["changed"]
    return (head + f"unchanged over the last {u} of {v} recorded version{'' if v == 1 else 's'} "
            f"(since {time.strftime('%Y-%m-%d', time.localtime(st['since']))}); {c} change{'' if c == 1 else 's'}.")
