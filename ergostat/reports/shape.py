"""What a report may say about the owner's model without naming anything in it (SPEC §12m): counts of its parts and
kinds, and a small generic reproduction: the parts involved (and what they touch), every name a stand-in, every
description, prompt and command left out."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

REPRO_MAX = 30           # a whole model this small (in entries) may be the reproduction when no part is named
DROP = {"description", "prompt", "ask", "reading", "example", "title", "says", "words", "note", "help", "label"}
COMMANDS = {"run", "command", "cmd", "exec"}


def stats(spec) -> dict:
    """Counts only: how many of each part, block type, sensor kind, projection and template, never which."""
    if spec is None:
        return {}
    blocks = Counter(b.type for b in spec.blocks.values())
    sensors: Counter = Counter()
    for s in spec.sensors():
        sensors["builtin" if s.builtin else "projection" if s.items else "changes" if s.changes else "query" if s.query
                else "manual" if s.manual else "command" if s.run else "other"] += 1
    own = [k for k in spec.items.values() if not k.name.startswith("ergostat.")]
    templates = Counter()
    from .scrub import public_names
    public = public_names()
    for u in (spec.uses or {}).values():
        t = (u.get("use") or u.get("template")) if isinstance(u, dict) else getattr(u, "template", None)
        templates[str(t) if t and str(t) in public else "the owner's own"] += 1
    depth = max((len(spec.chain(s)) for s in spec.systems), default=0)
    out = {
        "stocks": len(spec.stocks), "flows": len(spec.flows), "auxiliaries": len(spec.auxiliaries),
        "parameters": len(spec.parameters), "goals": len(spec.goals), "blocks": len(spec.blocks),
        "blocks by type": dict(sorted(blocks.items())), "sensors by kind": dict(sorted(sensors.items())),
        "agents by kind": dict(sorted(Counter(a.kind or "unknown" for a in spec.agents.values()).items())),
        "projections": len(own), "states per projection": sorted(len(k.states) for k in own),
        "projections with relations": sum(1 for k in own if k.relations),
        "systems": len(spec.systems), "systems nested deepest": depth,
        "sources by type": dict(sorted(Counter(s.type for s in spec.sources.values()).items())),
        "template uses": dict(sorted(templates.items())), "remotes": len(spec.remotes or {}),
        "named loops": len(spec.named_loops), "contexts": len(spec.contexts), "gated actions": len(spec.actions),
        "workspace pools": len(spec.workspaces), "files": len(spec.files),
    }
    return {k: v for k, v in out.items() if v not in (0, {}, [])}


def table(st: dict) -> str:
    if not st:
        return "_No model (or an `ergostat.toml`)._"
    rows = ["| part | count |", "|---|---|"]
    for k, v in st.items():
        if isinstance(v, dict):
            v = ", ".join(f"{a} {b}" for a, b in v.items())
        elif isinstance(v, list):
            v = ", ".join(map(str, v))
        rows.append(f"| {k} | {v} |")
    return "\n".join(rows)


# ---- the reproduction

def _plain(x):
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def _generic(x, scrubber, key: str | None = None):
    """An entry with every name a stand-in: keys that are names and every string scrubbed; descriptions and prompts
    left out, commands made a stand-in that prints 0, URLs a local one."""
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            if k in DROP:
                continue
            nk = scrubber.scrub(k) if isinstance(k, str) else k
            out[nk] = _generic(v, scrubber, k)
        return out
    if isinstance(x, list):
        return [_generic(v, scrubber, key) for v in x]
    if isinstance(x, str):
        if key in COMMANDS:
            return "echo 0"
        if key == "url":
            return "http://localhost:9090"
        return scrubber.scrub(x)
    return x


def _words(x) -> set[str]:
    import re

    import yaml
    return set(re.findall(r"[A-Za-z0-9_][\w-]*", yaml.safe_dump(_plain(x), sort_keys=False)))


def repro(path: Path | None, scrubber, parts: list[str] | None = None) -> str | None:
    """A tiny model, as YAML, with every name a stand-in: the parts named (``stock.inbox`` or a bare name) and every
    entry they name, or the whole model when it is small and no part is named. None: nothing to show."""
    if path is None or Path(path).name != "ergostat.yaml":
        return None
    try:
        from ..spec.load import SECTIONS
        from ..spec.load import load as load_doc
        doc = load_doc(Path(path))
    except Exception:
        return None
    entries = {(sec, name): ent for sec in SECTIONS for name, ent in doc.sections.get(sec, {}).items()}
    if not entries:
        return None
    if parts:
        want = {str(p).split(".", 1)[1] if "." in str(p) and str(p).split(".", 1)[0] in
                {"stock", "flow", "auxiliary", "goal", "block", "agent", "system", "source", "parameter", "item", "kind", "projection"}
                else str(p) for p in parts}
        chosen = {k for k in entries if k[1] in want}
        if not chosen:
            return None
        edge = set(chosen)
        for _ in range(4):                               # and what they name, and what that names, a few steps out
            words = set().union(*(_words(entries[k]) for k in edge)) if edge else set()
            edge = {k2 for k2 in entries if k2[1] in words} - chosen
            chosen |= edge
            if not edge or len(chosen) > REPRO_MAX:
                break
    elif len(entries) <= REPRO_MAX:
        chosen = set(entries)
    else:
        return None
    doc_out: dict = {"name": "repro"}
    for sec in SECTIONS:
        got = {name: entries[(sec, name)] for (s, name) in sorted(chosen) if s == sec}
        if got:
            doc_out[sec] = {scrubber.scrub(n): _generic(_plain(e), scrubber) for n, e in got.items()}
    import yaml
    return yaml.safe_dump(doc_out, sort_keys=False, allow_unicode=True, width=120)
