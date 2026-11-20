"""A gap asked for by the coordinator; run in the instance's folder. With a definition it is ready at the intake's next
look; without one, the planner plans it.

    request.py "Title" [--branch NAME] [--depends-on a,b] [--definition FILE]"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="request.py", description=__doc__)
    ap.add_argument("title")
    ap.add_argument("--branch", default="")
    ap.add_argument("--depends-on", default="", help="gaps it waits on, by branch or id, comma-separated")
    ap.add_argument("--definition", default="", help="its definition of done (copied into run/defs/)")
    args = ap.parse_args(argv)
    cfg = fac.config()
    fac.cli(cfg)
    branch = args.branch or fac.slug(args.title, 32)
    if not fac.SAFE.match(branch):
        raise SystemExit(f"branch {branch!r}: lowercase words and dashes")
    known = {g["id"] for g in fac.items("gap")}
    if f"gap/{branch}" in known:
        raise SystemExit(f"gap/{branch} exists already: name it otherwise (--branch)")
    deps = [d if d.startswith("gap/") else f"gap/{d}" for d in (x.strip() for x in args.depends_on.split(",")) if d]
    missing = [d for d in deps if d not in known]
    if missing:
        raise SystemExit(f"no such gap: {', '.join(missing)}")
    data = dict(title=args.title, source="request", branch=branch, depends_on=deps, requested_at=time.time())
    if args.definition:
        p = fac.run_dir(cfg, "defs") / f"{branch}.md"
        if p.exists():
            raise SystemExit(f"{fac.rel(p)} exists already")
        p.write_text(Path(args.definition).read_text())
        data["definition"] = fac.rel(p)
    fac.add("gap.requested", f"gap/{branch}", **data)
    print(f"gap/{branch} requested" + (" (defined)" if args.definition else " (the planner plans it)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
