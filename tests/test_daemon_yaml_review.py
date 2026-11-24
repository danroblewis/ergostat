"""The daemon YAML review (docs/proposals/daemon-yaml.md) checked against the code it reviews: a section per question
of the GAPS entry, every ``today`` model accepted by ``check`` as it is now, every ``proposed`` one refused for its
change (syntax) or read otherwise today (semantics), the table's counts recounted, and the ceilings it states equal to
the code's."""

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ergostat import model as mdl
from ergostat.daemons import config
from tests.test_daemon_docs import ROOT, blocks
from tests.test_gaps_doc import gaps_text

DOC = ROOT / "docs" / "proposals" / "daemon-yaml.md"
QUESTIONS = ["A modifier instead of a kind", "Per-sensor arguments", "Where shared daemons are declared",
             "The names of inline daemons", "Push", "The knobs", "The word"]
ROWS = ["A modifier instead of a kind", "Per-sensor arguments",
        "Where shared daemons are declared: top-level daemons:", "Where shared daemons are declared: an agent's process",
        "The names of inline daemons", "Push", "The knobs: concurrency and pool", "The knobs: restart.backoff",
        "The knobs: stdin-timeout", "The knobs: heartbeat on by default", "The word: runner", "The word: server",
        "The word: keep-alive"]
COUNTED = ["docs/DAEMONS.md", "docs/skills/ergostat-author/daemons.md", "docs/SPEC.md"]
COUNTED_AT = "f7b93be"                          # the commit the table's counts were taken at (said above the table)
BRANCH = "factory/daemon-yaml-schema-review"    # while it is built, the counts are compared with the tree itself
PAIR = re.compile(r"<!-- (today|proposed): ([\w-]+)(?:, (syntax|semantics)(?:: (.+?))?)? -->")


def sections() -> dict[str, str]:
    parts = re.split(r"^## ", DOC.read_text(), flags=re.M)
    return {p.split("\n", 1)[0].strip(): p for p in parts[1:]}


def marked() -> list[dict]:
    """Each yaml block of the review with the today/proposed mark on the line before its fence, and its section."""
    lines, out = DOC.read_text().splitlines(), []
    for b in blocks(DOC):
        fence = int(b["at"].rsplit(":", 1)[1]) - 1
        m = PAIR.fullmatch(lines[fence - 1].strip()) if b["lang"] == "yaml" else None
        if m:
            sec = next(x[3:] for x in reversed(lines[:fence]) if x.startswith("## "))
            out.append({"role": m[1], "pair": m[2], "how": m[3], "says": m[4], "text": b["text"], "section": sec})
    return out


MARKED = marked()
TODAY = {b["pair"]: b for b in MARKED if b["role"] == "today"}
PROPOSED = {b["pair"]: b for b in MARKED if b["role"] == "proposed"}


def check(tmp: Path, text: str) -> subprocess.CompletedProcess:
    """The model written as ergostat.yaml, an executable stub for each relative path a run: names, and check run."""
    (tmp / "ergostat.yaml").write_text(text)
    runs: list[str] = []

    def walk(x):
        if isinstance(x, dict):
            runs.extend(str(v) for k, v in x.items() if k == "run" and isinstance(v, str))
            [walk(v) for v in x.values()]
        elif isinstance(x, list):
            [walk(v) for v in x]
    walk(yaml.safe_load(text))
    for tok in (t for r in runs for t in shlex.split(r) if "/" in t and not t.startswith("/")):
        p = tmp / tok
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)
    return subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp), "check"], capture_output=True,
                          text=True, timeout=60)


def test_the_review_has_a_section_for_each_question_in_the_gap():
    got = sections()
    assert [s for s in got if s in QUESTIONS] == QUESTIONS, list(got)
    for q in QUESTIONS:
        s = got[q]
        pairs = {b["pair"] for b in PROPOSED.values() if b["section"] == q}
        assert pairs and all(p in TODAY and TODAY[p]["section"] == q for p in pairs), (q, pairs)
        for word in ("**Today.**", "**What changes.**", "**Recommendation.**", "**Owner's decision:** open."):
            assert word in s, (q, word)
        assert s.index("**Today.**") < s.index("**What changes.**") < s.index("**Recommendation.**") \
            < s.index("**Owner's decision:**"), q
    said = re.findall(r"Owner's decision:\*\* *(\S+)", DOC.read_text())
    assert said and all(w.startswith("open") for w in said), said         # never written in as made


@pytest.mark.parametrize("pair", sorted(TODAY))
def test_every_today_model_passes_check_as_ergostat_accepts_it_now(tmp_path, pair):
    r = check(tmp_path, TODAY[pair]["text"])
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("pair", sorted(PROPOSED))
def test_every_proposed_model_is_refused_by_check_today(tmp_path, pair):
    p = PROPOSED[pair]
    assert pair in TODAY and p["how"] in ("syntax", "semantics"), p
    r = check(tmp_path, p["text"])
    if p["how"] == "syntax":                     # refused, for the change: its key named in what check says
        assert r.returncode != 0 and p["says"] and p["says"] in r.stdout + r.stderr, (p["says"], r.stdout + r.stderr)
    else:                                        # accepted today, but read as something else than today's twin
        assert r.returncode == 0, r.stdout + r.stderr
        (tmp_path / "t").mkdir()
        assert check(tmp_path / "t", TODAY[pair]["text"]).returncode == 0
        assert mdl.load(tmp_path).spec.daemons != mdl.load(tmp_path / "t").spec.daemons, pair


def test_there_is_a_pair_in_every_section():
    assert len(PROPOSED) >= len(QUESTIONS) and {b["section"] for b in PROPOSED.values()} == set(QUESTIONS)


def table() -> list[tuple[str, str, int]]:
    s = sections()["Places a change would rewrite"]
    rows = re.findall(r"^\| (.+?) \| `(.+?)` \| (\d+) \|$", s, flags=re.M)
    return [(n, rx.replace("\\|", "|"), int(c)) for n, rx, c in rows]


def places(at: str | None, tmp: Path | None = None) -> list[str]:
    """Every YAML place counted: the fenced yaml blocks of the three docs, and examples/**/*.yaml; from the tree
    (at None) or from a commit (its docs written to ``tmp`` to be read)."""
    if at is None:
        docs = [ROOT / d for d in COUNTED]
        files = sorted((ROOT / "examples").rglob("*.yaml"))
        return [b["text"] for d in docs for b in blocks(d) if b["lang"] == "yaml"] + [f.read_text() for f in files]

    def show(path):
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{at}:{path}"], capture_output=True, text=True,
                              check=True).stdout
    out = []
    for d in COUNTED:
        (tmp / "doc.md").write_text(show(d))
        out += [b["text"] for b in blocks(tmp / "doc.md") if b["lang"] == "yaml"]
    names = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", at, "examples/"],
                           capture_output=True, text=True, check=True).stdout.split()
    return out + [show(n) for n in sorted(names) if n.endswith(".yaml")]


def count(texts: list[str], rx: str) -> int:
    r = re.compile(rx)
    return sum(1 for t in texts if any(r.search(line) for line in t.splitlines()))


def test_the_places_to_rewrite_are_counted_from_the_tree_as_it_is(tmp_path):
    rows = table()
    assert [n for n, _, _ in rows] == ROWS, rows
    here = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    tree = places(None)
    counted = tree if here in (BRANCH, "") else places(COUNTED_AT, tmp_path)   # (no git: the tree, the strict case)
    got = {n: count(counted, rx) for n, rx, _ in rows}
    wrong = [f"{n}: says {c}, counted {got[n]}" for n, _, c in rows if c != got[n]]
    assert not wrong, "\n".join(wrong)
    assert all(count(tree, rx) >= 1 for _, rx, _ in rows), [n for n, rx, _ in rows if not count(tree, rx)]


def test_the_knobs_section_states_the_ceilings_the_code_has(tmp_path):
    s = sections()["The knobs"]
    most = re.search(r"`WARM_MOST` \**(\d+)", s)
    every = re.search(r"`WARM_ALL` \**(\d+)", s)
    assert most and every and (int(most[1]), int(every[1])) == (config.WARM_MOST, config.WARM_ALL)
    assert "no maximum" in s and "engine threads" in s
    text = TODAY["knobs-pool"]["text"]
    assert "concurrency: 20" in text and "warm" not in text
    r = check(tmp_path, text.replace("concurrency: 20", "concurrency: 100000"))
    assert r.returncode == 0, r.stdout + r.stderr                         # a non-warm one: no maximum today
    assert mdl.load(tmp_path).spec.daemons["block.builder"].concurrency == 100000


def test_the_with_section_says_the_read_line_gains_a_field():
    s = sections()["Per-sensor arguments"]
    assert '{"op": "read"' in s and "adds a field" in s and "The protocol changes." in s
    assert "need not change" not in s


def test_the_gaps_entry_points_at_the_review_and_stays_open():
    text = gaps_text()                              # (the entry as dev/records/ render it, not docs/GAPS.md)
    m = re.search(r"^- \*\*Daemon YAML schema review\*\*.*?(?=^- \*\*|^#|\Z)", text, flags=re.M | re.S)
    assert m, "no GAPS entry"
    entry = m[0]
    assert "(open;" in entry and "docs/proposals/daemon-yaml.md" in entry and DOC.exists()
