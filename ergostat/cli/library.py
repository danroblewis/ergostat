"""``ergostat library fetch [NAME...] [--update]`` (SPEC §2a): the main file's ``libraries:`` read live with the
loader's own YAML reader, checked, and each library fetched and locked (``library/fetch.py``). It never opens the
project and never runs on the last good model: a main file that does not read stops it before any git process."""

from __future__ import annotations

import sys

from .spec_cmds import here


def register(sub, common) -> None:
    lp = sub.add_parser("library", parents=[common], help="Libraries fetched by git URL: fetch [NAME...] [--update]",
                        description="ergostat library fetch [NAME...] [--update]: clone each library in libraries: "
                                    "into .libraries/NAME and pin it in libraries.lock (SPEC §2a)")
    lp.add_argument("what", choices=["fetch"])
    lp.add_argument("names", nargs="*", metavar="NAME", help="only these libraries (leave out: all)")
    lp.add_argument("--update", action="store_true", help="resolve each version again, even an unchanged one")
    lp.set_defaults(fn=cmd_library)


def cmd_library(args) -> int:
    from ..library import fetch, sources
    from ..spec.load import FILE, find, read_file
    main = find(here(args))
    if main is None:
        print(f"no {FILE} here or above", file=sys.stderr)
        return 2
    problems: list = []
    data = read_file(main, problems)
    bad = [p for p in problems if p.level == "error"]
    if bad or not isinstance(data, dict):
        print(f"{main.name}: {bad[0] if bad else 'not a map of sections'}: fix it first (nothing fetched)",
              file=sys.stderr)
        return 2
    if data.get("libraries") is None:
        print(f"{main.name} has no libraries:")
        return 0
    try:
        cfg = sources.check(data["libraries"])
    except sources.SourceError as e:
        print(f"{main.name}: {e.field}: refused, {e.code}: nothing fetched", file=sys.stderr)
        return 2
    unknown = [n for n in args.names if n not in cfg]
    if unknown:
        print(f"no library {unknown[0]!r} in libraries: (there are: {', '.join(cfg)})", file=sys.stderr)
        return 2
    try:
        return fetch.run(str(main.parent), cfg, args.names, args.update)
    except (fetch.FetchError, OSError) as e:
        print(f"ergostat library fetch: {e}", file=sys.stderr)
        return 2
