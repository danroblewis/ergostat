"""intake: the factory's collector, the sensor of the whole workflow. Every few minutes it reads the gaps:

- each top-level entry of docs/GAPS.md on the checkout's main, outside *Done recently* and not itself done, that the
  record does not hold yet: `gap.found` (open);
- requests submitted as events (`ergostat event --add gap.requested --item gap/NAME --data '{"title": ...}'`) are in
  the record already, open;
- each open gap with a definition of done: `gap.defined` (ready). A definition is the gap's `definition` field (a
  file in run/defs/), `run/defs/<branch>.md` in the instance's folder (written by the coordinator), or
  `docs/roadmap/overnight/<branch>.md` on main or on the gap's branch; nothing else is read.

It reads git with commands that write nothing, and never acts. Run as a block: its lines are the record's."""

from __future__ import annotations

import re
import sys
import time

sys.dont_write_bytecode = True
import brief  # noqa: E402
import fac  # noqa: E402

ENTRY = re.compile(r"^- \*\*(.+?)\*\*\s*(\((?:[^()]|\([^()]*\))*\))?")


def gaps_md(text: str) -> list[dict]:
    """The entries of GAPS.md still to do: title, section, what it says of itself, the branches it names."""
    out, section = [], ""
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        m = ENTRY.match(line)
        if not m or section.lower().startswith("done"):
            continue
        paren = (m.group(2) or "").lower()
        if paren.startswith("(done"):
            continue
        title = m.group(1).rstrip(":").strip()
        out.append({"id": f"gap/{fac.slug(title, 60)}", "title": title, "section": section,
                    "gaps_says": "parked" if ("parked" in paren or "stopped" in paren) else
                    "in progress" if "in progress" in paren else "open"})
    return out


def definition(cfg: dict, gap: dict) -> str | None:
    """Where the gap's definition of done is (only run/defs/ or REF:docs/roadmap/overnight/, brief.definition_text),
    or None; None too for a gap whose branch is not a safe name."""
    try:
        branch = fac.branch_of(gap)
    except ValueError as e:
        print(f"intake: {e}: not taken", file=sys.stderr)
        return None
    rel = f"{fac.DEFS}/{branch}.md"
    for where in (str(gap["fields"].get("definition") or ""), f"run/defs/{branch}.md", f"{cfg['git']['base']}:{rel}",
                  f"{fac.git_branch(branch)}:{rel}"):
        if where and brief.definition_text(cfg, where, branch).strip():
            return where
    return None


def main() -> int:
    cfg = fac.config()
    repo = fac.path(cfg, "checkout")
    known = {g["id"]: g for g in fac.items("gap")}
    now = time.time()
    found = 0
    for e in gaps_md(fac.git(repo, "show", f"{cfg['git']['base']}:docs/GAPS.md")):
        if e["id"] not in known:
            gid = e.pop("id")
            fac.say("gap.found", gid, **e, source="gaps", branch=fac.slug(gid.split("/", 1)[1], 32), open_at=now)
            known[gid] = {"id": gid, "state": "open", "fields": {**e, "branch": fac.slug(gid.split("/", 1)[1], 32)}}
            found += 1
    defined = 0
    for g in known.values():
        if g["state"] != "open":
            continue
        where = definition(cfg, g)
        if where:
            fac.say("gap.defined", g["id"], definition=where, ready_at=now, branch=fac.branch_of(g))
            defined += 1
    print(f"intake: {found} found, {defined} defined", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
