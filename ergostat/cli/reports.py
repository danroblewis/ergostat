"""``ergostat report`` (SPEC §12m): reports about ergostat itself, drafted and scrubbed for the owner to read and, if
they choose, paste into a new issue on ergostat's GitHub project by hand. ergostat never sends one.

    ergostat report                          the reports, newest first
    ergostat report ID                       one: the text to paste, the link to a new issue, and what was scrubbed
    ergostat report --draft "what went wrong" [--details TEXT] [--part P ...] [--finding CODE ...] [--repro FILE]
    ergostat report ID --reviewed | --done | --dismiss [--note TEXT]
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..show import ago, c, table
from .common import open_project, out_json


def register(sub, common) -> None:
    rp = sub.add_parser("report", parents=[common], help="Reports about ergostat itself, scrubbed, for you to read and "
                        "submit by hand (--draft TEXT drafts one; ID --done, --dismiss)",
                        description="Reports upstream (SPEC §12m): something wrong with ergostat itself, drafted and "
                                    "scrubbed into the state directory's reports/ folder, ready to paste as a GitHub issue. "
                                    "ergostat never sends one.")
    rp.add_argument("name", nargs="?", metavar="ID", help="one report (a prefix of its id will do)")
    rp.add_argument("--draft", metavar="TEXT", help="draft a report: what went wrong, in a line")
    rp.add_argument("--details", metavar="TEXT", help="with --draft: more words")
    rp.add_argument("--part", action="append", metavar="PART", help="with --draft: a part involved (stock.x, block.y); "
                                                                     "a generic reproduction is made from them")
    rp.add_argument("--finding", action="append", metavar="CODE", help="with --draft: a finding involved (code or code@part)")
    rp.add_argument("--repro", metavar="FILE", help="with --draft: a reproduction you wrote (scrubbed like the rest)")
    rp.add_argument("--reviewed", action="store_true", help="with ID: you have read it")
    rp.add_argument("--done", action="store_true", help="with ID: you submitted it on GitHub")
    rp.add_argument("--dismiss", action="store_true", help="with ID: let it go")
    rp.add_argument("--note", metavar="TEXT", help="with --reviewed, --done or --dismiss: why, or the issue's link")
    rp.add_argument("--log", action="store_true", help="with ID: only the scrub log (what was removed, and why)")
    rp.set_defaults(fn=cmd_report)


def cmd_report(args) -> int:
    from ..reports import record
    p = open_project(args)
    try:
        if args.draft is not None:
            repro = Path(args.repro).read_text() if args.repro else None
            got = record.draft(p, args.draft, origin="owner", by="owner", details=args.details, parts=args.part,
                               findings=args.finding, repro=repro)
            if args.json:
                return out_json({k: v for k, v in got.items() if k != "text"})
            print(f"drafted {c(record.short(got['id']), 'bold')}: {got['title']}\n  {got['file']}\n"
                  f"  scrubbed: {_counts(got['scrubbed'])}\n"
                  f"read it: ergostat report {record.short(got['id'])}  (nothing is sent: you submit it by hand)")
            return 0
        if args.name and (args.reviewed or args.done or args.dismiss):
            to = "submitted" if args.done else "dismissed" if args.dismiss else "reviewed"
            got = record.mark(p, args.name, to, note=args.note)
            if args.json:
                return out_json(got)
            print(f"{record.short(got['id'])}: {got['state']}")
            return 0
        if args.name:
            return _one(p, args)
    except (record.ReportError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    got = sorted(record.stored(p).values(), key=lambda r: -r["time"])
    if args.json:
        return out_json([{k: r.get(k) for k in ("id", "state", "title", "origin", "occurrences", "time", "file")} for r in got])
    print(table(["REPORT", "STATE", "FROM", "SEEN", "DRAFTED", "TITLE"],
                [[record.short(r["id"]), r["state"], r.get("origin") or "", str(r.get("occurrences") or 1), ago(r["time"]),
                  (r.get("title") or "")[:70]] for r in got], "no reports: nothing about ergostat itself to tell its project"))
    if got:
        print(c(f"\nergostat report ID: one, ready to paste · the files: {Path(p.dir) / 'reports'}", "dim"))
    return 0


def _counts(counts: dict) -> str:
    return ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "nothing"


def _one(p, args) -> int:
    from ..reports import record
    r = record.text_of(p, args.name)
    if args.json:
        return out_json(r)
    if not args.log:
        print(c(f"{record.short(r['id'])} · {r['state']} · drafted {ago(r['time'])} by {r.get('by') or r.get('origin')}"
                + (f" · seen {r['occurrences']} times" if (r.get("occurrences") or 1) > 1 else ""), "dim"))
        print(c(f"file: {r['path']}", "dim"))
        print()
        print(r["text"] if r["text"] is not None else c("(its file is gone)", "warn"))
        print(c("open a new issue (nothing is sent; you paste the body):", "bold"))
        print(f"  {r['issue_url']}")
        print()
    print(c(f"Scrubbed (kept here, never part of the text): {_counts(r['counts'])}", "bold"))
    rows = [[x["stand_in"], x["rule"], x.get("what") or "", str(x["count"]), _short(x["original"]), x["why"]]
            for x in r["removed"]]
    print(table(["STAND-IN", "RULE", "WHAT", "N", "ORIGINAL", "WHY"], rows, "nothing was removed"))
    if r["state"] in ("drafted", "reviewed"):
        print(c(f"\nonce submitted: ergostat report {record.short(r['id'])} --done [--note URL]; or --dismiss", "dim"))
    return 0


def _short(s: str) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= 60 else s[:57] + "..."
