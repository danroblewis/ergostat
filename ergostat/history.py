"""The model's history, kept as events: each time the model is loaded and differs from the last one
recorded, ``model.changed`` says which parts were added, removed or changed. ``--since`` reads them
back, so a change can be seen before and after."""

from __future__ import annotations

import dataclasses
import hashlib
import json


def _declared(obj) -> dict:
    """What an object declares: its fields that differ from their defaults (so a field added to
    ergostat later, with a default, is not a change to anyone's model)."""
    out = {}
    for f in dataclasses.fields(obj):
        if f.metadata.get("history") is False:
            continue
        if f.name == "mode" and getattr(obj, "mode_set", True) is False:   # a default filled in, not written
            continue
        v = getattr(obj, f.name)
        default = f.default if f.default is not dataclasses.MISSING else (
            f.default_factory() if f.default_factory is not dataclasses.MISSING else dataclasses.MISSING)
        if v != default:
            out[f.name] = v
    return out


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(_declared(obj), sort_keys=True, default=str).encode()).hexdigest()[:10]


def fingerprints(model) -> dict[str, str]:
    """Each part and agent, by ``kind:name``, with a short hash of what it declares."""
    out = {}
    for t in (model.stocks, model.flows, model.valves, model.sensors, model.controllers):
        for p in t.values():
            kind = "disturbance" if getattr(p, "disturbance", False) else p.kind
            out[f"{kind}:{p.name}"] = _hash(p)
    for a in model.agents.values():
        out[f"agent:{a.name}"] = _hash(a)
    return out


def note(project) -> dict | None:
    """Record ``model.changed`` when the model differs from the last one recorded; return it."""
    now = fingerprints(project.model)
    last = project.events.query(n=1, type="model.changed")
    before = last[-1]["data"].get("parts", {}) if last else {}
    if now == before:
        return None
    added = sorted(set(now) - set(before))
    removed = sorted(set(before) - set(now))
    changed = sorted(k for k in set(now) & set(before) if now[k] != before[k])
    return project.events.add("model.changed", item=project.model.name, source="ergostat",
                              data={"added": added, "removed": removed, "changed": changed, "parts": now,
                                    "first": not last})


def changes(project, since: float) -> list[dict]:
    """The model's changes since then, oldest first (the first recording of a model is not a change)."""
    return [e for e in project.events.query(n=None, type="model.changed", since=since) if not e["data"].get("first")]
