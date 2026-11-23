"""``ergostat library fetch [NAME...] [--update]`` (SPEC §2a, *Fetched libraries*): each library in the main file's
``libraries:`` fetched into ``.libraries/NAME`` and pinned in ``libraries.lock``. It reads only ``libraries:``, with
the loader's YAML reader: never the project, its record or the last good model, so it is not a read topic
(``goodmodel.READS``) and runs nothing when the file does not parse."""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path


def register(sub, common) -> None:
    lp = sub.add_parser("library", parents=[common], help="Fetch the libraries: in the main file and pin them in "
                        "libraries.lock (library fetch [NAME...] [--update])",
                        description="Fetch each library in libraries: into .libraries/NAME, pinned by commit and tree "
                                    "in libraries.lock. A library whose git, version and path match its lock, with its "
                                    "copy there, is kept; --update resolves its version again and moves the lock.")
    lp.add_argument("what", choices=["fetch"])
    lp.add_argument("names", nargs="*", metavar="NAME", help="only these libraries (leave out: every one)")
    lp.add_argument("--update", action="store_true", help="resolve each version again and move its lock entry")
    lp.set_defaults(fn=cmd_library)


def cmd_library(args) -> int:
    from ..library import fetch, fetched, sources
    from ..spec import files
    from ..spec import load as _  # noqa: F401 (the module, which the package's load() hides)
    load = sys.modules["ergostat.spec.load"]
    start = Path(args.C).resolve() if args.C else Path.cwd()
    main = load.find(start)
    if main is None:
        print(f"no {load.FILE} here or above {start}", file=sys.stderr)
        return 2
    problems: list = []
    data = load.read_file(main, problems)
    bad = [p for p in problems if p.level == "error"]
    if bad or not isinstance(data, dict):
        for p in bad or [f"{main.name}: not a map of sections"]:
            print(f"error  {p}", file=sys.stderr)
        print("ergostat library fetch reads libraries: from the main file; fix it first (nothing was fetched)",
              file=sys.stderr)
        return 2
    try:
        wanted, _ = fetched.split(data.get("libraries") or {})
    except sources.SourceError as e:
        print(f"{e.code}: {e.field}", file=sys.stderr)
        return 2
    unknown = [n for n in args.names if n not in wanted]
    if unknown or not wanted:
        print(f"no library {', '.join(unknown)} in libraries: (there are: {', '.join(wanted) or 'none'})"
              if unknown else f"no libraries: in {main}", file=sys.stderr)
        return 2
    try:
        got = fetch.fetch(main.parent, {n: s for n, s in wanted.items() if not args.names or n in args.names},
                          update=args.update)
    except (fetch.FetchError, files.TreeError, sources.SourceError, tarfile.TarError, OSError) as e:
        print(f"ergostat library fetch: {e}", file=sys.stderr)
        return 1
    for name, how in got.items():
        print(f"{name}: {how}")
    return 0
