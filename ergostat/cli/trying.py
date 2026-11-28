"""``ergostat projection try|review FILE.yaml`` and ``ergostat events shape|query|kinds`` (SPEC §5a, *Trying a
projection* and *The workbench*): a projection tried on the record (or on events given) before it is written, said in a
few lines; a draft reviewed as the workbench reviews it (its residual, unmapped paths, distributions, lifecycles, one
object's timeline); the stream's shape, the paths into its events, so the events themselves need not be read; the
indexed query's counts and samples; and the kinds of event a query's result holds, suggested. The same engines as the
page's and the MCP tools' (``spec/trying.py``, ``spec/workbench.py``, ``eventquery.py``), each a thin call."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .common import open_project, out_json


def register(sub, common) -> None:
    pj = sub.add_parser("projection", parents=[common], help="Try a projection before it is written: ergostat "
                        "projection try FILE.yaml", description="ergostat projection try FILE.yaml: the projection "
                        "in FILE (its body, or projections: {NAME: ...}) compiled with the model and folded over the "
                        "record (or --events), in memory: what it matched, what it could not key, what changed "
                        "nothing, what it refused, its items, fields and states, duplicates, and against --expected")
    pj.add_argument("what", choices=["try", "review"], help="try: the try's report; review: the workbench's review "
                    "(the residual, unmapped paths, each field's distribution, lifecycles, --item KEY's timeline)")
    pj.add_argument("file", metavar="FILE.yaml")
    pj.add_argument("--name", help="the projection's name (a body alone: default the file's name)")
    pj.add_argument("--events", metavar="FILE.jsonl", help="fold these events (one JSON a line: recorded events or "
                                                            "event lines) instead of the record")
    pj.add_argument("--expected", metavar="FILE.json", help="what each item should be: {KEY: {field: value}}")
    pj.add_argument("--item", metavar="KEY", help="that item's trace: each event, the handler that ran, each field "
                                                  "before -> after")
    pj.add_argument("--refused", metavar="REASON", help="the events refused for this reason (words of it; try only)")
    pj.add_argument("--limit", type=int, help="the most events read from the record (the newest; default 200,000)")
    pj.set_defaults(fn=cmd_projection)
    ev = sub.add_parser("events", parents=[common], help="The stream: ergostat events shape [--type GLOB] | query "
                        "QUERY | kinds QUERY", description="ergostat events shape: each path into the events' JSON "
                        "(data.detail.state), its types, how often it is there, how many values it takes and a few of "
                        "them. events query QUERY: the indexed query (type.startswith('aws.'), data.detail.state == "
                        "'running', has('i-0abc')): how many events it holds, how it was answered, the newest few. "
                        "events kinds QUERY: the kinds of event its result holds, suggested (a when: each, its count "
                        "and paths); --taken WHEN for each kind already accepted, in order")
    ev.add_argument("what", choices=["shape", "query", "kinds"])
    ev.add_argument("query", nargs="?", metavar="QUERY", help="query, kinds: the query (an expression over an event)")
    ev.add_argument("--type", help="shape: only events of this type (a glob ending in *)")
    ev.add_argument("--limit", type=int, help="shape: the newest N events (default 5,000); query: the events shown "
                                              "(default 5, at most 500)")
    ev.add_argument("--sample", type=int, help="query: evaluate N candidates picked at random and estimate the total")
    ev.add_argument("--compare", metavar="QUERY", help="query: an earlier query, to say what this one adds and drops")
    ev.add_argument("--taken", action="append", metavar="WHEN", help="kinds: a when: already accepted (repeat, in order)")
    ev.set_defaults(fn=cmd_events)


def _since(args):
    from ..web.projection_api import moment
    return moment(getattr(args, "since", None))


def cmd_projection(args) -> int:
    from ..spec import trying
    f = Path(args.file)
    try:
        text = f.read_text()
    except OSError as e:
        print(f"{f}: {e.strerror or e}", file=sys.stderr)
        return 2
    evs = expected = None
    try:
        if args.events:
            evs = [json.loads(x) for x in Path(args.events).read_text().splitlines() if x.strip()]
        if args.expected:
            expected = json.loads(Path(args.expected).read_text())
    except (OSError, ValueError) as e:
        print(f"{e}", file=sys.stderr)
        return 2
    p = open_project(args)
    if args.what == "review":
        return _review(p, args, text, evs, expected)
    name = args.name
    if name is None:
        got, _ = trying.body_of(None, text)
        name = got or f.stem
    try:
        r = trying.run(p, name, text, since=_since(args), events=evs, expected=expected, item=args.item,
                       refused=args.refused, limit=args.limit, system=getattr(args, "system", None) or "", keep=False)
    except trying.TryError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json:
        out_json(r)
    else:
        print(trying.text_of(r))
    return 0 if r["ok"] else 1


def _review(p, args, text, evs, expected) -> int:
    from ..eventquery import QueryError
    from ..spec import trying, workbench
    if getattr(p.model, "spec", None) is None:
        print("the model is an ergostat.toml: projections are declared in ergostat.yaml", file=sys.stderr)
        return 2
    got, _ = trying.body_of(args.name, text)
    ask = {"name": got or Path(args.file).stem, "yaml": text, "since": _since(args), "item": args.item,
           "events": evs, "expected": expected, "system": getattr(args, "system", None) or ""}
    try:
        r = workbench.review(p, {k: v for k, v in ask.items() if v is not None})
    except (trying.TryError, QueryError) as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json:
        out_json(r)
    else:
        print(review_text(r))
    return 0 if r["ok"] else 1


def cmd_events(args) -> int:
    from ..eventquery import QueryError
    from ..spec import trying
    p = open_project(args)
    if args.what != "shape" and not args.query:
        print(f"ergostat events {args.what} QUERY: the query (an expression over an event: type.startswith('aws.'))",
              file=sys.stderr)
        return 2
    try:
        if args.what == "shape":
            r = trying.stream_shape(p, args.type, _since(args), args.limit)
        elif args.what == "query":
            from ..eventquery import run as query
            ask = {"query": args.query, "since": _since(args), "limit": 5 if args.limit is None else args.limit,
                   "sample": args.sample, "compare": args.compare}
            r = query(p.events, {k: v for k, v in ask.items() if v is not None})
        else:
            from ..spec import workbench
            r = workbench.suggest(p, {k: v for k, v in {"query": args.query, "since": _since(args),
                                                        "taken": args.taken}.items() if v is not None})
    except (trying.TryError, QueryError) as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json:
        return out_json(r)
    print(trying.shape_text(r) if args.what == "shape" else query_text(r) if args.what == "query" else kinds_text(r))
    return 0


# ---- said at a glance (the CLI's; --json gives the answers whole)

def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x)


def _j(v, most: int = 160) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str, separators=(",", ":"))
    return s if len(s) <= most else s[:most - 1] + "…"


def _how(r: dict) -> str:
    if r.get("scanned"):
        return f"a scan of the newest {_n(r.get('read', 0))}" + (", capped" if r.get("capped") else "")
    how = "exact, from the index" if r.get("exact") else f"indexed, {_n(r.get('read', 0))} evaluated"
    return how + (", capped" if r.get("capped") else "") + (", estimated" if r.get("estimated") else "")


def query_text(r: dict) -> str:
    out = [f"{_n(r['total'])} of {_n(r['record'])} events  ({_how(r)}; {r['took_ms']} ms)  {r['query']}"]
    if r.get("compare"):
        c = r["compare"]
        out.append(f"  against {c['query']}: {_n(c['total'])}; this adds {_n(c['added'])}, drops {_n(c['dropped'])}")
    for e in r["events"]:
        out.append(f"  {e['seq']:>7} {e['type']:<18} {_j(e.get('data'), 180)}")
    if r["total"] > r["shown"]:
        out.append(f"  ... {_n(r['total'] - r['shown'])} more (--limit N; --json for them whole)")
    return "\n".join(out)


def kinds_text(r: dict) -> str:
    out = [f"{_n(r['count'])} events" + (f", {_n(r['untaken'])} untaken by the {len(r['taken'])} given"
                                          if r.get("taken") else "") + f"; {len(r['kinds'])} kinds suggested ({r['took_s']}s)"]
    for k in r["kinds"]:
        out.append(f"  {_n(k['count']):>8}  {k['name']:<24} when: {k['when']}")
        if k.get("paths"):
            out.append(f"            paths: {_j(', '.join(k['paths']), 200)}")
    if r.get("kinds_left"):
        out.append(f"  ... {r['kinds_left']} more kinds")
    return "\n".join(out)


def _shape(g: dict) -> str:
    return " ".join(f"{k}={_j(v, 60)}" for k, v in (g.get("shape") or {}).items())


def review_text(r: dict) -> str:
    """The review in a few lines: what each kind took, the objects, the residual, what is unmapped, each field."""
    if not r.get("ok"):
        return "\n".join([f"projection {r['projection']}: does not check"] +
                         [f"  {'line ' + str(e['line']) + ': ' if e.get('line') else ''}{e['message']}" for e in r["errors"]])
    rd, o = r["read"], r["objects"]
    out = [f"projection {r['projection']}: {_n(rd['events'])} events read ({rd.get('source', '')}"
           f"{', capped' if rd.get('capped') else ''}), {r['took_s']}s",
           f"  objects    {_n(o['count']):>8}  key {' / '.join(o['key'])}; {_n(o['one_event'])} with one event"
           + (f"; e.g. {', '.join(o['sample'][:3])}" if o.get("sample") else "")]
    if o.get("names"):
        out.append("  names      " + _j(", ".join(f"{k} = {v}" for k, v in list(o["names"].items())[:3]), 200))
    out.append("  kinds")
    for k in r["kinds"]:
        out.append(f"    {_n(k['count']):>8}  {k['name']:<22} {_n(k['objects'])} objects   when: {_j(k['when'] or '', 100)}")
    res = r["residual"]
    rem = res["remainder"]
    if rem.get("count"):
        out.append(f"  remainder  {_n(rem['count']):>8}  (no kind takes them)")
        out += [f"    {_n(k['count']):>8}  {_j(k['when'], 140)}" for k in rem.get("kinds", [])]
    nk = res["no_key"]
    if nk["count"]:
        out.append(f"  no key     {_n(nk['count']):>8}  " + ", ".join(f"{k} {_n(c)}" for k, c in nk["by_kind"].items()))
        for g in nk.get("groups", []):
            out.append(f"    {_n(g['count']):>8}  {g['kind']}: lacks {', '.join(g.get('lacks') or []) or '-'}; "
                       f"reads no value: {', '.join(g.get('no_value') or []) or '-'}")
    rf = res["refused"]
    if rf["count"]:
        out.append(f"  refused    {_n(rf['count']):>8}")
        out += [f"    {_n(g['count']):>8}  {_j(g['why'], 150)}  ({g.get('objects', '?')} objects)" for g in rf["groups"]]
    ct = res["contradictions"]
    if ct["count"]:
        out.append(f"  contradict {_n(ct['count']):>8}  ({ct['after_final']} after a final state)")
        out += [f"    {_n(x['count']):>8}  {x['field']}: {x['from']} -> {x['to']}  e.g. {', '.join(x['samples'])}"
                for x in ct["rare"]]
    sp = res["splits"]
    if sp["count"]:
        out.append(f"  splits?    {_n(sp['count']):>8}  (objects only kinds keyed another way wrote)")
        out += [f"    {_n(g['objects']):>8}  by {', '.join(g['kinds'])}; e.g. {', '.join(g['samples'])}"
                + (f" ~ {g['twin']}" if g.get("twin") else "") + (f"; differ: {', '.join(g['differ'])}" if g.get("differ") else "")
                for g in sp["groups"]]
    mg = res["merges"]
    if mg["count"]:
        out.append(f"  merges?    {_n(mg['count']):>8}  (a first field given two values: the key too coarse?)")
        out += [f"    {_n(f['objects']):>8}  {f['field']}  e.g. {', '.join(f['samples'])}" for f in mg["fields"]]
    d = r["duplicates"]
    if d.get("says"):
        out.append(f"  duplicates {d['says']}")
    um = r["unmapped"]
    if um["count"]:
        out.append(f"  unmapped   {_n(um['count']):>8}  paths no field, key or time: reads ({um['read']} events read; "
                   f"{um['ignored']} ignore: entries)")
        out += [f"    {_n(x['events']):>8}  {x['path']:<44} {', '.join(x['kinds'])}"[:160] for x in um["paths"]]
        if um.get("paths_left"):
            out.append(f"    ... {um['paths_left']} more paths")
    out.append("  fields")
    for f in r["fields"]:
        if "min" in f:
            vals = f"{f['min']} .. {f['max']}"
        elif "top" in f:
            vals = f"{f.get('distinct', '?')} distinct: " + ", ".join(f"{v} {c}" for v, c in f["top"][:4])
        elif "sizes" in f:
            vals = f"sizes {f['sizes']['min']}..{f['sizes']['max']}"
        else:
            vals = ""
        bad = f"  {f['not_its_type']} not its type" if f.get("not_its_type") else ""
        out.append(f"    {f['field']:<20} {_n(f['have']):>6}/{_n(f['objects'])}  {f['type']:<10} {vals}{bad}"[:170])
    for f, lc in r["lifecycles"].items():
        tr = ", ".join(f"{t['from'] or '(new)'}->{t['to']} {t['count']}" for t in lc["transitions"][:8])
        out.append(f"  lifecycle  {f}: now " + ", ".join(f"{k} {v}" for k, v in lc["now"].items()) + f"; {tr}"[:300])
    if "compared" in r:
        c = r["compared"]
        out.append(f"  vs saved   {c.get('saved')} -> {c.get('draft')} objects: {c.get('appear')} appear, "
                   f"{c.get('disappear')} disappear, {c.get('change')} change")
    if "expected" in r:
        x = r["expected"]
        i = x["items"]
        out.append(f"  expected   {i['found']}/{i['expected']} items found ({i['missing']} missing, {i['extra']} extra); "
                   f"fields {x['fields_matched_pct']}% right")
    if "timeline" in r:
        t = r["timeline"]
        if not t.get("found"):
            out.append(f"  timeline   {t['key']}: no such object")
        else:
            out.append(f"  timeline   {t['key']}: {t['events']} events, now {t.get('state')}")
            for s in t["steps"][:60]:
                what = "; ".join(f"{c['field']} {_j(c['before'], 30)} -> {_j(c['after'], 30)}" for c in s.get("changes", []))
                mv = f"{s['move']['from']}->{s['move']['to']} " if s.get("move") else ""
                out.append(f"    {s['type']:<18} {s.get('kind') or '-':<18} {mv}{what}"
                           f"{' REFUSED ' + s['refused'] if s.get('refused') else ''}{' (unchanged)' if s.get('unchanged') else ''}"[:200])
            if len(t["steps"]) > 60:
                out.append(f"    ... {len(t['steps']) - 60} more (--json)")
    return "\n".join(out)
