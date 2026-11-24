"""gapsdoc: a GAPS.md entry as a form in its gap's record, and docs/GAPS.md rendered from the records.

A record (dev/records/<branch>.md) may hold one `## Entry` section, shaped as dev/prompts/definition.md shows:
`section:`, `done: YYYY-MM-DD sentence` lines, then the bullet (its later lines indented, no blank line); or, for a
sub-gap, `entry-of: <umbrella's record>` and its done lines only. Every done line of an umbrella and its sub-gaps is
rendered under the umbrella's bullet in date order (then by name): two sub-gaps are two files, merged with no conflict.
dev/records/GAPS-head.md is the rest of GAPS.md, each entry a line `@entry NAME`; an entry it does not list goes after
its section's last, by name. render() reports by name every malformed Entry, two titles slugging to one branch
(gap ids cut to 32, as intake does), a listed entry or an umbrella with none: rendered, never silently dropped.
split() is the inverse; an exact duplicate entry is dropped and said by name and line. No branch edits GAPS.md (the
build refuses one, the queue gives one back): each landing of the merge queue writes it from the records
(regenerate()); the intake, deps.py, the briefs, the planner and the knowledge block read the entries from main's
records (entries(); brief.records_at_main), not the file.

    gapsdoc.py render [--check]       GAPS.md from dev/records to stdout (--check: only the problems); exits 1 on any
    gapsdoc.py split --dry-run [FILE] what split would make of FILE (docs/GAPS.md): records, duplicates, problems
    gapsdoc.py split                  docs/GAPS.md split into dev/records (once: it never overwrites; write())"""

from __future__ import annotations

import datetime
import itertools
import re
import subprocess
import sys
import textwrap
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "dev" / "records"
HEAD = RECORDS / "GAPS-head.md"
UNPLACED = RECORDS / "GAPS-unplaced.md"                # text the retired carry step could not place: never a record
ENTRY = re.compile(r"^- \*\*(.+?)\*\*(.*)$")          # intake.ENTRY: a top-level GAPS.md entry
SLOT = re.compile(r"^@entry ([a-z0-9][a-z0-9-]{0,63})$")
DONE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\S.*)$")
# render() problems that lose no text (both entries drawn, or drawn elsewhere): the only ones a landing writes past
BENIGN = re.compile(r"(slug to one branch, [a-z0-9-]+|lists it twice; rendered once|; rendered where listed"
                    r"|is not in GAPS-head\.md; added at the end)$")
KEYS = ("section", "entry-of")


def gap_id(title: str) -> str:
    """The gap id intake gives an entry of this title (after `gap/`); its branch is this cut to 32 (intake.py:226)."""
    return fac.slug(title.rstrip(":").strip(), 60)


def parse(record: str) -> dict | None:
    """A record's `## Entry` section: {section, entry_of, done: [(date, sentence)], bullet: [lines]}, or None when
    it has none. Anything else in the section, or a form it breaks, raises ValueError saying what."""
    lines = record.split("\n")
    at = [n for n, ln in enumerate(lines) if ln.rstrip() == "## Entry"]
    if not at:
        return None
    if len(at) > 1:
        raise ValueError(f"{len(at)} '## Entry' sections")
    body = list(itertools.takewhile(lambda ln: not ln.startswith("## "), lines[at[0] + 1:]))
    while body and not body[-1].strip():
        body.pop()
    e: dict = {"section": None, "entry_of": None, "done": [], "bullet": []}
    for n, ln in enumerate(body):
        if e["bullet"] or ENTRY.match(ln):
            if e["bullet"] and (not ln.startswith("  ") or not ln.strip()):
                raise ValueError(f"bullet line {len(e['bullet']) + 1} is blank or not indented two spaces: {ln!r}")
            e["bullet"].append(ln)
        elif not ln.strip():
            continue
        elif ln.startswith("done:"):
            m = DONE.match(ln[5:].strip())
            try:
                datetime.date.fromisoformat(m.group(1) if m else "")
            except ValueError:
                raise ValueError(f"done line is not 'done: YYYY-MM-DD sentence' with a real date: {ln!r}") from None
            e["done"].append((m.group(1), m.group(2).strip()))
        elif (key := ln.split(":", 1)[0]) in KEYS and ":" in ln:
            if e[field := key.replace("-", "_")] is not None or not ln.split(":", 1)[1].strip():
                raise ValueError(f"'{key}:' given twice, or empty")
            e[field] = ln.split(":", 1)[1].strip()
        else:
            raise ValueError(f"line {n + 1} of the Entry is not section:, entry-of:, done: or the bullet: {ln!r}")
    if e["entry_of"] is not None:
        if e["bullet"] or not e["done"] or not fac.SAFE.match(e["entry_of"]):
            raise ValueError("a sub-gap is 'entry-of: BRANCH' and its done lines, with no bullet of its own")
    elif not e["section"] or not e["bullet"]:
        raise ValueError("an entry needs 'section:' and a bullet ('- **Title** ...')")
    return e


def done_lines(done: list[tuple[str, str, str]]) -> list[str]:
    """Done lines (date, record name, sentence) in date order, then name, as indented sub-bullets."""
    out = []
    for date, name, sentence in sorted(done, key=lambda d: (d[0], d[1])):
        out += textwrap.wrap(f"*Done {date}* (`{name}`): {sentence}", width=118, initial_indent="  - ",
                             subsequent_indent="    ", break_long_words=False, break_on_hyphens=False)
    return out


def render(records: dict[str, str], head: str, drawn: dict | None = None) -> tuple[str, list[str]]:
    """GAPS.md's text from {record name: record text} and the head, and the problems found, each naming its record.
    Every entry that parses is rendered, a problem or not; ``drawn`` (when given) gets {its text: record name}."""
    problems: list[str] = []
    tops: dict[str, dict] = {}
    subs: dict[str, list[tuple[str, dict]]] = {}
    for name in sorted(records):
        try:
            e = parse(records[name])
        except ValueError as err:
            problems.append(f"{name}: malformed Entry: {err}")
            continue
        if e and e["entry_of"]:
            subs.setdefault(e["entry_of"], []).append((name, e))
        elif e:
            tops[name] = e
    slugs: dict[str, list[str]] = {}
    for name, e in tops.items():
        slugs.setdefault(fac.slug(gap_id(ENTRY.match(e["bullet"][0]).group(1)), 32), []).append(name)
    problems += [f"{', '.join(ns)}: their entries' titles slug to one branch, {s}" for s, ns in slugs.items() if ns[1:]]
    for umbrella, kids in subs.items():
        for name, e in kids:
            if umbrella not in tops:
                problems.append(f"{name}: entry-of: {umbrella}, which has no top entry; its done lines are not drawn")
            elif e["section"] and e["section"] != tops[umbrella]["section"]:
                problems.append(f"{name}: section: {e['section']} is not its umbrella {umbrella}'s")

    def text(name: str) -> list[str]:
        e = tops[name]
        done = [(d, name, s) for d, s in e["done"]]
        done += [(d, kid, s) for kid, k in subs.get(name, []) for d, s in k["done"]]
        (drawn if drawn is not None else {})["\n".join(got := e["bullet"] + done_lines(done))] = name
        return got

    lines = head.split("\n")
    section, last = "", {}                         # last: the index after which a section's unlisted entries go
    for n, ln in enumerate(lines):
        section = ln[3:].strip() if ln.startswith("## ") else section
        if ln.startswith("## ") or SLOT.match(ln):
            last[section] = n
    listed = {m.group(1) for ln in lines if (m := SLOT.match(ln))}
    unlisted: dict[str, list[str]] = {}
    for name in tops.keys() - listed:
        unlisted.setdefault(tops[name]["section"], []).append(name)
    out, section, placed = [], "", set()
    for n, ln in enumerate(lines):
        section = ln[3:].strip() if ln.startswith("## ") else section
        m = SLOT.match(ln)
        if m and m.group(1) not in tops:
            problems.append(f"{m.group(1)}: GAPS-head.md lists it, but it has no top entry")
        elif m and m.group(1) in placed:
            problems.append(f"{m.group(1)}: GAPS-head.md lists it twice; rendered once")
        elif m:
            if tops[m.group(1)]["section"] != section:
                problems.append(f"{m.group(1)}: its entry says section {tops[m.group(1)]['section']!r}, but "
                                f"GAPS-head.md lists it under {section!r}; rendered where listed")
            out += text(m.group(1))
            placed.add(m.group(1))
        else:
            out.append(ln)
        if section and last.get(section) == n:     # after the section's last listed entry, or its heading and a gap
            names = sorted(unlisted.pop(section, []))
            out += ([""] if names and ln.startswith("## ") else []) + [x for name in names for x in text(name)]
    tail = [out.pop()] if out and out[-1] == "" else []
    for sec in sorted(unlisted):
        problems.append(f"{', '.join(sorted(unlisted[sec]))}: section {sec!r} is not in GAPS-head.md; added at the end")
        out += ["", f"## {sec}", ""] + [ln for name in sorted(unlisted[sec]) for ln in text(name)]
    return "\n".join(out + tail), problems


def split(gaps_md: str) -> dict:
    """GAPS.md's text as {head, records: {name: '## Entry' section}, dropped, problems}; render(records, head) gives
    the text back with the dropped exact duplicates left out. dropped and problems each name the entry and line."""
    lines = gaps_md.split("\n")
    head, records, seen, dropped, problems = [], {}, {}, [], []
    section, n = "", 0
    while n < len(lines):
        if not (m := ENTRY.match(lines[n]) if section else None):
            section = lines[n][3:].strip() if lines[n].startswith("## ") else section
            head.append(lines[n])
            n += 1
            continue
        end = n + 1
        while end < len(lines) and lines[end].startswith("  ") and lines[end].strip():
            end += 1
        block, title = lines[n:end], m.group(1).rstrip(":").strip()
        key = "\n".join(block)
        if key in seen:
            dropped.append(f"{title}: line {n + 1} repeats line {seen[key]} exactly; dropped")
        else:
            seen[key] = n + 1
            name = base = fac.slug(gap_id(title), 32) or "entry"           # its branch, as intake names it
            k = 1
            while name in records:
                k += 1
                name = f"{base}-{k}"
            if name != base:
                problems.append(f"{title}: line {n + 1} slugs to {base} as an earlier entry does; kept as {name}")
            records[name] = "\n".join(["## Entry", "", f"section: {section}", "", *block, ""])
            head.append(f"@entry {name}")
        n = end
    return {"head": "\n".join(head), "records": records, "dropped": dropped, "problems": problems}


def write(s: dict, where: Path) -> list[Path]:
    """split()'s head and records written under ``where`` (dev/records): each entry appended as `## Entry` at the end
    of its record, never overwriting. A record holding an Entry already, or a head already there, raises ValueError
    before anything is written."""
    files = {where / HEAD.name: ("", s["head"])}
    for name, rec in s["records"].items():
        p = where / f"{name}.md"
        files[p] = (p.read_text() if p.is_file() else "", rec)
    if bad := [p.name for p, (was, _) in files.items() if p.exists() and (p.name == HEAD.name or parse(was))]:
        raise ValueError(f"already there, never overwritten: {', '.join(bad)}")
    for p, (was, rec) in files.items():
        p.write_text(was.rstrip("\n") + "\n\n" + rec if was.strip() else rec)
    return list(files)


def entries(repo: Path, ref: str) -> tuple[str, dict[str, str]] | None:
    """GAPS.md's text as the records in dev/records/ at ``ref`` render it, read with one git call, and {record: why}
    for each that cannot be read (git cannot show it or it is not UTF-8: not read; its Entry is malformed: render()
    draws none of it), never read as having no entry. None before the split (no GAPS-head.md at ``ref``); an
    unreadable GAPS-head.md raises ValueError (the head names gaps too: its Depends on table)."""
    names = [n for n in fac.git(repo, "ls-tree", "-z", "--name-only", ref, f"{fac.DEFS}/").split("\0")
             if n.endswith(".md") and Path(n).stem != UNPLACED.stem]
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True, timeout=600,
                       input="".join(f"{ref}:{n}\n" for n in names).encode())
    if r.returncode:
        raise RuntimeError(f"git cat-file --batch in {repo}: {r.stderr.decode(errors='replace').strip()[-400:]}")
    files, bad, out = {}, {}, r.stdout
    for n in names:
        header, _, out = out.partition(b"\n")
        f, stem = header.split(), Path(n).stem
        if len(f) != 3 or f[1] != b"blob":                 # (missing, or not a file: a submodule's commit)
            bad[stem] = f"unreadable at {ref}: {header.decode(errors='replace')[-120:]}"
            continue
        data, out = out[:int(f[2])], out[int(f[2]) + 1:]
        try:
            parse(files.setdefault(stem, data.decode()))
        except UnicodeDecodeError as e:                   # (a subclass of ValueError: first)
            bad[stem] = f"unreadable at {ref}: {e}"[:200]
        except ValueError as e:
            bad[stem] = str(e).splitlines()[-1][:200]       # (parse()'s own words, as main's briefs say them)
    if HEAD.stem in bad:
        raise ValueError(f"{fac.DEFS}/{HEAD.name} at {ref} cannot be read: {bad[HEAD.stem]}")
    return (render(files, files.pop(HEAD.stem))[0], bad) if HEAD.stem in files else None


def regenerate(root: Path) -> dict:
    """Inside a landing (queue.py): docs/GAPS.md under ``root`` rendered from its records (no branch edits it: the queue
    gives back one whose diff touches it); written only when render() loses nothing (no problem but a BENIGN one), else
    ValueError and nothing written. {files: written, relative to root, problems}."""
    where, gaps = root / fac.DEFS, root / "docs" / "GAPS.md"
    records = {p.stem: p.read_text() for p in sorted(where.glob("*.md")) if p.name not in (HEAD.name, UNPLACED.name)}
    text, problems = render(records, (where / HEAD.name).read_text())
    if bad := [p for p in problems if not BENIGN.search(p)]:
        raise ValueError("; ".join(bad))
    gaps.write_text(text)
    return {"files": [str(gaps.relative_to(root))], "problems": problems}


def main(argv: list[str]) -> int:
    if argv[:1] == ["render"] and set(argv[1:]) <= {"--check"}:
        records = {p.stem: p.read_text() for p in sorted(RECORDS.glob("*.md")) if p not in (HEAD, UNPLACED)}
        if not HEAD.is_file():
            print(f"gapsdoc: {HEAD.relative_to(ROOT)} is missing: nothing to render into", file=sys.stderr)
            return 1
        text, problems = render(records, HEAD.read_text())
        if "--check" not in argv:
            sys.stdout.write(text)
        for p in problems:
            print(f"gapsdoc: {p}", file=sys.stderr)
        return 1 if problems else 0
    if argv[:2] == ["split", "--dry-run"] and len(argv) <= 3:
        path = Path(argv[2]) if len(argv) == 3 else ROOT / "docs" / "GAPS.md"
        s = split(path.read_text())
        print("\n".join([f"record {name}: {rec.split(chr(10))[2]}" for name, rec in s["records"].items()]
                        + [f"duplicate {d}" for d in s["dropped"]] + [f"problem {p}" for p in s["problems"]]))
        print(f"{len(s['records'])} entries, {len(s['dropped'])} duplicates dropped, {len(s['problems'])} problems")
        return 0
    if argv == ["split"]:
        s = split((ROOT / "docs" / "GAPS.md").read_text())
        try:
            print("\n".join(str(p.relative_to(ROOT)) for p in write(s, RECORDS)))
        except ValueError as e:
            print(f"gapsdoc: {e}", file=sys.stderr)
            return 1
        print("\n".join([f"duplicate {d}" for d in s["dropped"]] + [f"problem {p}" for p in s["problems"]]))
        return 0
    print("usage: gapsdoc.py render [--check] | split [--dry-run [FILE]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
