"""The review lessons' own queue (dev/README.md, *The knowledge queue*): a `lesson` item moves proposed -> approved ->
applied (or denied, retired), its exact text on the item (`entry`), applied by the program block lesson-apply. No
session, branch, review or merge, and never a gap. The repository's dev/knowledge/review-lessons.md is the seed; the
applied items live in the instance's record, so a version switch keeps them, and knowledge.block carries both. Run in
the instance's folder (apply is the block's run).

    lesson.py add "TITLE" --check "CHECK" [--seen "SHAPE"]   a new lesson, by the coordinator: approved at once
    lesson.py retire N "WHY"                                  lesson N no longer carried: approved at once
    lesson.py request lesson/ID                               the action knowledge-change: an approved proposal
    lesson.py apply                                           the block lesson-apply: an approved lesson applied
    lesson.py settle                                          each denied proposal settled; the migration (once)
    lesson.py hours                                           mean hours from proposed (or approved) to applied, 14 days"""

from __future__ import annotations

import argparse
import json
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import knowledge  # noqa: E402

QUIET = ("open", "planned", "replan", "ready", "fix", "parked", "closed")   # closable, when no lease holds it


def exact(f: dict) -> str:
    """The exact text a lesson item adds: a "seen as" shape, or a new lesson's entry (numbered when applied)."""
    if f.get("entry"):
        return str(f["entry"])
    if f.get("kind") == "seen":
        return " ".join(str(f.get("text") or "").split())
    return (f"{f.get('name')}\nSeen as: {' '.join(str(f.get('text') or '').split())}.\n**Check:** not yet written "
            f"(found in {', '.join(f.get('reviews') or [])}).")


def number(lessons: list[dict], gaps: dict[str, dict]) -> int:
    """The next lesson's number: past the seed's and every applied one's, and past one reserved for each new lesson
    still requested as a gap not merged or closed (it numbers itself next in the seed when it merges)."""
    seed = [int(e["id"][7:]) for e in knowledge.entries() if e["id"].startswith("lesson-")]
    held = sum(1 for i in lessons if i["state"] == "requested" and i["fields"].get("kind") == "entry" and (
        gaps.get(str(i["fields"].get("gap"))) or {}).get("state") not in ("merged", "closed"))
    return max([0, *seed, *(int(i["fields"].get("number") or 0) for i in lessons)]) + 1 + held


def approve(iid: str, **data) -> None:
    fac.add("lesson.approved", iid, approved_at=time.time(), **data)
    print(f"{iid} approved; lesson-apply applies it")


def apply(given: dict) -> int:
    """One approved lesson applied. The lease (pool 1, fenced) is the lock; the item is read again from the record and
    left as it is unless still approved, so a second run on one approval records nothing (lesson-1). A record that
    cannot be read raises: the lesson stays approved (lesson-3)."""
    iid, back = given["item"]["id"], (given.get("lease") or {}).get("back")
    it = json.loads(fac.ergostat("item", iid, "--json").stdout)
    if it.get("state") != "approved" and not (it.get("state") == "leased" and back == "approved"):   # (held: leased)
        print(f"{iid} is {it.get('state')}: nothing to apply", file=sys.stderr)
        return 0
    f, now, lessons = it["fields"], time.time(), fac.items("lesson")
    if f.get("kind") == "retire":
        for o in lessons:
            if o["state"] == "applied" and o["fields"].get("kind") == "entry" and o["fields"].get("lesson") == f["lesson"]:
                fac.say("lesson.retired", o["id"], retired_at=now, why=f.get("why") or "")
        fac.say("lesson.retired", iid, retired_at=now)
        return 0
    n = number(lessons, {g["id"]: g for g in fac.items("gap")}) if f.get("kind") == "entry" else None
    fac.say("lesson.applied", iid, entry=exact(f), applied_at=now, **({"lesson": f"lesson-{n}", "number": n} if n else {}))
    return 0


def settle() -> None:
    """Each proposal whose knowledge-change the coordinator denied, settled `denied` with who and why. A denial by the
    gate (fencing) is no decision; a record that cannot be read stops this with nothing written (lesson-3)."""
    open_ = {i["id"] for i in fac.items("lesson", "proposed")}
    for a in fac.items("ergostat.action", "denied"):
        f = a.get("fields") or {}
        lid = (f.get("args") or {}).get("lesson")
        if f.get("action") == "knowledge-change" and lid in open_ and f.get("denied_by") not in (None, "", "gate"):
            fac.add("lesson.denied", lid, denied_by=f["denied_by"], why=f.get("note") or "", action=a["id"],
                    denied_at=time.time())
            open_.discard(lid)
            print(f"{lid} denied by {f['denied_by']}")


def migrate() -> None:
    """Once, and idempotent: each lesson `requested` as a gap before this queue whose gap/knowledge-* has not merged is
    approved, for lesson-apply to apply and number (one actuator, one lease: lesson-1), and that gap closed with the
    reason. Only a gap in a state no run is in (QUIET) that no lease holds is closed: a merged one is left alone (its
    lesson is in the files already), one in flight or leased waits for a later run, and one not in the record is
    reported, never taken as unmerged (lesson-3). A lease taken between the read and the close (its fence moved) leaves
    the lesson requested, so a gap that then merges is not carried twice. Only the gap the lesson names is touched."""
    gaps, now = {g["id"]: g for g in fac.items("gap")}, time.time()
    lease = lambda g: g["fields"].get("lease") or {}  # noqa: E731
    for it in (i for i in fac.items("lesson") if i["state"] == "requested"):
        gid, f = str(it["fields"].get("gap") or ""), it["fields"]
        g = gaps.get(gid)
        if not gid.startswith("gap/knowledge-") or g is None or g["state"] not in QUIET or lease(g).get("holder"):
            print(f"{it['id']}: left requested ({gid or 'no gap'} {g['state'] if g else 'not in the record'})",
                  file=sys.stderr)
            continue
        if g["state"] != "closed":
            fac.add("gap.closed", gid, end="superseded", closed_by="lesson-migration", closed_at=now,
                    closed_reason=f"{it['id']} is applied by the knowledge queue (lesson-apply), not built as a gap")
            if lease(json.loads(fac.ergostat("item", gid, "--json").stdout)).get("fence") != lease(g).get("fence"):
                print(f"{it['id']}: left requested ({gid} was taken as it was closed)", file=sys.stderr)
                continue
        fac.add("lesson.approved", it["id"], entry=exact(f), approved_by="lesson-migration", approved_at=now,
                migrated_from=gid)
        print(f"{it['id']} approved; {gid} closed")


def hours() -> float:
    """Mean hours from proposed (or, for the coordinator's own, approved) to applied, of lessons applied in 14 days."""
    now, got = time.time(), []
    for i in fac.items("lesson", "applied"):
        f = i["fields"]
        at, began = float(f.get("applied_at") or 0), float(f.get("proposed_at") or f.get("approved_at") or 0)
        if began and now - at <= 14 * 86400:
            got.append((at - began) / 3600)
    return round(sum(got) / len(got), 3) if got else 0.0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="lesson.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("title")
    a.add_argument("--check", required=True)
    a.add_argument("--seen", default="")
    r = sub.add_parser("retire")
    r.add_argument("n", type=int)
    r.add_argument("why")
    sub.add_parser("request").add_argument("item")
    for c in ("apply", "settle", "hours"):
        sub.add_parser(c)
    args = ap.parse_args(argv)
    if args.cmd == "apply":
        return apply(fac.read_input())
    cfg = fac.config()
    fac.cli(cfg)
    if args.cmd in ("settle", "hours"):
        if args.cmd == "hours":
            print(hours())
            return 0
        settle()
        migrate()
        return 0
    held = {i["id"]: i for i in fac.items("lesson")}
    if args.cmd == "add":
        iid = f"lesson/add-{fac.slug(args.title, 40)}"
        if iid in held:
            raise SystemExit(f"{iid} is {held[iid]['state']} already")
        approve(iid, kind="entry", name=args.title, approved_by="the coordinator", entry=f"{args.title}\n" + (
            f"Seen as: {args.seen}.\n" if args.seen else "") + f"**Check:** {args.check}")
    elif args.cmd == "retire":
        iid, carried = f"lesson/retire-lesson-{args.n}", {e["id"] for e in knowledge.applied(knowledge.entries(),
                                                                                              list(held.values()))}
        if f"lesson-{args.n}" not in carried or iid in held:
            raise SystemExit(f"lesson {args.n} is not carried, or its retirement is asked for already")
        approve(iid, kind="retire", lesson=f"lesson-{args.n}", why=args.why, approved_by="the coordinator")
    else:
        it = held.get(args.item) or {}
        if it.get("state") != "proposed":
            raise SystemExit(f"{args.item} is {it.get('state', 'not in the record')}, not proposed")
        approve(args.item, entry=exact(it["fields"]), approved_by="knowledge-change")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
