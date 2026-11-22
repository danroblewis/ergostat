"""The commands of the YAML model: ``check`` (as it compiles: errors, then findings, each with its
file and line), ``convert`` (TOML to YAML), ``block`` (a block, or a person's report on one) and a
person's reading of a manual sensor."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from .. import model as mdl
from ..show import c
from .common import out_json

CHECK_WAIT = 5.0     # seconds check waits for the extreme-conditions tests not kept (numbers/extremes_cache.py)


def here(args) -> Path:
    return Path(args.C).resolve() if getattr(args, "C", None) else Path.cwd()


def calibration(path: Path) -> list:
    """Each equation that fits its record worse than holding it at its mean (``fit.worse_than_mean``), when there is a
    record."""
    from .. import model as mdl
    from ..numbers import fit as ft
    from ..spec.load import Problem
    from ..store import Project, state_dir
    try:
        m = mdl.load(path.parent)
        if not state_dir(m.name, path.parent, make=False).is_dir():     # no record: nothing to fit (and none made)
            return []
        p = Project(m)
        return [Problem("finding", msg, None, "calibration-worse-than-mean", ref)
                for ref, msg in ft.worse_than_mean(p.model.spec, ft.compute(p)[2])] if p.measurements.count() else []
    except Exception:                             # a record that cannot be read says nothing here
        return []


def coherence_of(args, spec, findings) -> dict | None:
    """The coherence check (``coherence.py``) over the project's record, unless asked to leave it out."""
    if getattr(args, "no_coherence", False):
        return None
    from .. import coherence as co
    from ..durations import parse_duration
    window = parse_duration(args.since, "--since") if getattr(args, "since", None) else co.WINDOW   # (check: a day)
    return co.of_spec(spec, findings, window)


def order_unset(path: Path, spec) -> list:
    """A note for each ``takes: {order: FIELD}`` whose field no item of its kind holds in the record (SPEC §9.5): until
    an event sets it, every item is taken as one without it. Loose: a record not read says nothing."""
    from ..spec import items as its
    from ..spec.load import Problem
    from ..store import Project, state_dir
    asked = [(b, f.lstrip("-")) for b in spec.blocks.values() if b.takes for f in b.takes.order]
    if not asked:
        return []
    try:
        m = mdl.load(path.parent)
        p = Project(m) if state_dir(m.name, path.parent, make=False).is_dir() else None
        held = {k: {f for i in its.project(p.events, spec, k, transcript=False) for f in i.fields} if p else set()
                for k in {b.takes.kind for b, _ in asked}}
    except Exception:  # noqa: BLE001
        return []
    return [Problem("note", f"block {b.name}: takes.order {f}: no {b.takes.kind} in the record holds {f!r} yet, so each "
                    f"is taken as one without it (an event sets it: data {{\"{f}\": ...}})", b.where, "takes-order-unset",
                    f"block.{b.name}") for b, f in asked if f not in held[b.takes.kind]]


def check_yaml(args, path: Path) -> int:
    from ..remote.compose import fresh
    from ..spec import read
    from ..spec.about import findings as about
    from ..spec.findings import late
    with fresh():                                 # references into remotes checked against what each serves now
        spec, problems = read(path, extremes=False)
    errors = [p for p in problems if p.level == "error"]
    if not errors:                                # calibration on the record; the extremes kept, a few seconds for the rest
        problems += calibration(path) + order_unset(path, spec) + late(spec, wait=CHECK_WAIT)
        about(spec, problems)                     # last: every finding above carries the items about its part
    findings = [p for p in problems if p.level != "error"]
    if args.json:
        coh = coherence_of(args, spec, findings) if not errors else None
        return out_json({"ok": not errors, "errors": len(errors), "findings": sum(1 for p in findings if p.level != "note"),
                         "notes": sum(1 for p in findings if p.level == "note"),
                         "found": [{"level": p.level, "code": p.code, "message": p.message, "about": p.about,
                                    **({"id": f"{p.code}@{p.about}" if p.about else p.code} if p.level != "error" else {}),
                                    **({"items": p.items} if p.items else {}),
                                    "file": str(p.where.file) if p.where else None,
                                    "line": p.where.line if p.where else None} for p in problems],
                         "local": {k: str(w) for k, w in (getattr(spec, "local", None) or {}).items()},
                         **({"coherence": coh} if coh is not None else {})}) or (1 if errors else 0)

    def n(k, word):
        return f"{k} {word}" + ("" if k == 1 else "s")
    aux = f"{len(spec.auxiliaries)} auxiliar{'y' if len(spec.auxiliaries) == 1 else 'ies'}"
    head = " · ".join([n(len(spec.stocks), "stock"), n(len(spec.flows), "flow"),
                       *([aux] if spec.auxiliaries else []), n(len(spec.sensors()), "sensor"),
                       n(len(spec.goals), "goal"), n(len(spec.blocks), "block"), n(len(spec.agents), "agent"),
                       n(len(spec.files), "file")])
    print(f"{c('error', 'bad') if errors else c('ok', 'ok')}   {head}")
    for k, w in (getattr(spec, "local", None) or {}).items():         # this machine's settings (SPEC §2)
        print(c(f"{k}: from {w}, this machine's own", "dim"))
    for name, r in (getattr(spec, "remotes", None) or {}).items():     # each remote system (SPEC §4c)
        print(c(f"remote {name}: {r['url']}, " + (f"model version {r['version']}, {len(r['parts'])} parts read in"
                                                  if r.get("version") else "its model not read"), "dim"))
    for inst, u in (getattr(spec, "uses", None) or {}).items():       # each use of a fetched library's template (§2a)
        if u.get("library"):
            print(c(f"use {inst}: template {u['template']} from library {u['library']} ({u['path']})", "dim"))
    for p in errors:
        print(f"{c('error', 'bad')}  {p}")
    if errors:
        for p in findings:                       # how YAML read a value often explains an error beside it
            if p.code == "yaml-1.1":
                print(f"{c(p.code, 'warn')}  {p}")
        print(c(f"{n(len(errors), 'error')}: ergostat will not run this model until they are fixed", "dim"))
        return 1
    loops = spec.loops()
    closed = [lp for lp in loops if lp.closes]
    print(c(f"{len(closed)} of {n(len(loops), 'goal')} closed by a loop ergostat can see", "dim"))
    notes = [p for p in findings if p.level == "note"]
    for p in findings:
        if p.level != "note":
            print(f"{c(p.code or 'finding', 'warn')}  {p}")
    if notes:                                   # the craft (docs/MODELLING-WELL.md): work for modelling, not wrong
        print(c(f"\n{n(len(notes), 'note')} on the craft (docs/MODELLING-WELL.md; ergostat check --json lists each, "
                f"and the modelling loop takes them up)", "dim"))
        by: dict[str, list] = {}
        for p in notes:
            by.setdefault(p.code, []).append(p)
        for code, ps in by.items():
            names = ", ".join(x.about.split(".", 1)[-1] for x in ps[:8]) + (f" and {len(ps) - 8} more" if len(ps) > 8 else "")
            print(f"{c(code, 'dim')}  {len(ps)}: {names}" if len(ps) > 1 else f"{c(code, 'dim')}  {ps[0]}")
    coh = coherence_of(args, spec, [p for p in findings if p.level != "note"])
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
    if getattr(args, "restart", False):                # a daemon given up, revived (SPEC §9.7): the block's, or one by name
        from ..spec.engine import RESTART_ASKED
        d = (spec.blocks[args.name].params.get("daemon") if args.name in spec.blocks else None) or args.name
        if d not in spec.daemons:
            print(f"{args.name}: no daemon (daemons: {', '.join(spec.daemons) or 'none'})", file=sys.stderr)
            return 2
        p.events.add(RESTART_ASKED, item=d, source="person", data={"note": args.note or ""})
        print(f"asked: daemon {d} starts afresh, its restarts forgotten (if ergostat is running here)")
        return 0
    b = spec.blocks.get(args.name)
    if b is None:
        print(f"no block {args.name!r}" + (f" (blocks: {', '.join(spec.blocks)})" if spec.blocks else ""), file=sys.stderr)
        return 2
    if getattr(args, "now", False):
        return run_now(p, b, args)
    if getattr(args, "check_warm", None):            # a warm daemon's promise, checked on one input (SPEC §9.7)
        d = spec.daemons.get(b.params.get("daemon") or "")
        if d is None or not d.warm:
            print(f"block {b.name}: its daemon is not warm (warm: true)", file=sys.stderr)
            return 2
        from ..daemons.warmcheck import check
        from ..spec.engine import callback_env
        try:
            given = json.loads(Path(args.check_warm).read_text())
        except (OSError, ValueError) as e:
            print(f"--check-warm {args.check_warm}: cannot be read as JSON ({e})", file=sys.stderr)
            return 2
        if not isinstance(given, dict):
            print(f"--check-warm {args.check_warm}: a run's input is a JSON object, not {type(given).__name__}",
                  file=sys.stderr)
            return 2
        print(f"running {d.run} for real, four times: twice on one process, once on each of two others; without what "
              f"the engine prepares for a run (no workdir or workspace, no action policy) and with only ERGOSTAT_RUN and "
              f"ERGOSTAT_ITEM in each item's env")
        rc, why = check(d, spec.root, callback_env(spec, p.dir), given)
        print(why)
        return rc
    if args.done is not None:
        if b.type != "person":
            print(f"block {b.name} is a {b.type}: it reports itself; --done is a person's report", file=sys.stderr)
            return 2
        from ..inbox.answer import person_done
        print(person_done(p, spec, b, args.done, args.note))
        return 0
    from ..spec.triggers import own
    if (args.approve or getattr(args, "reset", False)) and own(p.events, b.name):
        print(f"a run of {b.name} answers for it to no one: its approvals and its breaker are the owner's", file=sys.stderr)
        return 2
    if args.approve:
        if b.mode != "advise":
            print(f"block {b.name} is not in advise mode: nothing waits for approval", file=sys.stderr)
            return 2
        ask = p.events.query(n=1, item=b.name, type="block.advised") if b.on is not None else []
        p.events.add("block.approved", item=b.name, source="person",
                     data={"note": args.note or "", **({"ask": ask[0]["seq"]} if ask else {})})
        print(f"approved: {b.name} runs " + (f"on event {ask[0]['data'].get('event_type')}" if ask else "with its latest command")
              + " (if ergostat is running here)")
        return 0
    if getattr(args, "reset", False):
        if b.on is None:
            print(f"block {b.name} is not started by events: it has no breaker", file=sys.stderr)
            return 2
        p.events.add("trigger.reset", item=b.name, source="person", data={"note": args.note or ""})
        print(f"reset: {b.name}'s events start it again (if ergostat is running here)")
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
    s = _sensor(p, name)
    if s is None:
        return 2
    if not s.manual:
        how = "run" if s.run else "items" if s.items else "query"
        print(f"sensor {name} reads itself ({how}); only a manual: true sensor takes a person's "
              f"readings", file=sys.stderr)
        return 2
    p.measurements.add(s.series, float(value))
    print(f"recorded: {s.of.name}.{s.name} = {value:g}")
    return 0


def _sensor(p, name: str):
    from ..spec.ir import Ref
    spec = p.model.spec
    of, _, sensor = name.partition(".")
    s = None
    for kind in ("stock", "flow", "auxiliary"):
        s = s or spec.sensor(Ref(kind, of, sensor or "main"))
    if s is None:
        print(f"no sensor {name!r}: name it as its stock (or flow) and sensor, like inbox.eyes", file=sys.stderr)
    return s


def _num(x) -> float | None:
    """A finite number from JSON (not a boolean, nor an integer too large for a float), else None."""
    return float(x) if isinstance(x, float) and math.isfinite(x) or type(x) is int and abs(x) < 1e300 else None


def backfill(args) -> int | None:
    """``sensor PART.SENSOR --backfill FILE`` (readings at past times, written whole or not at all, each kept in the
    measurements' ledger so it is never written twice) and ``--backfilled`` (that ledger's backfills of the series)."""
    import time

    from .common import open_project
    if args.topic != "sensor" or (getattr(args, "backfill", None) is None and not getattr(args, "backfilled", False)):
        return None
    p = open_project(args)
    if getattr(p.model, "spec", None) is None:
        print("backfill is for a YAML model's sensors", file=sys.stderr)
        return 2
    s = _sensor(p, args.name or "")
    if s is None:
        return 2
    name = f"{s.of.name}.{s.name}"
    if args.backfilled:
        got = p.measurements.backfills(s.series)
        if args.json:
            return out_json(got)
        for b in got:
            day = [time.strftime("%Y-%m-%d %H:%M", time.localtime(b[k])) if b[k] else "" for k in ("written_at", "first", "last")]
            print(f"{day[0]}  {b['count']} readings{f', {day[1]} to {day[2]}' if b['count'] else ''}"
                  f"  from {b['from'] or '(not said)'}")
        print(f"{len(got)} backfill{'' if len(got) == 1 else 's'} of {name}")
        return 0
    derived = "items" if s.items else "changes" if s.changes else "builtin" if s.builtin else None
    if derived:
        print(f"sensor {name} is derived by ergostat ({derived}): only a sensor that records a value (run, query, "
              f"manual, daemon) takes backfilled readings", file=sys.stderr)
        return 2
    try:
        text = sys.stdin.read() if args.backfill == "-" else Path(args.backfill).read_text()
    except (OSError, UnicodeDecodeError) as e:
        print(f"cannot read {args.backfill}: {e}", file=sys.stderr)
        return 2
    rows, now = [], time.time()
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            at, value = _num(r["at"]), _num(r["value"])
        except (ValueError, TypeError, KeyError, IndexError):
            r = at = value = None
        why = "not a JSON object with at and value" if r is None else "at and value must be finite numbers" \
            if at is None or value is None else "at is in the future" if at > now else None
        if why:
            print(f"refused, nothing written: line {i}: {why}", file=sys.stderr)
            return 2
        rows.append((at, value))
    try:
        got = p.measurements.backfill(s.series, rows, args.from_)
    except ValueError as e:                              # more than the store takes at once
        print(f"refused, nothing written: {e}", file=sys.stderr)
        return 2
    p.events.add("sensor.backfilled", source="ergostat", data={
        "sensor": name, "written": got["count"], "skipped": got["skipped"], "repeated": got["repeated"],
        "first": got["first"], "last": got["last"], "from": args.from_, "backfill": got["id"]})
    if args.json:
        return out_json({k: got[k] for k in ("id", "count", "skipped", "repeated", "first", "last", "from")})
    print(f"backfilled {name}: {got['count']} written, {got['skipped']} skipped (backfilled before)"
          + (f", {got['repeated']} at a time another line had (the last kept)" if got["repeated"] else ""))
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
    out: dict = {}
    moved = e.run_block(b, "by hand", outcome=out)
    if out.get("refused"):                                # nothing started: no earlier run reported as this one
        print(c(f"refused: budget: {out['refused']}", "warn"))
        return 1
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
