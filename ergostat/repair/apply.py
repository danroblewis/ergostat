"""``python -m ergostat.repair fix|apply|settle`` (SPEC §12r). ``apply``, the approved ``apply-fix``: the tested commit
fast-forwarded onto the owner's HEAD it was made on, else back to open. ``settle``: a denied fix dismissed, and the
clones no failure needs removed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..sandbox import git as sgit
from . import FAILURE
from .fix import Refused, failure, owner_repo, record

DONE = ("applied", "dismissed", "dead")


def apply() -> int:
    from ..library.run.common import project
    p = project()
    fid = os.environ.get("ERGOSTAT_ITEM", "")
    try:
        _, name, it = failure(p, fid)
        f = it.fields if it else {}
        if it is None or it.state != "awaiting-approval" or not f.get("fix"):
            raise Refused(f"{fid} has no tested fix waiting")
        work = Path(p.dir) / "repair" / name
        c = sgit.Repo(work, work / ".git")
        if c("rev-parse", "HEAD").strip() != f["fix"]:
            raise Refused("the clone is not at the tested commit")
        owner = owner_repo(p.model.spec.root)
        if owner("rev-parse", "HEAD").strip() != f["base"]:
            raise Refused(f"the repository moved since the fix was made on {f['base'][:12]}: fixed again on the new HEAD")
        owner("fetch", "-q", "--no-tags", str(work), "HEAD")
        if owner("rev-parse", "FETCH_HEAD").strip() != f["fix"]:
            raise Refused("what was fetched is not the tested commit")
        owner("merge", "--ff-only", "-q", f["fix"])
    except (Refused, sgit.Tampered, subprocess.CalledProcessError) as e:
        why = str(e) if not isinstance(e, subprocess.CalledProcessError) else f"git: {(e.stderr or '').strip()[-500:]}"
        record(p, "apply-failed", fid, {"why": why})
        print(f"not applied: {why}", file=sys.stderr)
        return 1
    record(p, "applied", fid, {"commit": f["fix"], "orig_head": f["base"]})
    shutil.rmtree(work, ignore_errors=True)
    print(f"applied {f['fix'][:12]} onto {f['base'][:12]}")
    return 0


def settle() -> int:
    from ..actions import record as actions
    from ..library.run.common import items, project
    p = project()
    n = 0
    for it in items(p, FAILURE, ["awaiting-approval"]):
        asked = actions.about(p, it.id)                     # newest first: the answer to the latest asked
        if asked and asked[0]["state"] == "denied":
            record(p, "dismissed", it.id, {"by": asked[0].get("denied_by"), "note": asked[0].get("note")})
            n += 1
    states = {i.id.split("/", 1)[1]: i.state for i in items(p, FAILURE)}
    for d in (Path(p.dir) / "repair").glob("*/"):
        if states.get(d.name, "dead") in DONE:
            shutil.rmtree(d, ignore_errors=True)
    print(json.dumps({"out": "flow.fixes-dismissed", "moved": n}))
    return 0


def main(argv: list[str]) -> int:
    from . import fix
    if argv[:1] == ["fix"]:
        return fix.main(argv[1:])
    if argv in (["apply"], ["settle"]):
        return apply() if argv == ["apply"] else settle()
    print("usage: python -m ergostat.repair fix [...] | apply | settle", file=sys.stderr)
    return 2
