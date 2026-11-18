"""The commands of the YAML model: ``check`` (as it compiles: errors, then findings, each with its
file and line), ``convert`` (TOML to YAML), ``block`` (a block, or a person's report on one) and a
person's reading of a manual sensor."""

from __future__ import annotations

import sys
from pathlib import Path

from .. import model as mdl
from ..show import c
from .common import out_json


def here(args) -> Path:
    return Path(args.C).resolve() if getattr(args, "C", None) else Path.cwd()


def coherence_of(args, spec, findings) -> dict | None:
    """The coherence check (``coherence.py``) over the project's record, unless asked to leave it out."""
    if getattr(args, "no_coherence", False):
        return None
    from .. import coherence as co
    from ..durations import parse_duration
    window = parse_duration(args.since, "--since") if getattr(args, "since", None) else co.WINDOW   # (check: a day)
    return co.of_spec(spec, findings, window)


def check_yaml(args, path: Path) -> int:
    from ..spec import read
    spec, problems = read(path)
    errors = [p for p in problems if p.level == "error"]
    findings = [p for p in problems if p.level != "error"]
    if args.json:
        coh = coherence_of(args, spec, findings) if not errors else None
        return out_json({"ok": not errors, "errors": len(errors), "findings": len(findings),
                         "found": [{"level": p.level, "code": p.code, "message": p.message, "about": p.about,
                                    **({"id": f"{p.code}@{p.about}" if p.about else p.code} if p.level != "error" else {}),
                                    "file": str(p.where.file) if p.where else None,
                                    "line": p.where.line if p.where else None} for p in problems],
                         **({"coherence": coh} if coh is not None else {})}) or (1 if errors else 0)

    def n(k, word):
        return f"{k} {word}" + ("" if k == 1 else "s")
    aux = f"{len(spec.auxiliaries)} auxiliar{'y' if len(spec.auxiliaries) == 1 else 'ies'}"
    head = " · ".join([n(len(spec.stocks), "stock"), n(len(spec.flows), "flow"),
                       *([aux] if spec.auxiliaries else []), n(len(spec.sensors()), "sensor"),
                       n(len(spec.goals), "goal"), n(len(spec.blocks), "block"), n(len(spec.agents), "agent"),
                       n(len(spec.files), "file")])
    print(f"{c('error', 'bad') if errors else c('ok', 'ok')}   {head}")
    for p in errors:
        print(f"{c('error', 'bad')}  {p}")
    if errors:
        print(c(f"{n(len(errors), 'error')}: ergostat will not run this model until they are fixed", "dim"))
        return 1
    loops = spec.loops()
    closed = [lp for lp in loops if lp.closes]
    print(c(f"{len(closed)} of {n(len(loops), 'goal')} closed by a loop ergostat can see", "dim"))
    for p in findings:
        print(f"{c(p.code or 'finding', 'warn')}  {p}")
    coh = coherence_of(args, spec, findings)
    if coh is not None and coh["kinds"]:
        from ..coherence import lines
        print(c("\nCoherence: the Process, Dynamics and Blocks views held against each other, over the record", "dim"))
        for style, line in lines(coh):
            print(c(line, "bold") if style == "head" else c(line, style) if style != "warn" else
                  f"{c(line.split('  ', 1)[0], 'warn')}  {line.split('  ', 1)[1]}" if "  " in line else c(line, "warn"))
    return 0


def cmd_convert(args) -> int:
    from ..spec.convert import convert
    start = here(args)
    toml = next((d / mdl.FILE for d in (start, *start.parents) if (d / mdl.FILE).is_file()), None)
    if toml is None:
        print(f"no {mdl.FILE} here or above {start}", file=sys.stderr)
        return 2
    m = mdl.parse(__import__("tomllib").loads(toml.read_text(encoding="utf-8")), toml, default_name=toml.parent.name)
    text, notes = convert(m)
    if args.stdout:
        print(text, end="")
        return 0
    dest = toml.with_name(mdl.YAML)
    if dest.exists() and not args.force:
        print(f"{dest} exists; --force to replace it, or --stdout to see the conversion", file=sys.stderr)
        return 1
    dest.write_text(text, encoding="utf-8")
    print(f"wrote {dest} ({len(text.splitlines())} lines; {toml.name} was {len(toml.read_text().splitlines())})")
    if notes:
        print(c(f"{len(notes)} thing{'s' if len(notes) > 1 else ''} to look at, listed at the top of the file", "warn"))
    print(c(f"ergostat now reads {dest.name} (it wins over {toml.name}); remove {toml.name} when you are done", "dim"))
    from ..spec import read
    _, problems = read(dest)
    for p in problems:
        if p.level == "error":
            print(f"{c('error', 'bad')}  {p}")
    return 0


def cmd_block(args) -> int:
    from .common import open_project
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("blocks belong to the YAML model (ergostat.yaml); this project is still ergostat.toml (ergostat convert)",
              file=sys.stderr)
        return 2
    if not args.name:
        rows = []
        for b in spec.blocks.values():
            ins = ", ".join(str(r) for r in b.inputs.values()) or (f"goal.{b.goal}" if b.goal else "")
            outs = ", ".join(str(r) for r in b.targets())
            rows.append((b.name, b.type + (' (implied)' if b.implied else ''), spec.role(b), ins, outs))
        if args.json:
            return out_json([dict(zip(("name", "type", "role", "in", "out"), r, strict=True)) for r in rows])
        from ..show import table
        print(table(["BLOCK", "TYPE", "ROLE", "IN", "OUT"], rows))
        return 0
    if getattr(args, "stop", False):                   # a block removed from the model may still be finishing its run
        from ..messages.route import running
        from ..spec.engine import STOP_ASKED
        if not any(r["block"] == args.name for r in running(p, spec)):
            print(f"{args.name}: no run under way to stop", file=sys.stderr)
            return 2
        p.events.add(STOP_ASKED, item=args.name, source="person", data={"note": args.note or ""})
        print(f"asked: {args.name}'s run under way stops (if ergostat is running here); nothing else changes")
        return 0
    b = spec.blocks.get(args.name)
    if b is None:
        print(f"no block {args.name!r}" + (f" (blocks: {', '.join(spec.blocks)})" if spec.blocks else ""), file=sys.stderr)
        return 2
    if getattr(args, "now", False):
        return run_now(p, b, args)
    if args.done is not None:
        if b.type != "person":
            print(f"block {b.name} is a {b.type}: it reports itself; --done is a person's report", file=sys.stderr)
            return 2
        from ..spec.legacy import valve_name
        flows = [t.name for t in b.targets() if t.kind == "flow"]
        run = p.events.add("agent.ran", item=b.name, source="person", data={"done": args.done, "note": args.note or ""})
        for f in flows[:1]:
            if args.done > 0:
                p.events.add("valve.opened", item=valve_name(spec, b.name, f), source=b.name, causedby=run["id"],
                             data={"amount": float(args.done), "flow": f, **({"note": args.note} if args.note else {})})
        print(f"recorded: {b.name} moved {args.done:g}" + (f" along flow.{flows[0]}" if flows else ""))
        return 0
    if args.approve:
        if b.mode != "advise":
            print(f"block {b.name} is not in advise mode: nothing waits for approval", file=sys.stderr)
            return 2
        p.events.add("block.approved", item=b.name, source="person", data={"note": args.note or ""})
        print(f"approved: {b.name} runs with its latest command (if ergostat is running here)")
        return 0
    info = {"name": b.name, "type": b.type, "role": spec.role(b), "in": {k: str(v) for k, v in b.inputs.items()},
            "out": {k: [str(r) for r in v] for k, v in b.outputs.items()}, "agent": b.agent,
            "where": str(b.where) if b.where else None,
            "runs": p.events.query(n=5, item=b.name, type="agent.ran"),
            "commanded": p.events.query(n=5, item=b.name, type="block.commanded")}
    if args.json:
        return out_json(info)
    print(f"block {b.name} · {b.type} · {spec.role(b)}" + (f" · on {b.agent}" if b.agent else "") +
          c(f"   {b.where}" if b.where else "", "dim"))
    if b.goal:
        print(f"  goal  goal.{b.goal}")
    if b.type == "person":
        print(f"  asks  {b.params.get('ask', '')}")
    for k, r in b.inputs.items():
        print(f"  in    {r}" + (c(f"  ({k})", "dim") if k not in ("in",) else ""))
    for k, rs in b.outputs.items():
        for r in rs:
            print(f"  out   {r}" + (c(f"  ({k})", "dim") if k != "out" else ""))
    for e in info["commanded"][-3:]:
        print(c(f"  commanded {e['data'].get('amount')}" + (f" (asked {e['data']['asked']})" if 'asked' in e['data'] else ""),
                "dim"))
    for e in info["runs"][-3:]:
        d = e["data"]
        print(c(f"  ran: moved {d.get('moved', {})} in {d.get('seconds', '?')}s", "dim"))
    return 0


def read_manual(p, name: str, value: float) -> int:
    """``ergostat sensor STOCK.SENSOR --read V`` on a YAML model: a manual sensor's reading."""
    from ..spec.ir import Ref
    spec = p.model.spec
    of, _, sensor = name.partition(".")
    s = None
    for kind in ("stock", "flow", "auxiliary"):
        s = s or spec.sensor(Ref(kind, of, sensor or "main"))
    if s is None:
        print(f"no sensor {name!r}: name it as its stock (or flow) and sensor, like inbox.eyes", file=sys.stderr)
        return 2
    if not s.manual:
        how = "run" if s.run else "items" if s.items else "query"
        print(f"sensor {name} reads itself ({how}); only a manual: true sensor takes a person's "
              f"readings", file=sys.stderr)
        return 2
    p.measurements.add(s.series, float(value))
    print(f"recorded: {s.of.name}.{s.name} = {value:g}")
    return 0


def cmd_findings(args) -> int:
    """``ergostat findings``: everything worth a look, from the model (missing feedback, ...) and from
    the record (heading for a limit, saturating, not answering, a critical goal decaying)."""
    from ..durations import parse_duration
    from ..spec import watch
    from .common import open_project
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("findings are the YAML model's (ergostat convert); for this one: ergostat check", file=sys.stderr)
        return 2
    window = parse_duration(args.since, "--since") if args.since else watch.WINDOW
    found = [x for x in p.model.problems if x.level != "error"] + watch.find(p, spec, window)
    if args.json:
        return out_json([{"code": f.code, "about": f.about, "message": f.message,
                          "file": str(f.where.file) if f.where else None, "line": f.where.line if f.where else None}
                         for f in found])
    if not found:
        print(c("nothing found", "ok"))
    for f in found:
        print(f"{c(f.code, 'warn')}  {f}")
    return 0


def cmd_explain(args) -> int:
    """``ergostat explain [PART]``: the model, or one part, in sentences."""
    from ..spec.explain import explain
    from .common import open_project
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("explain reads the YAML model (ergostat convert)", file=sys.stderr)
        return 2
    try:
        text = explain(spec, args.name, p)
    except KeyError as e:
        print(e.args[0], file=sys.stderr)
        return 2
    if args.json:
        return out_json({"part": args.name, "text": text})
    print(text)
    return 0


def cmd_discover(args) -> int:
    """``ergostat discover prometheus URL`` (a draft model from what a Prometheus holds) and
    ``ergostat discover loops`` (loops in the record: flows that follow their stock's level)."""
    from ..spec import discover as dc
    what = args.name or "loops"
    if what == "prometheus":
        if not args.url:
            print("ergostat discover prometheus --url http://prometheus:9090 [--match REGEX]", file=sys.stderr)
            return 2
        try:
            text, _ = dc.from_prometheus(args.url, args.match)
        except Exception as e:
            print(f"prometheus at {args.url}: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        print(text, end="")
        return 0
    if what != "loops":
        print("discover what? prometheus (a draft model from its series) or loops (from the record)", file=sys.stderr)
        return 2
    from ..durations import parse_duration
    from .common import open_project
    p = open_project(args)
    spec = getattr(p.model, "spec", None)
    if spec is None:
        print("discover reads the YAML model (ergostat convert)", file=sys.stderr)
        return 2
    window = parse_duration(args.since, "--since") if args.since else 6 * 3600.0
    found = dc.loops(p, spec, window)
    if args.json:
        return out_json(found)
    if not found:
        print(c("not enough readings yet to say (each stock needs a few hours of them, and its flows measured)", "dim"))
    for f in found:
        tag = "loop" if f["kind"] == "loop" and f["known"] else "unwritten" if f["kind"] == "loop" else "unanswered"
        print(f"{c(tag, 'ok' if tag == 'loop' else 'warn')}  {f['says']}")
    prop = dc.proposal(found, spec)
    if prop:
        print(c("\nto write them down (fill in the setpoints and name what acts):\n", "dim") + prop)
    return 0


def run_now(p, b, args) -> int:
    """``ergostat block NAME --now [--command N]``: one run, at once, recorded like any other: what
    it was given, and what it said."""
    if not b.machine:
        print(f"block {b.name} is {'built in: ergostat computes it' if b.builtin else 'external: ergostat never runs it'}",
              file=sys.stderr)
        return 2
    if b.type == "person":
        print(f"block {b.name} is a person's: they report with ergostat block {b.name} --done N", file=sys.stderr)
        return 2
    from ..spec.engine import Engine
    e = Engine(p, say=lambda s: print(c(s, "warn")))
    e._initial()
    e.measure()
    for name, g in p.model.spec.goals.items():               # the errors, without recording a crossing
        y = e.signals.get(str(g.of))
        if y is not None:
            e.signals[f"goal.{name}.error"] = g.hold.error(y)
    if args.command is not None:                          # stand in for its commander
        for cmd in p.model.spec.commanders_of(b.name):
            if cmd.builtin:
                e.signals[f"block.{cmd.name}"] = args.command
            else:
                e.outputs.setdefault(cmd.name, {})["out"] = args.command
    ctx = e.context(b, "by hand")
    print(c("given: " + __import__("json").dumps(ctx), "dim"))
    moved = e.run_block(b, "by hand")
    last = p.events.query(n=1, item=b.name, type="agent.*")
    d = last[-1]["data"] if last else {}
    print(f"{'failed' if last and last[-1]['type'] == 'agent.failed' else 'ran'} in {d.get('seconds', '?')}s"
          + (f": moved {', '.join(f'{v:g} along flow.{k}' for k, v in d.get('moved', {}).items())}" if moved else
             ": moved nothing") + (f" ({d['note']})" if d.get("note") else ""))
    for r in p.events.query(n=5, item=b.name, type="agent.refused", since=last[-1]["time"] - 60 if last else None):
        print(c(f"refused: {r['data']['why']}", "warn"))
    from ..runner import log_path
    print(c(f"its log: {log_path(p, b.name)}", "dim"))
    return 1 if last and last[-1]["type"] == "agent.failed" else 0
