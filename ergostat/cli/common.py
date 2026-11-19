"""What every topic shares: opening the project, the window and the moment to look at, and output."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .. import model as mdl
from .. import state as st
from ..durations import DurationError, human, parse_duration
from ..show import c

PART_TOPICS = ("stock", "flow", "valve", "sensor", "controller", "disturbance")

def out_json(obj) -> int:
    print(json.dumps(obj, indent=2, default=str))
    return 0

def open_project(args):
    from ..store import Project
    here = Path(args.C).resolve() if args.C else Path.cwd()
    try:
        m = mdl.load(here)
    except FileNotFoundError:
        print(f"no {mdl.FILE} here or above {here}. To start:\n"
              f"  ergostat check --example cron > {mdl.FILE}   two one-liners that run as they are; then ergostat run\n"
              f"  ergostat chat                                   describe your system (your crontab too) to the Supervisor\n"
              f"  ergostat check --example                        one program to write, to start from",
              file=sys.stderr)
        raise SystemExit(2) from None
    except (mdl.ModelError, DurationError) as e:
        found = mdl.find(here)
        print(f"{found.name if found else mdl.FILE}: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    return Project(m)

def window(args) -> float:
    return parse_duration(args.since, "--since") if args.since else st.WINDOW

def at_of(args) -> float | None:
    """``--at``: a moment in the past, as ``30m`` (that long ago), ``07:30`` (today, or yesterday when
    that is still to come), or seconds since the epoch. None: now."""
    v = getattr(args, "at", None)
    if not v:
        return None
    import re
    from datetime import datetime, timedelta
    forms = "a time ago (30m, 2h), a clock time today (07:30; yesterday when it is still to come), or epoch seconds"
    if m := re.fullmatch(r"(\d{1,2}):(\d{2})", v.strip()):
        if int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise DurationError(f"--at {v!r}: not a clock time; give {forms}")
        t = datetime.now().replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if t > datetime.now():
            t -= timedelta(days=1)
        return t.timestamp()
    try:
        x = float(v)
        if x > 1e9:
            return x
    except ValueError:
        pass
    try:
        return time.time() - parse_duration(v, "--at")
    except DurationError:
        raise DurationError(f"--at {v!r}: give {forms}") from None

def snap_of(p, args) -> dict:
    return st.snapshot(p, window(args), at_of(args))

def as_of(snap: dict) -> str:
    return "" if snap.get("live", True) else c(f" · as of {time.strftime('%H:%M:%S', time.localtime(snap['at']))} "
                                               f"({human(time.time() - snap['at'])} ago)", "accent")

def parts_of(args, m) -> set[str]:
    if getattr(args, "system", None):
        if args.system not in m.system_names():
            print(f"no system {args.system!r}; systems: {', '.join(m.system_names()) or 'none'}", file=sys.stderr)
            raise SystemExit(2)
        return m.members(args.system)
    return m.members(None)

EXAMPLE = '''# ergostat.toml: one loop. disk usage is held under 80% by a program that measures and cleans.
# (the project's name defaults to its folder's; ./clean.sh is yours to write: see `ergostat help blocks`,
#  and try it with `ergostat agent disk-cleaner --now`)

[[stock]]
name = "disk-used"
unit = "%"
systems = ["host"]

[[disturbance]]
name = "logs-written"
into = "disk-used"
description = "what the services write; nothing here controls it"

[[flow]]
name = "cleaned"
from = "disk-used"

[[sensor]]
name = "disk-usage"
measures = "disk-used"
agent = "disk-cleaner"

[[controller]]
name = "disk-under-80"
holds = "disk-used"
setpoint = "<= 80"
reads = ["disk-usage"]
drives = ["delete-old-files"]
agent = "disk-cleaner"

[[valve]]
name = "delete-old-files"
flow = "cleaned"
agent = "disk-cleaner"

[[agent]]
name = "disk-cleaner"
kind = "program"
command = "./clean.sh"
every = "5m"
'''


EXAMPLE_CRON = '''# ergostat.toml: two jobs as a crontab would have them, one-liners that print a number; nothing to
# write. A job filling one sensor or one valve may print a bare number: its reading, or what it moved.
# Try it here as it is: `ergostat run`, then `ergostat` and `ergostat system --blocks`.

[[stock]]
name = "tmp-files"
unit = "files"
systems = ["host"]

[[disturbance]]
name = "files-left"
into = "tmp-files"
description = "whatever leaves files in .ergostat-example/tmp/ (its own folder: point it at yours when you are ready)"

[[flow]]
name = "pruned"
from = "tmp-files"

[[sensor]]
name = "count-tmp"
measures = "tmp-files"
agent = "count"

[[controller]]
name = "tmp-under-500"
holds = "tmp-files"
setpoint = "<= 500"
drives = ["prune-old"]
agent = "pruner"
open_loop = true          # a timer: it deletes by age, whatever the count; the count only watches it

[[valve]]
name = "prune-old"
flow = "pruned"
agent = "pruner"

[[agent]]
name = "count"
kind = "program"
command = "mkdir -p .ergostat-example/tmp; find .ergostat-example/tmp -type f | wc -l"
every = "1m"

[[agent]]
name = "pruner"
kind = "rule"
command = "find .ergostat-example/tmp -type f -mmin +60 -delete -print | wc -l"
cron = "0 * * * *"
'''
