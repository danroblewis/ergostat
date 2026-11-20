"""librarian: after each review (a run per `review.written`), its blocking findings compared with the review lessons
(dev/knowledge/review-lessons.md). A program around one small AI step that classifies each finding: a lesson's id, a
new class, or none. Then, by the program:

- a known class in a shape the lesson's "Seen as" does not cover: a proposed "seen as" line (lesson/seen-<id>-<hash>);
- a new class: counted on lesson/new-<name>; found in a second review, a proposed entry;
- the classes found recorded on the review (review.measured: classes), so plans are scored against them.

Each proposal is asked as the gated action knowledge-change: the coordinator approves, and `lesson.py request` makes it
a gap whose definition is the exact edit, built and landed like any other."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time

sys.dont_write_bytecode = True
import agents  # noqa: E402
import fac  # noqa: E402
import knowledge  # noqa: E402

MOST = 5                                         # proposals one review may make
LIST = re.compile(r"```json\s*(\[.*?\])\s*```", re.S)


def propose(lid: str, **data) -> None:
    fac.say("lesson.proposed", lid, proposed_at=time.time(), **data)
    fac.act("knowledge-change", key=lid.replace("/", "-"), lesson=lid)


def classify(cfg: dict, rid: str, found: list[str], lessons: dict) -> list[dict]:
    """The AI step: each finding's class (haiku, a fraction of a cent of the day's cap)."""
    prompt = (fac.HERE / "prompts" / "librarian.md").read_text().replace(
        "{lessons}", "\n\n".join(e["text"] for e in lessons.values())).replace("{review}", rid).replace(
        "{findings}", "\n".join(f"{i}. {x}" for i, x in enumerate(found, 1)))
    work = agents.scratch(cfg, fac.slug(rid.split("/", 1)[1], 48) or "review", "librarian") / "work"
    work.mkdir()
    said = str(fac.session(cfg, "librarian", prompt, work).get("result", ""))
    rows = json.loads(LIST.findall(said)[-1]) if LIST.findall(said) else None
    if not isinstance(rows, list):
        raise RuntimeError("the librarian's step gave no fenced JSON list")
    return [r for r in rows if isinstance(r, dict)][:len(found)]


def main() -> int:
    cfg = fac.config()
    if not (cfg.get("knowledge") or {}).get("librarian"):
        print("librarian: off ([knowledge] librarian = true turns it on)", file=sys.stderr)
        return 0
    ev = (json.loads(sys.stdin.read() or "{}") or {}).get("event") or {}
    rid, d = ev.get("item"), ev.get("data") or {}
    if not rid:
        raise RuntimeError("no review: the librarian runs for a review.written event")
    found = [str(x) for x in d.get("blocking") or [] if not str(x).startswith(("gate 1:", "size:"))]
    lessons = {e["id"]: e for e in knowledge.entries() if e["id"].startswith("lesson-")}
    rows = classify(cfg, rid, found, lessons) if found else []
    known = {i["id"]: i for i in fac.items("lesson")}
    classes, asked = set(), 0
    for row in rows:
        c, shape = str(row.get("class") or "none"), " ".join(str(row.get("shape") or "").split())[:300]
        n = int(row.get("finding") or 0)
        finding = found[n - 1] if 1 <= n <= len(found) else ""
        if c in lessons:
            classes.add(c)
            lid = f"lesson/seen-{c}-{hashlib.sha1(shape.lower().encode()).hexdigest()[:8]}"
            if row.get("new_shape") is True and shape and lid not in known and asked < MOST:
                propose(lid, kind="seen", lesson=c, text=shape, findings=[finding], reviews=[rid])
                asked += 1
        elif c == "new" and fac.slug(str(row.get("name") or ""), 40):
            lid = f"lesson/new-{fac.slug(str(row['name']), 40)}"
            classes.add(lid[7:])
            was = known.get(lid) or {"state": "seen", "fields": {}}
            if rid in (was["fields"].get("reviews") or []):
                continue
            fac.say("lesson.seen" if was["state"] == "seen" else "lesson.measured", lid, times=1, reviews=[rid],
                    findings=[finding], name=str(row["name"])[:120], kind="entry", text=shape)
            reviews = [*(was["fields"].get("reviews") or []), rid]
            now = was["state"] == "seen" and len(reviews) >= 2 and asked < MOST       # a class found twice
            if now:
                propose(lid, kind="entry")
                asked += 1
            known[lid] = {"state": "proposed" if now else was["state"], "fields": {"reviews": reviews}}
    fac.say("review.measured", rid, classes=sorted(classes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
