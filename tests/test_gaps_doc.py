"""docs/GAPS.md's entry for upkeep's fault injection: done, citing only files and commits main has
(dev/records/from-upkeep-s-fault-injection.md)."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GAPS = ROOT / "docs" / "GAPS.md"
TITLE = "From upkeep's fault injection"
CITED = ("docs/roadmap/overnight/resilience-core.md", "docs/roadmap/overnight/cli-fallback.md",
         "docs/roadmap/overnight-2026-11-19.md")
HASH = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[a-f])[0-9a-f]{7,12}(?![0-9A-Za-z])")   # a hex word with a letter
PATH = re.compile(r"`([^`\s]*/[^`\s]*\.(?:md|py|jsonl))`")


def upkeep_entry(text: str) -> list[str]:
    """The *Done recently* bullet whose title starts TITLE, with its indented lines; the test fails if there is none."""
    section, out = "", None
    for line in text.splitlines():
        if out is not None:
            if line.startswith("  "):
                out.append(line)
                continue
            return out
        if line.startswith("## "):
            section = line[3:].strip()
        elif section == "Done recently" and line.startswith(f"- **{TITLE}"):
            out = [line]
    if out is None:
        pytest.fail(f"no entry titled {TITLE!r} under ## Done recently in {GAPS}")
    return out


def main_ref() -> str:
    """The ref a cited commit must be on: origin/main, else main, else HEAD; no history at all fails."""
    for ref in ("origin/main", "main", "HEAD"):
        r = subprocess.run(["git", "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    pytest.fail("no git history to check the cited commits against")


def test_upkeep_entry_is_not_found_open_by_intake():
    code = ("import sys, json; sys.path[:0] = [sys.argv[1]]; import intake; "
            "print(json.dumps(intake.gaps_md(open(sys.argv[2]).read())))")
    r = subprocess.run([sys.executable, "-c", code, str(ROOT / "dev" / "bin"), str(GAPS)], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    entries = json.loads(r.stdout.strip().splitlines()[-1])
    assert len(entries) >= 10 and any(e["section"] == "Runtime, scale and latency" for e in entries)   # it parsed
    assert not [e for e in entries if e["title"].startswith(TITLE)]
    first = upkeep_entry(GAPS.read_text())[0]
    assert first.split("**", 2)[2].lstrip().startswith("(done"), first


def test_upkeep_entry_cites_only_paths_that_exist():
    entry = "\n".join(upkeep_entry(GAPS.read_text()))
    paths = PATH.findall(entry)
    assert paths
    assert [p for p in paths if not (ROOT / p).exists()] == []
    assert [p for p in CITED if p not in entry] == []
    assert "docs/proposals/upkeep.md" not in entry


def test_upkeep_entry_cites_only_commits_on_main():
    lines = upkeep_entry(GAPS.read_text())
    hashes = HASH.findall("\n".join(lines))
    assert len(hashes) >= 2
    ref = main_ref()
    off = [h for h in hashes if subprocess.run(["git", "merge-base", "--is-ancestor", h, ref], cwd=ROOT,
                                               capture_output=True).returncode != 0]
    assert off == [], f"not on {ref}: {off}"
    problems, cur = [], None                                     # each of the five problems carries its own hash
    for line in lines[1:]:
        if line.startswith("  - **"):
            cur = [line]
            problems.append(cur)
        elif cur is not None:
            cur.append(line)
    assert len(problems) == 5 and all(HASH.search("\n".join(p)) for p in problems), problems
    if not {"3e106ee", "75e7687"} <= set(hashes):              # a substitute merge commit is said where it stopped
        record = (ROOT / "dev" / "records" / "from-upkeep-s-fault-injection.md").read_text()
        assert "## Where it stopped" in record and "substitute" in record.split("## Where it stopped", 1)[1]


def test_resilience_docstring_cites_no_missing_file():
    doc = ast.get_docstring(ast.parse((ROOT / "tests" / "test_resilience.py").read_text()))
    cited = re.findall(r"docs/[\w./-]*?\.(?:md|py|jsonl)\b", doc or "")
    assert "docs/roadmap/overnight-2026-11-19.md" in cited
    assert [p for p in cited if not (ROOT / p).exists()] == []
