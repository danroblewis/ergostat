"""gapsdoc: a GAPS.md entry as a form in its gap's record, and docs/GAPS.md rendered from the records.

A record (dev/records/<branch>.md) may hold one `## Entry` section, shaped as dev/prompts/definition.md shows:
`section:`, `done: YYYY-MM-DD sentence` lines, then the bullet (its later lines indented, no blank line); or, for a
sub-gap, `entry-of: <umbrella's record>` and its done lines only. Every done line of an umbrella and its sub-gaps is
rendered under the umbrella's bullet in date order (then by name): two sub-gaps are two files, merged with no conflict.
dev/records/GAPS-head.md is the rest of GAPS.md, each entry a line `@entry NAME`; an entry it does not list goes after
its section's last, by name. render() reports by name every malformed Entry, two titles slugging to one branch
(gap ids cut to 32, as intake does), a listed entry or an umbrella with none: rendered, never silently dropped.
split() is the inverse; an exact duplicate entry (a union merge's) is dropped and said by name and line. Each landing
of the merge queue carries the batch's own GAPS.md edits into the records and GAPS-head.md (carry()) and writes GAPS.md from them
(regenerate()); the intake reads the records' render at main (entries()), not the file.

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
UNPLACED = RECORDS / "GAPS-unplaced.md"                # GAPS.md text a landing could not put in any record (carry())
ENTRY = re.compile(r"^- \*\*(.+?)\*\*(.*)$")          # intake.ENTRY: a top-level GAPS.md entry
SLOT = re.compile(r"^@entry ([a-z0-9][a-z0-9-]{0,63})$")
DONE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\S.*)$")
DONE_AT = re.compile(r"^  - \*Done (\d{4}-\d{2}-\d{2})\* \(`([a-z0-9][a-z0-9-]*)`\): (.*)$")   # done_lines()' first line
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


def with_entry(record: str, e: dict | None) -> str:
    """The record with its `## Entry` section (wherever it was) made ``e``'s, at its end; ``e`` None: removed ("" when
    nothing else is left)."""
    lines = record.split("\n")
    if at := [n for n, ln in enumerate(lines) if ln.rstrip() == "## Entry"][:1]:
        lines = lines[:at[0]] + list(itertools.dropwhile(lambda ln: not ln.startswith("## "), lines[at[0] + 1:]))
    if e is None:
        return "\n".join(lines).rstrip("\n") + "\n" if "".join(lines).strip() else ""
    keys = [f"{k}: {e[k.replace('-', '_')]}" for k in KEYS if e[k.replace("-", "_")]]
    body = ["## Entry", "", *keys, *[f"done: {d} {s}" for d, s in e["done"]], *[""] * bool(e["bullet"]), *e["bullet"]]
    return ("\n".join(lines).rstrip("\n") + "\n\n" if "".join(lines).strip() else "") + "\n".join(body) + "\n"


def carry(pre: str, head: str, records: dict[str, str], gaps_head: str,
          before: str | None = None) -> tuple[dict, list[str], list[str], str]:
    """The entry text and done lines a batch added to GAPS.md (``head``) that neither the records before it rendered
    (``pre``) nor the records (at head) render, put in them: ({record: its new text}, what was carried, by record, the
    entries it could not place, whole, and GAPS-head.md). An entry goes to the record of its title whose drawn block the
    batch changed (two such: placed nowhere, as which it replaces is not known), else, when every record of its title
    still has its block, to a new `<branch>-N`, else to the record its branch names (the gap id cut to 32; made when
    there is none), its section and bullet replacing that Entry's; each done line (as done_lines() draws it) is added
    to the record it names in backticks. An entry with any part that cannot be placed (another title's Entry, a
    sub-gap's under another umbrella) is placed in no part. A block whose text a record draws, moved to another section,
    goes back to that record with the new section. A record whose block GAPS.md showed before the batch (``before``,
    the file main held at pre; None: ``pre``) and the batch removed (never a record-only Entry added or retitled, nor
    one an earlier failed render kept out of GAPS.md), when no block of its
    title was left unplaced or stale (not carried), has its Entry removed, and its sub-gaps' too, said by name (a record
    left empty is deleted by regenerate()). When the batch changed GAPS.md outside the entries (its
    head, as split() cuts it), GAPS-head.md becomes that head, each `@entry` naming the record that draws (or now
    holds) the entry there; an entry no record holds loses its slot."""
    drawn: dict[str, str] = {}
    have = set(split(pre)["records"].values()) | set(split(render(records, gaps_head, drawn)[0])["records"].values())
    tops, out, said, lost, at = {}, {}, [], [], {}     # at: {split()'s name for a block of head: the record holding it}
    title, kids, keep = {}, {}, set()                  # keep: titles of blocks not placed (stale or lost): never removed
    for name, text in records.items():
        try:
            e = parse(text)
        except ValueError:
            continue
        if e and not e["entry_of"]:
            tops.setdefault(title.setdefault(name, gap_id(ENTRY.match(e["bullet"][0]).group(1))), []).append(name)
        elif e:
            kids.setdefault(e["entry_of"], []).append(name)
    cut = split(head)
    shown = {"\n".join(r.split("\n")[4:-1]) for r in cut["records"].values()}
    gone = {n for t, n in drawn.items() if t not in shown}   # records whose drawn block the batch changed or removed
    drew = {"\n".join(r.split("\n")[4:-1]) for r in split(pre if before is None else before)["records"].values()}
    was = {n for t, n in drawn.items() if t in drew}         # records whose block GAPS.md showed before the batch
    for slot, rec in cut["records"].items():
        lines = rec.split("\n")
        section, block, bullet, done = lines[2].removeprefix("section: "), lines[4:-1], [], []
        gid = gap_id(ENTRY.match(block[0]).group(1))
        same = tops.get(gid, [])                       # (two records may hold entries of one title: never one of them)
        if rec in have:
            at[slot] = drawn.get("\n".join(block)) or (same[0] if len(same) == 1 else None)
            keep |= {gid} - {title.get(drawn.get("\n".join(block)))}   # (drawn by a record: that one's, no other's)
            continue
        owner = drawn.get("\n".join(block))           # its text unchanged, its section moved: the record that draws it
        if len(ns := [owner] if owner else [n for n in same if n in gone]) > 1:   # which it replaces is not known
            lost.append("\n".join(block))
            keep.add(gid)
            continue
        for ln in block:
            if m := DONE_AT.match(ln):
                done.append(list(m.groups()))
            elif done and ln.startswith("    "):
                done[-1][2] += " " + ln.strip()
            else:
                bullet.append(ln)
        base, taken, trial = fac.slug(gid, 32), set(records) | set(out), dict(out)
        name = ns[0] if ns else base if base not in taken or not same else next(    # another of a title: its own record
            n for k in itertools.count(2) if (n := f"{base}-{k}") not in taken)
        try:
            for who, d, s in [(name, None, None)] + [(w, d, s) for d, w, s in done]:
                if not fac.SAFE.match(who):
                    raise ValueError(f"{who!r} is not a record name")
                e = parse(trial.get(who, records.get(who, "")))       # (no record yet: one is made, its Entry alone)
                if (e or {}).get("entry_of") not in (None, name) or e and d and who != name and not e["entry_of"]:
                    raise ValueError(f"{who}'s Entry is not {name}'s nor under it")
                if e and d is None and not e["entry_of"] and gap_id(ENTRY.match(e["bullet"][0]).group(1)) != gid:
                    raise ValueError(f"{who}'s Entry has another title")
                if d is None:
                    e = {"section": section, "entry_of": None, "done": (e or {}).get("done", []), "bullet": bullet}
                elif not e:                                   # (a sub-gap's record with no Entry yet: one, under it)
                    e = {"section": None, "entry_of": name, "done": [(d, s)], "bullet": []}
                elif (d, s) not in e["done"]:
                    e["done"].append((d, s))
                trial[who] = with_entry(trial.get(who, records.get(who, "")), e)
        except ValueError:
            lost.append("\n".join(block))
            keep.add(gid)
            continue
        out, at[slot] = trial, name
        gone.discard(name)
        said += [f"{name}: {block[0][:80]}"]
    # the batch removed the entry: its Entry goes too. Only a block GAPS.md showed before it: a record's Entry never in
    # GAPS.md (added or retitled in the record, or kept out by a failed render) is not one it removed.
    for name in sorted(n for n in gone & was if title[n] not in keep):
        for who in [name, *kids.get(name, [])]:                    # (with its sub-gaps' done lines, drawn under it)
            out[who] = with_entry(out.get(who, records[who]), None)
        said += [f"{name}: its Entry removed, as the batch removed it from GAPS.md"]
    new_head = gaps_head
    if cut["head"] != split(pre)["head"]:            # the batch's edits outside the entries: kept, in GAPS-head.md
        lines, listed = [], set()
        for ln in cut["head"].split("\n"):
            if not (m := SLOT.match(ln)):
                lines.append(ln)
            elif (n := at.get(m.group(1))) and n not in listed:
                lines.append(f"@entry {n}")
                listed.add(n)
        new_head = "\n".join(lines)
        said += ["GAPS-head.md: the batch's GAPS.md text outside the entries"] * (new_head != gaps_head)
    return {n: t for n, t in out.items() if t != records.get(n)}, said, lost, new_head


def rendered_at(repo: Path, ref: str) -> str:
    """GAPS.md as the records at commit ``ref`` render it; "" before the split (no GAPS-head.md there), so a landing
    then carries every entry the records do not render (main's GAPS.md edits since the split commit included)."""
    names = fac.git(repo, "ls-tree", "--name-only", ref, f"{fac.DEFS}/").splitlines()
    files = {Path(n).stem: fac.git(repo, "show", f"{ref}:{n}") for n in names if n.endswith(".md")}
    files.pop(UNPLACED.stem, None)
    return render(files, files.pop(HEAD.stem))[0] if HEAD.stem in files else ""


def entries(repo: Path, ref: str) -> tuple[str, list[str]] | None:
    """GAPS.md as the records at commit ``ref`` render it, read with one git call, and the problems, each naming its
    record: one git cannot show or decode, or whose Entry is malformed, is drawn nowhere and said, never read as having
    no entry. None before the split (no GAPS-head.md at ``ref``); an unreadable GAPS-head.md raises ValueError."""
    names = [n for n in fac.git(repo, "ls-tree", "-z", "--name-only", ref, f"{fac.DEFS}/").split("\0")
             if n.endswith(".md")]
    r = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True, timeout=600,
                       input="".join(f"{ref}:{n}\n" for n in names).encode())
    if r.returncode:
        raise RuntimeError(f"git cat-file --batch in {repo}: {r.stderr.decode(errors='replace').strip()[-400:]}")
    files, problems, out = {}, [], r.stdout
    for n in names:
        header, _, out = out.partition(b"\n")
        f = header.split()
        if len(f) != 3 or f[1] != b"blob":                 # (missing, or not a file: a submodule's commit)
            problems.append(f"{Path(n).stem}: unreadable at {ref}: {header.decode(errors='replace')[-120:]}")
            continue
        data, out = out[:int(f[2])], out[int(f[2]) + 1:]
        try:
            files[Path(n).stem] = data.decode()
        except UnicodeDecodeError as e:
            problems.append(f"{Path(n).stem}: unreadable at {ref}: {e}")
    if HEAD.stem not in files:
        if any(p.startswith(f"{HEAD.stem}:") for p in problems):
            raise ValueError("; ".join(problems))
        return None
    head = files.pop(HEAD.stem)
    files.pop(UNPLACED.stem, None)
    text, said = render(files, head)
    return text, problems + said


def regenerate(root: Path, pre: str, before: str | None = None) -> dict:
    """Inside a landing (queue.py): the batch's own GAPS.md edits (from ``pre``: GAPS.md as the records rendered it
    before the batch, rendered_at(); ``before``: the GAPS.md main held then, what a removal is judged against) carried
    into the records under ``root`` (carry()), then docs/GAPS.md rendered
    from them; written only when render() loses nothing
    (no problem but a BENIGN one), else ValueError and nothing written. {files: written, relative to root, carried,
    unplaced: kept in GAPS-unplaced.md, problems}."""
    where, gaps = root / fac.DEFS, root / "docs" / "GAPS.md"
    head = (where / HEAD.name).read_text()
    records = {p.stem: p.read_text() for p in sorted(where.glob("*.md")) if p.name not in (HEAD.name, UNPLACED.name)}
    changed, carried, unplaced, new_head = carry(pre, gaps.read_text(), records, head, before)
    text, problems = render({**records, **changed}, new_head)
    if bad := [p for p in problems if not BENIGN.search(p)]:
        raise ValueError("; ".join(bad))
    files = {where / f"{n}.md": t for n, t in changed.items()} | {gaps: text}
    if new_head != head:
        files[where / HEAD.name] = new_head
    if unplaced:
        p = where / UNPLACED.name
        files[p] = (p.read_text() if p.is_file() else "# GAPS.md text no record took (gapsdoc.carry)\n") + "".join(
            f"\n{b}\n" for b in unplaced)
    for p, t in files.items():                         # (a record left empty by a removed Entry: deleted)
        p.write_text(t) if t or p == gaps else p.unlink()
    return {"files": [str(p.relative_to(root)) for p in files], "carried": carried, "unplaced": unplaced,
            "problems": problems}


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
