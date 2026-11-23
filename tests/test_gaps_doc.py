"""GAPS.md's entries for upkeep's fault injection (dev/records/from-upkeep-s-fault-injection.md) and Remote
systems (dev/records/remote-systems.md): done, said once, citing only files and commits main has. Read from a fixture
(tests/fixtures/gaps_doc_entries.md: those entries and the IR's, as docs/GAPS.md held them at FIXTURE_COMMIT), never
the live docs/GAPS.md, which the merge queue rewrites from the records as gaps land."""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
GAPS = ROOT / "tests" / "fixtures" / "gaps_doc_entries.md"
FIXTURE_COMMIT = "278f54a403730f231134ebd5c133a3610a64e9fa"       # main when the fixture was cut from its GAPS.md
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
    assert [(e["title"], e["section"]) for e in entries] == [                                     # it parsed
        ("Remote systems", "Remote systems and libraries"), ("The IR and a Rust runtime", "Runtime, scale and latency")]
    assert not [e for e in entries if e["title"].startswith(TITLE)]
    first = upkeep_entry(GAPS.read_text())[0]
    assert first.split("**", 2)[2].lstrip().startswith("(done"), first


def test_the_fixture_is_docs_gaps_md_as_of_its_commit():
    """Each line of the fixture is a line of docs/GAPS.md at FIXTURE_COMMIT, in order (read from git, never the live
    file); a clone without that commit checks nothing here."""
    r = subprocess.run(["git", "show", f"{FIXTURE_COMMIT}:docs/GAPS.md"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        return
    there, at = r.stdout.split("\n"), 0
    for line in GAPS.read_text().rstrip("\n").split("\n"):
        assert line in there[at:], line
        at = there.index(line, at) + 1


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


# Remote systems: one entry, done, its sub-gaps each said once, its only Left the IR (handed to the IR's entry).
REMOTE = "Remote systems"
REMOTE_RECORD = ROOT / "dev" / "records" / "remote-systems.md"
SUBGAPS = ("remote-box-measures", "remote-of-remotes", "remote-mtls", "remote-process-lines", "remote-items-record")
FILE = re.compile(r"`([\w.-]+(?:/[\w.-]+)*(?:\.(?:md|py|jsonl|yaml)|/))`")     # a file or a folder/, not /remote/v1/


def entry(text: str, title: str) -> list[str]:
    """The first top-level entry titled exactly TITLE outside *Done recently*, with its indented lines; fails if none."""
    section, out = "", None
    for line in text.splitlines():
        if out is not None:
            if line.startswith("  "):
                out.append(line)
                continue
            return out
        if line.startswith("## "):
            section = line[3:].strip()
        elif section != "Done recently" and line.startswith(f"- **{title}**"):
            out = [line]
    if out is None:
        pytest.fail(f"no entry titled {title!r} in {GAPS}")
    return out


def clauses(lines: list[str], name: str) -> list[str]:
    """Each `  - *NAME*` clause of an entry, joined over its own indented lines."""
    out, cur = [], None
    for line in lines[1:]:
        if line.startswith("  - "):
            cur = [line] if line.startswith(f"  - *{name}*") else None
            if cur is not None:
                out.append(cur)
        elif cur is not None:
            cur.append(line)
    return [" ".join(x.strip() for x in c) for c in out]


def remote_problems(lines: list[str]) -> list[str]:
    """What is wrong with a Remote systems entry: a splice's marks (two Done or Left, a sub-gap said twice, a line
    resuming mid-sentence) and a Left naming anything but the IR. Empty when it is whole."""
    text = "\n".join(lines)
    problems = []
    if len(clauses(lines, "Done")) != 1:
        problems.append(f"{len(clauses(lines, 'Done'))} Done clauses")
    lefts = clauses(lines, "Left")
    if len(lefts) > 1:
        problems.append(f"{len(lefts)} Left clauses")
    for left in lefts:               # an allowlist: every item of a Left is about the IR
        problems += [f"a Left item not about the IR: {part!r}" for part in left.split(":", 1)[1].split(";")
                     if not re.search(r"\bIR\b", part)]
    problems += [f"{s} said {text.count(f'`{s}`')} times" for s in SUBGAPS if text.count(f"`{s}`") != 1]
    for a, b in zip(lines, lines[1:], strict=False):
        if a.rstrip().endswith(".") and re.match(r"\s+[a-z]", b) and not b.lstrip().startswith("- "):
            problems.append(f"a line resumes mid-sentence after a full stop: {b.strip()!r}")
    if re.search(r"Items|Record|composed of remotes|imported", " ".join(lefts)):
        problems.append("a Left says the Items/Record pages or a remote of remotes is left")
    return problems


def run_bin(code: str, data: str) -> object:
    """CODE run with dev/bin on its path and DATA on stdin; its last line read as JSON."""
    r = subprocess.run([sys.executable, "-c", "import sys, json; sys.path[:0] = [sys.argv[1]]; " + code,
                        str(ROOT / "dev" / "bin")], input=data, cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_remote_systems_entry_is_found_done_by_intake():
    text = GAPS.read_text()
    first = entry(text, REMOTE)[0]
    spliced = text.replace(first, "- **Remote systems** (first slice done, 72da4e1, merged from `remote`; what is "
                                  "left below is open;", 1)
    said = run_bin("import intake; print(json.dumps([intake.gaps_md(t) for t in json.load(sys.stdin)]))",
                   json.dumps([text, spliced]))
    entries, spliced_entries = said
    mine = [e for e in entries if e["title"] == REMOTE]                   # (once: twice would be neither found nor done)
    assert [(e["section"], e["gaps_says"]) for e in mine] == [("Remote systems and libraries", "done")], mine
    assert [e["gaps_says"] for e in spliced_entries if e["title"] == REMOTE] == ["open"]      # the check can fail


def test_remote_systems_entry_has_one_done_and_no_stale_left():
    lines = entry(GAPS.read_text(), REMOTE)
    assert remote_problems(lines) == []
    assert len(clauses(lines, "Left")) <= 1 and len(clauses(lines, "Done")) == 1
    mtls = [n for n, ln in enumerate(lines) if "Mutual TLS" in ln]
    assert mtls
    for spliced in (lines + ["  - *Left*: the remote's events in the Items and Record pages; serving the IR."],
                    lines + lines[mtls[0]:mtls[0] + 3],
                    lines + ["    measures on its closed box (done on a branch)."],
                    lines[:1] + [ln for ln in lines[1:] if not ln.startswith("  - *Done*")]):
        assert remote_problems(spliced), spliced                                           # each splice is seen


def test_ir_entry_holds_remote_ir_serving():
    ir = "\n".join(entry(GAPS.read_text(), "The IR and a Rust runtime"))
    assert "format=ir" in ir and "ergostat-model/1" in ir, ir
    assert "docs/proposals/remote-systems.md" in ir
    left = (ROOT / "docs" / "proposals" / "remote-systems.md").read_text().split("**Left for later**", 1)[1]
    left, built = left.split("are built:", 1)        # what is still left, then the list of what was built
    assert "format=ir" in left and "Items" not in left and "Record" not in left, left
    assert "`remote-items-record`" in built.split("## ", 1)[0]


def test_remote_systems_record_entry_is_whole():
    """The record's own Entry (what GAPS.md is rendered from), not the fixture: parsed, in its section, and with no
    splice's marks (remote_problems), so it is checked as it moves on and never pinned to a copy."""
    record = REMOTE_RECORD.read_text()
    said = run_bin("import gapsdoc\ntry: print(json.dumps(gapsdoc.parse(sys.stdin.read())))\n"
                   "except ValueError as e: print(json.dumps({'problem': str(e)}))", record)
    assert said and "problem" not in said, said
    assert said["section"] == "Remote systems and libraries" and said["entry_of"] is None
    assert said["bullet"][0].startswith(f"- **{REMOTE}** (done") and remote_problems(said["bullet"]) == []
    assert "problem" in run_bin("import gapsdoc\ntry: print(json.dumps(gapsdoc.parse(sys.stdin.read())))\n"
                                "except ValueError as e: print(json.dumps({'problem': str(e)}))",
                                record.replace("\n  (Owner, 2026-11-18.)", "\n\n  (Owner, 2026-11-18.)", 1))


def test_remote_systems_entry_cites_only_paths_and_commits_that_exist():
    lines = entry(GAPS.read_text(), REMOTE)
    text = "\n".join(lines)
    paths = FILE.findall(text)
    assert {"docs/proposals/remote-systems.md", "examples/remote-pair/", "tests/test_remote.py",
            "tests/test_remote_items.py"} <= set(paths), paths
    assert [p for p in paths if not (ROOT / p).exists()] == []
    flat = " ".join(x.strip() for x in lines)
    for s in SUBGAPS:                                 # each sub-gap said done names the tests that show it
        assert re.search(rf"`{s}`, `tests/test_[\w]+\.py`", flat), s
    hashes = HASH.findall(text)
    assert "72da4e1" in hashes
    ref = main_ref()
    off = [h for h in hashes if subprocess.run(["git", "merge-base", "--is-ancestor", h, ref], cwd=ROOT,
                                               capture_output=True).returncode != 0]
    assert off == [], f"not on {ref}: {off}"
