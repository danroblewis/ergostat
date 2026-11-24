"""The entry for searching items and querying their graph: done, read as done by intake, naming both merge commits on
main, listed once (dev/records/item-search-join-2.md). Read from the pinned copy of GAPS.md (tests/test_gapsdoc.py
checks it is GAPS.md as of a named commit), never the moving docs/GAPS.md, which the merge queue writes from the
records (dev/records/merge-pipeline-gaps-briefs-read-records.md)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GAPS = ROOT / "tests" / "fixtures" / "gaps_md_pinned.md"
TITLE = "Searching items and querying their graph"
LIMITS = "Not the Items page's own box, not MCP, not `--at`."


def intake(fn: str):
    """intake.<fn> over GAPS.md, run in a subprocess as tests/test_gaps_doc.py does."""
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import intake; "
            f"print(json.dumps(intake.{fn}(open(sys.argv[2], encoding='utf-8').read())))")
    r = subprocess.run([sys.executable, "-c", code, str(ROOT / "dev" / "bin"), str(GAPS)], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def entry() -> list[str]:
    """The ## Interface bullet titled TITLE with its indented lines; the test fails if there is none."""
    section, out = "", None
    for line in GAPS.read_text(encoding="utf-8").splitlines():
        if out is not None:
            if line.startswith("  "):
                out.append(line)
                continue
            return out
        if line.startswith("## "):
            section = line[3:].strip()
        elif section == "Interface" and line.startswith(f"- **{TITLE}**"):
            out = [line]
    if out is None:
        pytest.fail(f"no entry titled {TITLE!r} under ## Interface in {GAPS}")
    return out


def subpoint(name: str) -> str:
    """The entry's sub-point starting `  - *name*`, its lines joined."""
    lines, cur = entry(), None
    for line in lines[1:]:
        if line.startswith("  - "):
            if cur is not None:
                break
            if line.startswith(f"  - *{name}*"):
                cur = [line]
        elif cur is not None:
            cur.append(line)
    assert cur, f"no *{name}* sub-point in the entry"
    return " ".join(x.strip() for x in cur)


def main_ref() -> str:
    for ref in ("origin/main", "main", "HEAD"):
        r = subprocess.run(["git", "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    pytest.fail("no git history to check the cited commits against")


def test_item_search_entry_read_done_by_intake():
    entries = intake("gaps_md")
    assert len(entries) >= 10 and any(e["section"] == "Runtime, scale and latency" for e in entries)   # it parsed
    mine = [e for e in entries if e["section"] == "Interface" and e["title"] == TITLE]
    assert len(mine) == 1, mine
    assert mine[0]["gaps_says"] == "done", mine[0]
    assert "split in two" not in " ".join(entry())


def test_item_search_entry_names_both_merge_commits():
    assert "512f08ef" in subpoint("Search")
    assert "c5eb54e6" in subpoint("near, path and about")
    ref = main_ref()
    for h in ("512f08ef", "c5eb54e6"):
        r = subprocess.run(["git", "merge-base", "--is-ancestor", h, ref], cwd=ROOT, capture_output=True)
        assert r.returncode == 0, f"{h} is not on {ref}"
    assert "the coordinator fills in" not in " ".join(x.strip() for x in entry())


def test_item_search_entry_keeps_its_limits():
    assert " ".join(x.strip() for x in entry()).count(LIMITS) == 1


def test_item_search_entry_listed_once():
    gid = [e["id"] for e in intake("gaps_md") if e["title"] == TITLE]
    assert gid, "intake finds no entry titled " + TITLE
    assert gid[0] not in intake("twice")
    assert sum(line.startswith(f"- **{TITLE}**") for line in GAPS.read_text(encoding="utf-8").splitlines()) == 1
