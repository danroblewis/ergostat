"""The review lessons changed by hand, and the gated action that makes the librarian's proposal a gap. Each change is
a gap (`knowledge-<name>`) whose definition is the exact edit to dev/knowledge/review-lessons.md, built, reviewed and
landed like any other, since the knowledge is in the repository. Run in the instance's folder.

    lesson.py add "TITLE" --check "CHECK" [--seen "SHAPE"]   a new lesson, by the coordinator
    lesson.py retire N "WHY"                                  lesson N removed (briefs carried it to no effect)
    lesson.py request lesson/ID                               the action knowledge-change: an approved proposal"""

from __future__ import annotations

import argparse
import json
import sys
import time

sys.dont_write_bytecode = True
import fac  # noqa: E402
import knowledge  # noqa: E402


def request(cfg: dict, name: str, what: str, edit: str, who: str, item: str = "") -> None:
    branch = f"knowledge-{fac.slug(name, 40)}"
    p = fac.run_dir(cfg, "defs") / f"{branch}.md"
    if not fac.SAFE.match(branch) or p.exists():
        raise SystemExit(f"{branch}: not a branch name, or asked for already ({fac.rel(p)})")
    p.write_text(f"# {branch}: {what}\n\ndepends-on: []\n\nBranch `{branch}`, from main. Asked by {who}.\n\n"
                 f"## Definition of done\n\n`dev/knowledge/review-lessons.md`: {what}, as below, and nothing else "
                 f"changed.\n\n{edit.strip()}\n\n## Acceptance tests\n\n- `tests/test_factory_knowledge.py::"
                 "test_knowledge_files_parse`: the knowledge files still parse into entries with ids.\n\n"
                 "## Size budget\n\n0 net lines of code (knowledge only).\n")
    fac.add("gap.requested", f"gap/{branch}", title=what[:100], source="request", branch=branch, definition=fac.rel(p),
            requested_at=time.time(), knowledge=item)
    if item:
        fac.add("lesson.requested", item, gap=f"gap/{branch}", requested_at=time.time())
    print(f"gap/{branch} requested ({fac.rel(p)})")


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
    args = ap.parse_args(argv)
    cfg = fac.config()
    fac.cli(cfg)
    lessons = {int(e["id"][7:]): e for e in knowledge.entries() if e["id"].startswith("lesson-")}
    if args.cmd == "add":
        n = max(lessons) + 1
        request(cfg, args.title, f"a new lesson, § {n}", f"## {n}. {args.title}\n" + (
            f"Seen as: {args.seen}.\n" if args.seen else "") + f"**Check:** {args.check}", "the coordinator")
    elif args.cmd == "retire":
        if args.n not in lessons:
            raise SystemExit(f"no lesson {args.n}")
        request(cfg, f"retire-{args.n}", f"lesson {args.n} ({lessons[args.n]['title']}) retired",
                f"Remove § {args.n} whole; renumber nothing. Why:\n\n> {args.why}", "the coordinator")
        fac.add("lesson.retired", f"lesson/retire-lesson-{args.n}", lesson=f"lesson-{args.n}", why=args.why)
    else:
        it = json.loads(fac.ergostat("item", args.item, "--json").stdout)
        f, seen = it["fields"], "\n".join(f"> {x}" for x in it["fields"].get("findings") or [] if x)
        if it.get("state") != "proposed":
            raise SystemExit(f"{args.item} is {it.get('state')}, not proposed")
        if f.get("kind") == "seen":
            request(cfg, args.item.split("/", 1)[1], f"{f.get('lesson')} seen as a new shape", "Add to its \"Seen "
                    f"as:\" (a new line under its first paragraph if it has none), in its style: {f.get('text')}\n\n"
                    f"From:\n\n{seen}", "the librarian, approved by the coordinator", args.item)
        else:
            request(cfg, args.item.split("/", 1)[1], f"a new lesson: {f.get('name')}", "A new entry at the end, "
                    f"numbered next: the class \"{f.get('name')}\", its shapes as seen below, and the check that "
                    f"catches it before review, in the others' style. Found in {', '.join(f.get('reviews') or [])}:"
                    f"\n\n{seen}", "the librarian, approved by the coordinator", args.item)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
