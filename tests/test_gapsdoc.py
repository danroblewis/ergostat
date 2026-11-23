"""dev/bin/gapsdoc.py: a GAPS.md entry as a form in its gap's record (`## Entry`), GAPS.md rendered from the records
and split back into them (dev/records/merge-pipeline-gaps-entries-in-records.md). The round trip is pinned to a copy
of docs/GAPS.md as of a named commit, never to the moving file."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "dev" / "bin"
if str(BIN) not in sys.path:
    sys.path.append(str(BIN))          # appended: dev/bin/queue.py must not shadow the standard library's queue

import gapsdoc  # noqa: E402

PINNED = ROOT / "tests" / "fixtures" / "gaps_md_pinned.md"
PINNED_COMMIT = "277a9c6c29e3d737019fd3424dbc34dcd7fc1ff0"      # main when this gap was built on it
PINNED_BLOB = "50fb3b5cef194119f602fee06260f1543e293a79"        # git rev-parse PINNED_COMMIT:docs/GAPS.md


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fixture() -> str:
    return PINNED.read_text(encoding="utf-8")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def test_the_fixture_is_docs_gaps_md_as_of_the_pinned_commit():
    assert blob_sha(PINNED.read_bytes()) == PINNED_BLOB
    shown = git(ROOT, "rev-parse", f"{PINNED_COMMIT}:docs/GAPS.md")
    if shown.returncode == 0:                      # a clone without that commit still checks the content's sha
        assert shown.stdout.strip() == PINNED_BLOB


def test_render_of_split_gives_the_pinned_gaps_md_back_line_for_line():
    s = gapsdoc.split(fixture())
    text, problems = gapsdoc.render(s["records"], s["head"])
    assert text.split("\n") == fixture().split("\n")
    assert s["dropped"] == []                      # the pinned copy has no exact duplicate
    assert len(s["records"]) == fixture().count("\n- **")       # every top entry (nested '  - **' lines are not)
    # its two different 'External event logs' entries: both kept, and said by name, in split and in render
    assert s["problems"] == ["External event logs: line 84 slugs to external-event-logs as an earlier entry does; "
                             "kept as external-event-logs-2"]
    assert problems == ["external-event-logs, external-event-logs-2: their entries' titles slug to one branch, "
                        "external-event-logs"]


def entry_block(text: str, title: str) -> list[str]:
    lines = text.split("\n")
    n = next(i for i, ln in enumerate(lines) if ln.startswith(f"- **{title}**"))
    end = n + 1
    while lines[end].startswith("  "):
        end += 1
    return lines[n:end]


LEASE, JOB = "A run whose lease expired is killed", "Remodel `the-job`"


def with_duplicates() -> tuple[str, int, int]:
    """The pinned copy with two exact duplicates a union merge could leave: one entry repeated next to itself, one
    repeated at the end of *Done recently*, another section. Returns the text and the two duplicates' first lines."""
    lines = fixture().split("\n")
    lease, job = entry_block(fixture(), LEASE), entry_block(fixture(), JOB)
    at = lines.index(lease[0]) + len(lease)
    lines[at:at] = lease
    end = len(lines) - 1                           # before the file's last newline
    lines[end:end] = job
    return "\n".join(lines), at + 1, end + 1


def test_exact_duplicates_are_dropped_and_each_named_by_entry_and_line():
    text, lease_at, job_at = with_duplicates()
    s = gapsdoc.split(text)
    rendered, _ = gapsdoc.render(s["records"], s["head"])
    assert rendered.split("\n") == fixture().split("\n")
    lines = fixture().split("\n")
    lease_first = lines.index(entry_block(fixture(), LEASE)[0]) + 1
    job_first = lines.index(entry_block(fixture(), JOB)[0]) + 1 + 2      # the lease's 2 lines inserted above it
    assert s["dropped"] == [f"{LEASE}: line {lease_at} repeats line {lease_first} exactly; dropped",
                            f"{JOB}: line {job_at} repeats line {job_first} exactly; dropped"]


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BIN / "gapsdoc.py"), *args], capture_output=True, text=True)


def test_split_dry_run_lists_every_duplicate_it_drops(tmp_path):
    text, lease_at, job_at = with_duplicates()
    (tmp_path / "GAPS.md").write_text(text)
    r = run("split", "--dry-run", str(tmp_path / "GAPS.md"))
    assert r.returncode == 0, r.stderr
    dups = [ln for ln in r.stdout.splitlines() if ln.startswith("duplicate ")]
    assert dups == [f"duplicate {d}" for d in gapsdoc.split(text)["dropped"]]
    assert f"{LEASE}: line {lease_at} repeats" in dups[0] and f"{JOB}: line {job_at} repeats" in dups[1]
    assert "problem External event logs: line 84 slugs to external-event-logs" in r.stdout
    assert run("split", str(tmp_path / "GAPS.md")).returncode == 2       # (split itself takes no FILE: docs/GAPS.md)


HEAD = "# Known gaps\n\nIntro.\n\n## Remote\n\n@entry remote-systems\n\n## Done recently\n"
UMBRELLA = """# remote-systems: the umbrella

## Entry

section: Remote
done: 2026-11-18 The read-only remote API.

- **Remote systems** (open; `remote-systems`): a system run by another instance.
  - *Left*: the IR.
"""


def sub(name: str, date: str, sentence: str) -> str:
    return f"# {name}: a sub-gap\n\nSome definition.\n\n## Entry\n\nentry-of: remote-systems\ndone: {date} {sentence}\n"


def records_in(repo: Path) -> dict[str, str]:
    return {p.stem: p.read_text() for p in sorted((repo / "dev" / "records").glob("*.md")) if p.name != "GAPS-head.md"}


def test_two_sub_gaps_of_one_umbrella_merge_with_no_conflict_and_both_render_once(tmp_path):
    repo = tmp_path / "repo"
    (repo / "dev" / "records").mkdir(parents=True)
    git(tmp_path, "init", "-q", "-b", "main", str(repo))
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
        git(repo, "config", k, v)
    (repo / "dev" / "records" / "remote-systems.md").write_text(UMBRELLA)
    (repo / "dev" / "records" / "GAPS-head.md").write_text(HEAD)
    git(repo, "add", "-A")
    assert git(repo, "commit", "-qm", "umbrella").returncode == 0
    for branch, date, sentence in (("remote-mtls", "2026-11-21", "Mutual TLS."),
                                   ("remote-box-measures", "2026-11-20", "A remote's measures on its box.")):
        git(repo, "checkout", "-qb", branch, "main")
        (repo / "dev" / "records" / f"{branch}.md").write_text(sub(branch, date, sentence))
        git(repo, "add", "-A")
        assert git(repo, "commit", "-qm", branch).returncode == 0
    git(repo, "checkout", "-q", "main")
    for branch in ("remote-mtls", "remote-box-measures"):
        r = git(repo, "merge", "-q", "--no-edit", branch)
        assert r.returncode == 0, r.stdout + r.stderr
    text, problems = gapsdoc.render(records_in(repo), HEAD)
    assert problems == []
    assert text.count("Mutual TLS.") == 1 and text.count("A remote's measures on its box.") == 1
    assert text.split("\n")[6:11] == [
        "- **Remote systems** (open; `remote-systems`): a system run by another instance.",
        "  - *Left*: the IR.",
        "  - *Done 2026-11-18* (`remote-systems`): The read-only remote API.",
        "  - *Done 2026-11-20* (`remote-box-measures`): A remote's measures on its box.",     # date order, not name
        "  - *Done 2026-11-21* (`remote-mtls`): Mutual TLS.",
    ]


def test_an_entry_the_head_does_not_list_renders_after_its_sections_last():
    other = UMBRELLA.replace("Remote systems", "Another remote thing").replace("done: 2026-11-18 The read-only remote "
                                                                               "API.\n", "")
    text, problems = gapsdoc.render({"remote-systems": UMBRELLA, "another": other}, HEAD)
    assert problems == []
    lines = text.split("\n")
    assert lines[lines.index("  - *Done 2026-11-18* (`remote-systems`): The read-only remote API.") + 1] == \
        "- **Another remote thing** (open; `remote-systems`): a system run by another instance."


def test_entries_the_head_places_badly_or_not_at_all_are_rendered_and_named():
    done = UMBRELLA.replace("section: Remote", "section: Done recently").replace("Remote systems", "Old thing")
    away = UMBRELLA.replace("section: Remote", "section: Elsewhere").replace("Remote systems", "Far thing")
    text, problems = gapsdoc.render({"remote-systems": UMBRELLA, "old": done, "far": away}, HEAD)
    assert text.endswith("## Done recently\n\n- **Old thing** (open; `remote-systems`): a system run by another "
                         "instance.\n  - *Left*: the IR.\n  - *Done 2026-11-18* (`old`): The read-only remote API.\n"
                         "\n## Elsewhere\n\n- **Far thing** (open; `remote-systems`): a system run by another "
                         "instance.\n  - *Left*: the IR.\n  - *Done 2026-11-18* (`far`): The read-only remote API.\n")
    assert problems == ["far: section 'Elsewhere' is not in GAPS-head.md; added at the end"]
    head = HEAD.replace("## Done recently\n", "## Done recently\n\n@entry remote-systems\n")
    text, problems = gapsdoc.render({"remote-systems": UMBRELLA}, head)
    assert text.count("- **Remote systems**") == 1
    assert problems == ["remote-systems: GAPS-head.md lists it twice; rendered once"]
    text, problems = gapsdoc.render({"remote-systems": UMBRELLA}, head.replace("\n@entry remote-systems\n\n## D",
                                                                                "\n\n## D"))
    assert text.index("- **Remote systems**") > text.index("## Done recently")
    assert problems == ["remote-systems: its entry says section 'Remote', but GAPS-head.md lists it under "
                        "'Done recently'; rendered where listed"]


MALFORMED = {
    "no-section": UMBRELLA.replace("section: Remote\n", ""),
    "bad-date": UMBRELLA.replace("2026-11-18", "2026-13-40"),
    "no-date": UMBRELLA.replace("done: 2026-11-18 ", "done: "),
    "stray-line": UMBRELLA.replace("section: Remote\n", "section: Remote\nstate: open\n"),
    "unindented": UMBRELLA.replace("  - *Left*", "- *Left*"),
    "blank-inside": UMBRELLA.replace("  - *Left*", "\n  - *Left*"),
    "no-bullet": "## Entry\n\nsection: Remote\n",
    "sub-with-bullet": UMBRELLA.replace("section: Remote\n", "entry-of: other\n"),
    "sub-no-done": "## Entry\n\nentry-of: remote-systems\n",
    "two-sections": UMBRELLA + "\n## Entry\n\nsection: Remote\n",
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_a_malformed_entry_is_reported_by_name_never_skipped(name):
    text, problems = gapsdoc.render({"remote-systems": UMBRELLA, name: MALFORMED[name]}, HEAD)
    assert [p for p in problems if p.startswith(f"{name}: malformed Entry: ")], problems
    assert "- **Remote systems**" in text


def test_two_entries_slugging_to_one_branch_are_named_and_both_rendered():
    twin = UMBRELLA.replace("**Remote systems**", "**Remote: systems**")
    text, problems = gapsdoc.render({"remote-systems": UMBRELLA, "remote-twin": twin}, HEAD)
    assert problems == ["remote-systems, remote-twin: their entries' titles slug to one branch, remote-systems"]
    assert text.count("- **Remote systems**") == 1 and text.count("- **Remote: systems**") == 1


def test_two_titles_that_differ_only_past_32_slug_characters_are_named_as_one_branch():
    # intake: two gap ids (slug at 60), one branch (the id cut to 32, dev/bin/intake.py:226), so one worktree and record
    a = UMBRELLA.replace("**Remote systems**", "**Remote systems keep their measures when the link drops**")
    b = UMBRELLA.replace("**Remote systems**", "**Remote systems keep their measures across restarts**")
    ida, idb = (gapsdoc.gap_id(t) for t in ("Remote systems keep their measures when the link drops",
                                            "Remote systems keep their measures across restarts"))
    assert ida != idb                              # not caught by the gap id: only by the 32-char branch
    head = HEAD.replace("@entry remote-systems", "@entry remote-a\n@entry remote-b")
    text, problems = gapsdoc.render({"remote-a": a, "remote-b": b}, head)
    assert problems == ["remote-a, remote-b: their entries' titles slug to one branch, remote-systems-keep-their"]
    assert "measures when the link drops**" in text and "measures across restarts**" in text


def test_a_sub_gap_whose_umbrella_has_no_entry_and_a_listed_entry_with_none_are_named():
    _, problems = gapsdoc.render({"remote-mtls": sub("remote-mtls", "2026-11-21", "Mutual TLS.")}, HEAD)
    assert any(p.startswith("remote-mtls: entry-of: remote-systems, which has no top entry") for p in problems)
    assert any(p.startswith("remote-systems: GAPS-head.md lists it, but it has no top entry") for p in problems)


def cli_tree(tmp_path: Path, monkeypatch, records: dict[str, str], head: str | None = HEAD) -> None:
    rec = tmp_path / "dev" / "records"
    rec.mkdir(parents=True)
    for name, text in records.items():
        (rec / f"{name}.md").write_text(text)
    if head is not None:
        (rec / "GAPS-head.md").write_text(head)
    monkeypatch.setattr(gapsdoc, "ROOT", tmp_path)
    monkeypatch.setattr(gapsdoc, "RECORDS", rec)
    monkeypatch.setattr(gapsdoc, "HEAD", rec / "GAPS-head.md")


def test_render_check_exits_1_on_a_malformed_entry_and_0_when_clean(tmp_path, monkeypatch, capsys):
    cli_tree(tmp_path, monkeypatch, {"remote-systems": UMBRELLA, "no-date": MALFORMED["no-date"]})
    assert gapsdoc.main(["render", "--check"]) == 1
    err = capsys.readouterr()
    assert "gapsdoc: no-date: malformed Entry: done line" in err.err and err.out == ""
    (tmp_path / "dev" / "records" / "no-date.md").unlink()
    assert gapsdoc.main(["render", "--check"]) == 0
    assert gapsdoc.main(["render"]) == 0
    assert capsys.readouterr().out.startswith("# Known gaps\n")


def test_render_check_exits_1_on_a_slug_collision_and_without_a_head(tmp_path, monkeypatch, capsys):
    twin = UMBRELLA.replace("**Remote systems**", "**Remote: systems**")
    cli_tree(tmp_path, monkeypatch, {"remote-systems": UMBRELLA, "remote-twin": twin})
    assert gapsdoc.main(["render", "--check"]) == 1
    assert "remote-systems, remote-twin: their entries' titles slug to one branch" in capsys.readouterr().err
    (tmp_path / "dev" / "records" / "GAPS-head.md").unlink()
    assert gapsdoc.main(["render", "--check"]) == 1
    assert "GAPS-head.md is missing" in capsys.readouterr().err


def test_the_definition_prompt_shows_the_entry_shape():
    text = (ROOT / "dev" / "prompts" / "definition.md").read_text()
    e = gapsdoc.parse(text)
    assert e is not None and e["section"] and e["bullet"] and e["done"]
    assert "entry-of:" in text


# ---- merge-pipeline-gaps-md-regenerated-on-land: split written once; a landing carries its GAPS.md edits, renders

MTLS = "# remote-mtls: mutual TLS\n\n## Definition of done\n\nIt works.\n"


def test_split_appends_each_entry_to_its_record_and_never_overwrites(tmp_path, monkeypatch):
    own = "# external-event-logs: a definition\n\n## Definition of done\n\nIt works.\n"
    cli_tree(tmp_path, monkeypatch, {"external-event-logs": own}, head=None)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "GAPS.md").write_text(fixture())
    s = gapsdoc.split(fixture())
    assert gapsdoc.main(["split"]) == 0
    rec = tmp_path / "dev" / "records"
    kept = (rec / "external-event-logs.md").read_text()
    assert kept.startswith(own + "\n## Entry\n")                       # appended at the end of the definition
    assert gapsdoc.parse(kept) == gapsdoc.parse(s["records"]["external-event-logs"])
    assert (rec / "GAPS-head.md").read_text() == s["head"]
    records = {p.stem: p.read_text() for p in rec.glob("*.md") if p.name != "GAPS-head.md"}
    assert set(records) == set(s["records"]) and max(map(len, records)) <= 32     # each named as intake's branch
    assert gapsdoc.render(records, s["head"])[0] == fixture()
    before = {p: p.read_text() for p in rec.glob("*.md")}
    assert gapsdoc.main(["split"]) == 1                                # once: a second run never overwrites
    assert {p: p.read_text() for p in rec.glob("*.md")} == before


SPLIT_COMMIT = "b8334bfc6722d3555a1807f852aba3e85fd6e713"     # `gapsdoc.py split`, run once on main's GAPS.md


def files_at(ref: str) -> dict[str, str]:
    """docs/GAPS.md and dev/records as commit ``ref`` holds them, by path."""
    names = git(ROOT, "ls-tree", "-r", "--name-only", ref, "--", "docs/GAPS.md", "dev/records/").stdout.split()
    return {n: git(ROOT, "show", f"{ref}:{n}").stdout for n in names}


def test_the_split_commit_moves_every_entry_into_the_records_and_every_reader_sees_the_same():
    import deps
    import fac
    import intake
    assert git(ROOT, "cat-file", "-e", f"{SPLIT_COMMIT}^{{commit}}").returncode == 0
    before, after = files_at(f"{SPLIT_COMMIT}^"), files_at(SPLIT_COMMIT)
    gaps = before["docs/GAPS.md"]
    assert after["docs/GAPS.md"] == gaps                           # GAPS.md itself is not changed by the split
    s = gapsdoc.split(gaps)
    assert after["dev/records/GAPS-head.md"] == s["head"]
    for name, entry in s["records"].items():                       # each appended, nothing overwritten
        was = before.get(f"dev/records/{name}.md", "")
        assert after[f"dev/records/{name}.md"] == (was.rstrip("\n") + "\n\n" + entry if was.strip() else entry), name
        assert was or fac.entry_only(entry)                        # a new record is no definition (intake, fac)
    made = {f"dev/records/{n}.md" for n in s["records"]} | {"dev/records/GAPS-head.md"}
    assert {p for p in after if p not in before} == made - set(before)          # nothing else made
    records = {Path(p).stem: t for p, t in after.items() if p.startswith("dev/records/") and "GAPS-head" not in p}
    text, problems = gapsdoc.render(records, s["head"])
    assert text == gaps and problems and all(gapsdoc.BENIGN.search(p) for p in problems)   # (the two External logs)
    assert intake.gaps_md(text) == intake.gaps_md(gaps) and intake.twice(text) == intake.twice(gaps)  # gaps, closes
    assert deps.from_gaps(text) == deps.from_gaps(gaps)            # links and their sources


def tree(root: Path, records: dict[str, str]) -> str:
    """dev/records under ``root`` (with HEAD) and docs/GAPS.md their render, as main holds them: that GAPS.md."""
    (root / "dev" / "records").mkdir(parents=True)
    (root / "docs").mkdir()
    for name, text in {**records, "GAPS-head": HEAD}.items():
        (root / "dev" / "records" / f"{name}.md").write_text(text)
    text, problems = gapsdoc.render(records, HEAD)
    assert problems == []
    (root / "docs" / "GAPS.md").write_text(text)
    return text


NOBODY = "- **Nobody's gap** (open): no record has it yet.\n"
STRAY = "- **Stray** (open): a done line under the wrong entry.\n  - *Done 2026-11-23* (`remote-systems`): not its own.\n"


def edited(pre: str) -> str:
    """GAPS.md as a branch approved before the records took the entries edits it: a bullet line changed, a done line
    of a sub-gap under its umbrella, and a new entry no record has yet."""
    return pre.replace("  - *Left*: the IR.\n", "  - *Left*: the IR, and the API.\n").replace(
        "The read-only remote API.\n", "The read-only remote API.\n  - *Done 2026-11-23* (`remote-mtls`): Mutual "
        "TLS, every link.\n" + NOBODY)


def test_carry_puts_a_batchs_own_gaps_md_edits_in_the_named_records():
    records = {"remote-systems": UMBRELLA, "remote-mtls": MTLS}
    pre = gapsdoc.render(records, HEAD)[0]
    changed, carried, lost, head = gapsdoc.carry(pre, edited(pre) + STRAY, records, HEAD)
    assert sorted(changed) == ["nobody-s-gap", "remote-mtls", "remote-systems"] and carried == [
        "remote-systems: - **Remote systems** (open; `remote-systems`): a system run by another instance.",
        "nobody-s-gap: - **Nobody's gap** (open): no record has it yet.",
        "GAPS-head.md: the batch's GAPS.md text outside the entries"]
    assert lost == [STRAY.strip()]                                     # placed nowhere: said, never dropped
    assert changed["nobody-s-gap"] == f"## Entry\n\nsection: Remote\n\n{NOBODY}"   # a new entry: its record made
    assert head == HEAD.replace("@entry remote-systems\n", "@entry remote-systems\n@entry nobody-s-gap\n")
    assert changed["remote-mtls"].startswith(MTLS)                     # its definition kept, its Entry after it
    assert gapsdoc.parse(changed["remote-mtls"])["entry_of"] == "remote-systems"
    assert gapsdoc.parse(changed["remote-systems"])["bullet"][1] == "  - *Left*: the IR, and the API."
    text, problems = gapsdoc.render({**records, **changed}, head)
    assert problems == [] and text == edited(pre)                      # where the branch put it
    assert gapsdoc.carry(text, text, {**records, **changed}, head) == ({}, [], [], head)   # nothing new: nothing


def test_an_entry_whose_branch_names_another_titles_record_is_kept_unplaced():
    long = "A title long enough that its branch"                    # its gap ids differ, its branches do not
    records = {"remote-systems": UMBRELLA, gapsdoc.fac.slug(gapsdoc.gap_id(long), 32): UMBRELLA.replace(
        "Remote systems", f"{long} characters").replace("done: 2026-11-18 The read-only remote API.\n", "")}
    pre = gapsdoc.render(records, HEAD)[0]
    other = f"- **{long} letters** (open): another gap, the same branch.\n"
    changed, carried, lost, _ = gapsdoc.carry(pre, pre + other, records, HEAD)
    assert changed == {} and lost == [other.strip()]                   # never written over the other title's Entry


TWIN = UMBRELLA.replace("(open; `remote-systems`): a system run by another instance.\n  - *Left*: the IR.",
                        "(mirroring done): the second entry.\n  - *Left*: nothing.").replace(
    "done: 2026-11-18 The read-only remote API.\n", "")


@pytest.mark.parametrize("line, owner", [("  - *Left*: the IR.", "remote-systems"),
                                         ("  - *Left*: nothing.", "remote-systems-2")])
def test_two_records_of_one_title_each_keep_their_entry_when_either_is_edited(line, owner):
    # (dev/records/external-event-logs.md and external-event-logs-2.md: one title, two entries)
    records = {"remote-systems": UMBRELLA, "remote-systems-2": TWIN}
    pre = gapsdoc.render(records, HEAD)[0]
    assert pre.count("- **Remote systems**") == 2
    batch = pre.replace(line, line[:-1] + ", edited.")
    changed, carried, lost, head = gapsdoc.carry(pre, batch, records, HEAD)
    assert list(changed) == [owner] and lost == [] and len(carried) == 1
    assert carried[0].startswith(f"{owner}: - **Remote systems**")
    assert gapsdoc.render({**records, **changed}, head)[0] == batch    # both entries, the edit in its own record


def test_two_edits_of_one_entry_keep_the_first_in_its_record_and_the_other_said_never_lost():
    records = {"remote-systems": UMBRELLA}
    pre = gapsdoc.render(records, HEAD)[0]
    block = "\n".join(gapsdoc.split(pre)["records"]["remote-systems"].split("\n")[4:-1])
    one, two = block.replace("the IR.", "the IR, one."), block.replace("the IR.", "the IR, two.")
    changed, _, lost, _ = gapsdoc.carry(pre, pre.replace(block, f"{one}\n{two}"), records, HEAD)   # a union merge's
    assert gapsdoc.parse(changed["remote-systems"])["bullet"][1] == "  - *Left*: the IR, one."
    assert lost == [two]                                               # not written over the first: kept, said
    new = TWIN.replace("the second entry", "a third entry")            # another entry of the title: its own record
    changed, _, lost, _ = gapsdoc.carry(pre, pre + "\n".join(new.split("\n")[6:]), records, HEAD)
    assert list(changed) == ["remote-systems-2"] and lost == [] and "a third entry" in changed["remote-systems-2"]


def test_regenerate_writes_the_records_and_gaps_md_and_keeps_what_it_cannot_place(tmp_path):
    pre = tree(tmp_path, {"remote-systems": UMBRELLA, "remote-mtls": MTLS})
    (tmp_path / "docs" / "GAPS.md").write_text(edited(pre) + STRAY)   # the batch's merge, as main holds it
    got = gapsdoc.regenerate(tmp_path, pre)
    assert got["unplaced"] == [STRAY.strip()] and len(got["carried"]) == 3 and got["problems"] == []
    assert sorted(got["files"]) == ["dev/records/GAPS-head.md", "dev/records/GAPS-unplaced.md",
                                    "dev/records/nobody-s-gap.md", "dev/records/remote-mtls.md",
                                    "dev/records/remote-systems.md", "docs/GAPS.md"]
    assert (tmp_path / "docs" / "GAPS.md").read_text() == edited(pre)
    assert STRAY.strip() in (tmp_path / "dev" / "records" / "GAPS-unplaced.md").read_text()
    again = gapsdoc.regenerate(tmp_path, (tmp_path / "docs" / "GAPS.md").read_text())    # the next landing: no change
    assert again["carried"] == [] and again["files"] == ["docs/GAPS.md"]


def test_a_batchs_edit_outside_the_entries_is_carried_into_the_head(tmp_path):
    def prose(text: str) -> str:                       # the preamble, a section's prose and a new section heading
        return text.replace("Intro.\n", "Intro, said again.\n").replace(
            "## Remote\n", "## Remote\n\nThe section's prose.\n").replace("## Done recently\n", "## Proposed\n\n## Done "
                                                                          "recently\n")
    pre = tree(tmp_path, {"remote-systems": UMBRELLA, "remote-mtls": MTLS})
    (tmp_path / "docs" / "GAPS.md").write_text(prose(pre))
    got = gapsdoc.regenerate(tmp_path, pre)
    assert got["carried"] == ["GAPS-head.md: the batch's GAPS.md text outside the entries"] and not got["unplaced"]
    assert sorted(got["files"]) == ["dev/records/GAPS-head.md", "docs/GAPS.md"]
    assert (tmp_path / "docs" / "GAPS.md").read_text() == prose(pre)       # never reverted by the render
    assert (tmp_path / "dev" / "records" / "GAPS-head.md").read_text() == prose(HEAD)


def test_an_entry_the_batch_deleted_loses_its_entry_in_the_records_and_stays_gone(tmp_path):
    nobody = f"## Entry\n\nsection: Remote\n\n{NOBODY}"
    mtls = sub("remote-mtls", "2026-11-21", "Mutual TLS.")
    pre = tree(tmp_path, {"remote-systems": UMBRELLA, "remote-mtls": mtls, "nobody-s-gap": nobody})
    batch = "\n".join(ln for ln in pre.split("\n") if not ln.startswith(("- **", "  ")))   # both entries deleted
    (tmp_path / "docs" / "GAPS.md").write_text(batch)
    got = gapsdoc.regenerate(tmp_path, pre)
    assert got["carried"] == ["nobody-s-gap: its Entry removed, as the batch removed it from GAPS.md",
                              "remote-systems: its Entry removed, as the batch removed it from GAPS.md",
                              "GAPS-head.md: the batch's GAPS.md text outside the entries"] and not got["unplaced"]
    rec = tmp_path / "dev" / "records"
    assert "dev/records/nobody-s-gap.md" in got["files"] and not (rec / "nobody-s-gap.md").exists()  # Entry-only: gone
    assert (rec / "remote-systems.md").read_text() == "# remote-systems: the umbrella\n"   # its definition kept
    assert (rec / "remote-mtls.md").read_text() == "# remote-mtls: a sub-gap\n\nSome definition.\n"   # (its done line)
    assert (tmp_path / "docs" / "GAPS.md").read_text() == batch and "Remote systems" not in batch   # never drawn again


def test_one_of_two_records_of_a_title_deleted_removes_only_its_entry():
    records = {"remote-systems": UMBRELLA, "remote-systems-2": TWIN}
    pre = gapsdoc.render(records, HEAD)[0]
    batch = pre.replace("- **Remote systems** (mirroring done): the second entry.\n  - *Left*: nothing.\n", "")
    changed, carried, lost, head = gapsdoc.carry(pre, batch, records, HEAD)
    assert changed == {"remote-systems-2": "# remote-systems: the umbrella\n"} and lost == []
    assert carried[0].startswith("remote-systems-2: its Entry")
    assert gapsdoc.render({**records, **changed}, head)[0] == batch


def test_an_entry_the_batch_left_stale_or_unplaced_is_never_removed():
    records = {"remote-systems": UMBRELLA}
    pre = gapsdoc.render(records, HEAD)[0]
    newer = {"remote-systems": UMBRELLA.replace("the IR.", "the IR, in the record.")}   # the batch edited the record
    assert gapsdoc.carry(pre, pre, newer, HEAD) == ({}, [], [], HEAD)   # and left GAPS.md as it was: not a deletion


def test_a_new_or_retitled_entry_written_only_in_its_record_is_kept_and_drawn(tmp_path):
    # (after this gap a new gap writes its entry only as its record's Entry, and must not edit GAPS.md)
    pre = tree(tmp_path, {"remote-systems": UMBRELLA})
    rec = tmp_path / "dev" / "records"
    new = f"# nobody-s-gap: a new gap\n\nIts definition.\n\n## Entry\n\nsection: Remote\n\n{NOBODY}"
    (rec / "nobody-s-gap.md").write_text(new)
    retitled = UMBRELLA.replace("**Remote systems**", "**Remote instances**")
    (rec / "remote-systems.md").write_text(retitled)
    got = gapsdoc.regenerate(tmp_path, pre)                       # GAPS.md as main had it: the batch never edited it
    assert got["carried"] == [] and got["unplaced"] == []
    assert (rec / "nobody-s-gap.md").read_text() == new and (rec / "remote-systems.md").read_text() == retitled
    text = (tmp_path / "docs" / "GAPS.md").read_text()
    assert NOBODY in text and "- **Remote instances**" in text and "- **Remote systems**" not in text


def test_a_record_only_entry_kept_out_of_gaps_md_by_a_failed_render_is_drawn_at_the_next_landing(tmp_path):
    shown = tree(tmp_path, {"remote-systems": UMBRELLA})                 # docs/GAPS.md as main holds it
    rec = tmp_path / "dev" / "records"
    new = f"# nobody-s-gap: a new gap\n\nIts definition.\n\n## Entry\n\nsection: Remote\n\n{NOBODY}"
    (rec / "nobody-s-gap.md").write_text(new)                           # the first batch: a record-only Entry ...
    (rec / "no-date.md").write_text(MALFORMED["no-date"])               # ... and a malformed record
    with pytest.raises(ValueError, match="no-date: malformed Entry"):
        gapsdoc.regenerate(tmp_path, shown, shown)
    assert (tmp_path / "docs" / "GAPS.md").read_text() == shown and NOBODY not in shown   # lands without the render
    (rec / "no-date.md").unlink()                                       # the next batch mends it
    records = {p.stem: p.read_text() for p in rec.glob("*.md") if p.stem != "GAPS-head"}
    pre = gapsdoc.render(records, HEAD)[0]                              # rendered_at(pre): it draws the new entry
    assert NOBODY in pre
    got = gapsdoc.regenerate(tmp_path, pre, shown)                      # judged against the GAPS.md main held
    assert got["carried"] == [] and got["unplaced"] == []
    assert (rec / "nobody-s-gap.md").read_text() == new and NOBODY in (tmp_path / "docs" / "GAPS.md").read_text()


def test_an_entry_moved_to_another_section_moves_its_record_and_is_drawn_once():
    records = {"remote-systems": UMBRELLA}
    pre = gapsdoc.render(records, HEAD)[0]
    block = "\n".join(gapsdoc.split(pre)["records"]["remote-systems"].split("\n")[4:-1])
    batch = pre.replace(block + "\n", "").rstrip("\n") + f"\n\n{block}\n"    # under Done recently, its text the same
    changed, carried, lost, head = gapsdoc.carry(pre, batch, records, HEAD)
    assert list(changed) == ["remote-systems"] and lost == []           # never a second record (remote-systems-2)
    assert gapsdoc.parse(changed["remote-systems"])["section"] == "Done recently"
    assert changed["remote-systems"].startswith("# remote-systems: the umbrella\n")
    assert [c.split(":")[0] for c in carried] == ["remote-systems", "GAPS-head.md"]
    text, problems = gapsdoc.render(changed, head)
    assert problems == [] and text == batch and text.count("- **Remote systems**") == 1


def test_regenerate_on_a_malformed_record_writes_nothing(tmp_path):
    pre = tree(tmp_path, {"remote-systems": UMBRELLA})
    (tmp_path / "dev" / "records" / "no-date.md").write_text(MALFORMED["no-date"])
    (tmp_path / "docs" / "GAPS.md").write_text(edited(pre))
    with pytest.raises(ValueError, match="no-date: malformed Entry"):
        gapsdoc.regenerate(tmp_path, pre)
    assert (tmp_path / "docs" / "GAPS.md").read_text() == edited(pre)                 # as the merge left it
    assert (tmp_path / "dev" / "records" / "remote-systems.md").read_text() == UMBRELLA
    assert not (tmp_path / "dev" / "records" / "GAPS-unplaced.md").exists()
