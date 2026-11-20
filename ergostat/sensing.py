"""How a sensor is said on the diagrams: what it reads and how often ("items: alert, fired, every 5 s",
"prometheus: sum(queue_depth), every 30 s", "Jira: FF tickets approved, every 5 min"), the collectors
that turn an outside system into the items a count reads, and where an inflow from outside comes from.
Worked out from the model, never written (SPEC §6)."""

from __future__ import annotations

from .spec.ir import Sensor, Spec


def every_words(sec: float | None) -> str:
    """``5 s``, ``5 min``, ``2 h``, ``1 d``: a period as a reader says it."""
    if not sec:
        return ""
    for size, word in ((86400, "d"), (3600, "h"), (60, "min")):
        if sec >= size:
            return f"{sec / size:.3g} {word}"
    return f"{sec:.3g} s"


def how_often(x: Sensor) -> str:
    """``every 5 s``; ``on cron 0 9 * * *``; ``read by hand``."""
    if x.manual:
        return "read by hand"
    if x.cron:
        return f"on cron {x.cron}"
    return f"every {every_words(x.every)}" if x.every else ""


def _command(run: str) -> str:
    """``python3 bin/watch.py alert`` as ``watch.py alert``: the program and its arguments, its interpreter
    and folders left out."""
    words = run.split()
    if words and words[0].split("/")[-1].startswith(("python", "node", "bash", "sh", "ruby", "perl", "uv")) and len(words) > 1:
        words = words[1:]
    if len(words) > 1 and words[0] == "-m":                 # a module run: ergostat's own library says its step and its name
        mod, rest = words[1], words[2:]
        if mod.startswith("ergostat."):
            sub = next((w for w in rest if not w.startswith("-")), "")
            name = rest[rest.index("--name") + 1] if "--name" in rest[:-1] else ""
            return " ".join(x for x in (sub, name) if x) or mod
        words = [mod.split(".")[-1], *rest]
    if words:
        words[0] = words[0].split("/")[-1]
    return " ".join(words)


def command(spec: Spec, x: Sensor) -> str:
    """The program a sensor reads by: its ``run:``, or its daemon's (SPEC §9.7)."""
    return x.run or (spec.daemons[x.daemon].run if x.daemon in spec.daemons else "")


def short(text: str, n: int = 32) -> str:
    """At most ``n`` characters, an ellipsis where it is cut (the whole of it is in the panel)."""
    return text if len(text) <= n else text[:n - 1] + "…"


def what(spec: Spec, x: Sensor) -> str:
    """What a sensor reads, without how often: ``items: alert, fired``; ``prometheus: <query>``; its
    description when it says it (``Jira: FF tickets approved``); else its command."""
    if x.items:
        q = x.items
        kind = q.get("kind") or ""
        st = q.get("state")
        if q.get("entering") or q.get("leaving"):
            moving = f"entering {q['entering']}" if q.get("entering") else f"leaving {q['leaving']}"
            which = f"{moving}, over {every_words(q.get('over') or 3600.0)}"
        else:
            which = ", ".join(st) if isinstance(st, list) else (st or "any state")
        if q.get("measure") == "oldest":
            which = f"the oldest {which}"
        where = q.get("where") or {}
        cond = "".join(f", {k} = {', '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in where.items())
        return f"items: {kind}, {which}{cond}"
    if x.query:
        src = spec.sources.get(x.query.get("source") or "")
        head = src.type if src is not None and src.type not in ("command",) else (x.query.get("source") or "query")
        body = x.query.get("promql") or ", ".join(f"{k} {v}" for k, v in x.query.items() if k != "source")
        return f"{head}: {body}"
    if x.changes:
        c = x.changes
        return f"changes of {c.get('stock') or x.of.name}: {c.get('what') or 'net'}, over {every_words(c.get('over') or 3600.0)}"
    if x.builtin:
        return f"ergostat: {x.builtin.removeprefix('ergostat.')}"
    if x.manual:
        return x.description or "a person's reading"
    if x.description and len(x.description) <= 60:
        return x.description
    return f"{'daemon' if x.daemon else 'run'}: {short(_command(command(spec, x)))}"   # (the whole command: in its panel)


def reads(spec: Spec, x: Sensor) -> str:
    """What a sensor reads and how often: ``items: alert, fired, every 5 s``."""
    w, h = what(spec, x), how_often(x)
    if x.manual:
        return w if w == "a person's reading" else f"{w}, read by hand"
    return f"{w}, {h}" if h else w


def collectors(spec: Spec) -> dict[str, list[Sensor]]:
    """For each kind of item, the sensors taken to collect it: a command or a query on a flow that brings
    a stock counted by that kind in from outside. It polls the outside system and records what it saw
    as events about items (SPEC §6), so the counts of that kind are only as fresh as it is."""
    out: dict[str, list[Sensor]] = {}
    for st in spec.stocks.values():
        kinds = {x.items.get("kind") for x in st.sensors.values() if x.items and x.items.get("kind")}
        if not kinds:
            continue
        for f in spec.flows.values():
            if f.target != st.name or f.source:
                continue
            for x in f.sensors.values():
                if x.commands or x.query:
                    for k in sorted(kinds):
                        if all(y is not x for y in out.get(k, [])):
                            out.setdefault(k, []).append(x)
    return out


def source_name(x: Sensor, spec: Spec) -> str | None:
    """The outside system a sensor reads, where the model says it: a query's source, or what its
    description names before a colon (``Jira: FF tickets approved``)."""
    if x.query and x.query.get("source"):
        return x.query["source"]
    head, sep, _ = (x.description or "").partition(":")
    if sep and head.strip() and len(head.split()) <= 3:
        return head.strip()
    return None


def comes_from(spec: Spec, flow: str) -> str | None:
    """Where an inflow from outside comes from, where the model knows it: the block outside the control
    system that drives it (an external block, the world), its agent, or the system its sensor reads."""
    f = spec.flows.get(flow)
    if f is None or f.source:
        return None
    commanded = {t.name for b in spec.blocks.values() for t in b.targets() if t.kind == "block"}
    for b in spec.blocks.values():
        world = not b.reads() and b.name not in commanded
        if any(t.kind == "flow" and t.name == flow for t in b.targets()) and (b.type == "external" or world):
            ag = spec.agents.get(b.agent) if b.agent else None
            return ag.name if ag is not None and b.type == "external" else b.name
    for x in f.sensors.values():
        n = source_name(x, spec)
        if n:
            return n
    return None
