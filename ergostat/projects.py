"""Every project on this machine that ergostat has seen: its record's folder in the home holds
``repo.json`` (the repository's path). Read only."""

from __future__ import annotations

import json

from .store import home


def known() -> list[dict]:
    """Each project: name, repository, whether it runs, its page, and its loops' statuses."""
    from . import model as mdl
    from . import state as st
    from .runner import running_pid, web_url
    from .store import Project
    out = []
    for d in sorted(home().glob("*/repo.json")):
        try:
            note = json.loads(d.read_text())
            m = mdl.load(__import__("pathlib").Path(note["repo"]))
        except Exception as e:                       # a repository moved or its model broken: say so, don't stop
            out.append({"name": d.parent.name, "repo": None, "error": f"{type(e).__name__}: {e}"})
            continue
        p = Project(m, d.parent)
        pid = running_pid(p)
        snap = st.snapshot(p)
        loops = {n: lp["status"] for n, lp in snap["loops"].items()}
        out.append({"name": m.name, "repo": note["repo"], "running": bool(pid), "web": web_url(p) if pid else None,
                    "loops": len(loops), "off": sorted(n for n, s in loops.items() if s in ("off", "open")),
                    "attention": len([a for a in st.attention(snap, bool(pid), m) if a["level"] != "hint"])})
    return out
