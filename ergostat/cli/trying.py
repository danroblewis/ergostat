"""``ergostat projection try FILE.yaml`` and ``ergostat events shape`` (SPEC §5a, *Trying a projection*): a projection
tried on the record (or on events given) before it is written, said in a few lines; and the stream's shape, the paths
into its events, so the events themselves need not be read. The same engine as the page's and the MCP tools'
(``spec/trying.py``)."""

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
    pj.add_argument("what", choices=["try"])
    pj.add_argument("file", metavar="FILE.yaml")
    pj.add_argument("--name", help="the projection's name (a body alone: default the file's name)")
    pj.add_argument("--events", metavar="FILE.jsonl", help="fold these events (one JSON a line: recorded events or "
                                                            "event lines) instead of the record")
    pj.add_argument("--expected", metavar="FILE.json", help="what each item should be: {KEY: {field: value}}")
    pj.add_argument("--item", metavar="KEY", help="that item's trace: each event, the handler that ran, each field "
                                                  "before -> after")
    pj.add_argument("--refused", metavar="REASON", help="the events refused for this reason (words of it)")
    pj.add_argument("--limit", type=int, help="the most events read from the record (the newest; default 200,000)")
    pj.set_defaults(fn=cmd_projection)
    ev = sub.add_parser("events", parents=[common], help="The stream's shape: ergostat events shape [--type GLOB]",
                        description="ergostat events shape: each path into the events' JSON (data.detail.state), its "
                                    "types, how often it is there, how many values it takes and a few of them")
    ev.add_argument("what", choices=["shape"])
    ev.add_argument("--type", help="only events of this type (a glob ending in *)")
    ev.add_argument("--limit", type=int, help="the newest N events (default 5,000)")
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


def cmd_events(args) -> int:
    from ..spec import trying
    p = open_project(args)
    try:
        r = trying.stream_shape(p, args.type, _since(args), args.limit)
    except trying.TryError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.json:
        return out_json(r)
    print(trying.shape_text(r))
    return 0
