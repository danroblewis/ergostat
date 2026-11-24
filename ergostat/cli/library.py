"""``ergostat library fetch [NAME...] [--update] [--dry-run]`` (SPEC §2a): the main file's ``libraries:`` read live
with the loader's own YAML reader, checked, and each library fetched and locked (``library/fetch.py``), or with
``--dry-run`` one update reviewed without taking it (``library/compare.py``). It never opens the project and never
runs on the last good model: a main file that does not read stops it before any git process.
``ergostat library`` alone lists them (``listing``), offline, on the last good model when the main file is broken."""

from __future__ import annotations

import sys

from .spec_cmds import here


def register(sub, common) -> None:
    lp = sub.add_parser("library", parents=[common], help="Libraries fetched by git URL: list them, or fetch [NAME...]",
                        description="ergostat library: each library in libraries:, where from, its pin and trust, "
                                    "offline. ergostat library fetch [NAME...] [--update]: clone each library "
                                    "into .libraries/NAME and pin it in libraries.lock (SPEC §2a)")
    lp.add_argument("what", nargs="?", choices=["fetch"])
    lp.add_argument("names", nargs="*", metavar="NAME", help="only these libraries (leave out: all)")
    lp.add_argument("--update", action="store_true", help="resolve each version again, even an unchanged one")
    lp.add_argument("--dry-run", action="store_true", help="with --update and one NAME: fetch the new version aside, "
                    "take nothing, and say what it breaks and changes (exit 1 when it adds an error)")
    lp.set_defaults(fn=cmd_library)


def cmd_library(args) -> int:
    from ..library import fetch, sources
    from ..spec.files import TreeError
    from ..spec.load import FILE, find, read_file
    main = find(here(args))
    if main is None:
        print(f"no {FILE} here or above", file=sys.stderr)
        return 2
    problems: list = []
    data = read_file(main, problems)
    bad = [p for p in problems if p.level == "error"]
    if args.what is None:
        return listing(main, data if not bad and isinstance(data, dict) else None, bad)
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
    if args.dry_run:
        return _dry_run(args, main, cfg)
    rc = 0
    for name in args.names or list(cfg):          # one after another; each read-decide-write under the flock
        try:
            got = fetch.fetch(main.parent, {name: cfg[name]}, args.update,
                              lambda line: print(line, file=sys.stderr, flush=True))[name]
            e = fetch.read_lock(main.parent).get(name, {})
            print(f"library {name}: up to date at {e.get('commit', '')[:12]}" if got == "kept" else
                  f"library {name}: {e.get('version')} at {e.get('commit', '')[:12]} ({e.get('tree', '')[:19]})")
        except fetch.FetchError as x:
            print(f"library {name}: not fetched: {x}", file=sys.stderr)
            if x.code in ("bad-lock", "linked-library-folder"):
                return 2
            rc = 1
        except (TreeError, OSError) as x:
            print(f"library {name}: not fetched: {x}", file=sys.stderr)
            rc = 1
    return rc


def _dry_run(args, main, cfg) -> int:
    """``fetch NAME --update --dry-run`` (library/compare.py): 0 when the candidate adds no error, else 1."""
    from ..library import compare, fetch
    from ..spec.files import TreeError
    if not args.update or len(args.names) != 1:
        print("--dry-run reviews one update: ergostat library fetch NAME --update --dry-run", file=sys.stderr)
        return 2
    name = args.names[0]
    try:
        r = compare.update(main, name, cfg[name], None, lambda line: print(line, file=sys.stderr, flush=True))
    except fetch.FetchError as x:
        print(f"library {name}: not reviewed: {x}", file=sys.stderr)
        return 2 if x.code in ("bad-lock", "linked-library-folder") else 1
    except (TreeError, OSError) as x:
        print(f"library {name}: not reviewed: {x}", file=sys.stderr)
        return 1
    print("\n".join(compare.lines(r)))
    return 0 if r["ok"] else 1


def listing(main, data, bad) -> int:
    """``ergostat library``: each library as load reads it (fetched.described): no git process, nothing written. A
    main file that does not read is listed from the last good model (goodmodel.fallback), said on standard error."""
    from .. import goodmodel
    from ..library.fetched import SECTION, line
    from ..library.untrusted import OPEN, SAYS, printable
    from ..spec.load import load
    refused = []                                  # the libraries: section itself refused (sources.check): rc 1
    if data is not None:
        doc = load(main)
        libs = doc.listed
        refused = [p for p in doc.problems if p.level == "error" and p.code in SECTION]
    else:
        p = goodmodel.fallback(main.parent, ValueError(f"{main.name}\n{bad[0] if bad else 'not a map of sections'}"))
        if p is None:
            print(f"{main.name}: {bad[0] if bad else 'not a map of sections'} (and no last good model is kept)",
                  file=sys.stderr)
            return 2
        libs = p.model.spec.libraries
    lines = [line(d) for d in libs.values()]
    if lines or not refused:
        print("\n".join(lines) if lines else f"{main.name} has no libraries:")
    print(f"\n{SAYS}" if any(OPEN in x for x in lines) else "", end="")
    for p in refused:
        print(f"{main.name}: {printable(p)}", file=sys.stderr)
    return 1 if refused else 0
