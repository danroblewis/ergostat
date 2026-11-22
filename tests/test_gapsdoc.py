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
    assert run("split", str(tmp_path / "GAPS.md")).returncode == 2       # writing records is not built


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
