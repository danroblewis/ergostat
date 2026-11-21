"""The factory's knowledge in its briefs (dev/knowledge/README.md), put together by priority within a size budget
([knowledge] in dev/factory.toml): the house rules and the review lessons always (the files' and the
record's applied lesson items, lesson.py); then, as they fit, the owner's
decisions (ergostat.decision items, confirmed or proposed) whose scope the gap's text names, related gaps, past review
findings on the files it touches, and the module map of main. Each brief records the ids it carried and dropped, so
the model can relate what a brief carried to how its gap did.

    knowledge.py count | map     how many entries | the module map (cached by main's sha in run/modules/)
    knowledge.py sync            the collector: each entry an item knowledge/<id> (knowledge.found, .changed, .retired),
                                 and each decision of decisions.md not yet an item proposed (ergostat.decision.proposed)"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

KINDS = ("component", "rule", "lesson", "finding", "question", "source")   # the allowlist of a file's `kind:`
DECISION = "ergostat.decision"       # the one other kind, and only decisions.md's: read as the owner's decisions
STOP = set("a an the and or but of to in on for with at by from is are be it this that we i you our my as so "
           "not no do does don't dont never always should must".split())      # ergostat.decisions.kinds.STOP
ABOUT = re.compile(r"^\*About:\*\s*(.+)$", re.M)      # the parts of the root model an entry bears on: goal.x, stock.y
FILES = re.compile(r"\b((?:ergostat|dev|scripts|tests|docs|examples)/[\w./-]+\.(?:py|md|yaml|toml|sh))\b")
MORE = {"implementor": ("decisions", "related", "findings", "modules"),   # beyond the rules and the lessons, in order
        "reviewer": ("decisions", "findings", "related", "modules"), "planner": ("decisions", "related", "findings",
        "modules"), "researcher": ("decisions", "modules"), "pipeline_manager": ("decisions",)}
HEADS = {"decisions": "The owner's decisions this gap touches", "related": "Related gaps", "findings": "Past review "
         "findings on the files this gap touches", "modules": "The module map (main; the packages it touches in full)"}


class Refused(ValueError):
    """A knowledge file that cannot be read as it must be, or decisions that cannot all be read: the collector
    records nothing and a brief is not built (lesson-3: never read as "no entries" or "no decisions")."""


def read(path: Path) -> tuple[str, str]:
    """(its declared kind, the text after its front matter). Its kind must be one of KINDS, or, for decisions.md and
    only there, ergostat.decision; anything else, or no front matter, is refused."""
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    kind = re.search(r"^kind:[ \t]*(\S+)[ \t]*$", m[1], re.M) if m else None
    allowed = (DECISION,) if path.name == "decisions.md" else KINDS
    if not kind or kind[1] not in allowed:
        raise Refused(f"{path.name}: kind {kind[1] if kind else '(none: no front matter kind:)'}, not one of "
                      f"{', '.join(allowed)}")
    return kind[1], text[m.end():]


def sections(path: Path) -> list[tuple[str, str, str, list[str]]]:
    """The file's kind, and its entries: each `## ` heading with its body, and its closing *Areas:* list."""
    kind, body = read(path)
    out = []
    for m in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", body, re.M | re.S):
        areas = re.search(r"\*Areas:\s+(.+?)\.\*", m[2], re.S)
        out.append((kind, m[1].strip(), m[0].strip(), [a.strip() for a in " ".join(areas[1].split()).split(",")]
                    if areas else []))
    return out


def entries() -> list[dict]:
    """Every entry of dev/knowledge/ but decisions.md: {id (rules-process, lesson-3, <kind>-<slug of its heading>),
    title, kind (the file's), file, text, areas, about (its *About:* line: the parts of the root model it bears on,
    goal.x)}. Refused: a file whose kind is missing or not allowed, a lesson not
    headed `## N. Title`, two entries with one id."""
    out, ids = [], set()
    for p in sorted(p for p in (fac.HERE / "knowledge").glob("*.md") if p.name not in ("README.md", "decisions.md")):
        for kind, head, text, areas in sections(p):
            n = re.fullmatch(r"(\d+)\. (.+)", head) if kind == "lesson" else None
            if kind == "lesson" and not n:
                raise Refused(f"{p.name}: a lesson is headed ## N. Title, not {head!r}")
            first = re.match(r"\w*", head)[0].lower()                  # the house rules keep their ids
            eid = f"lesson-{n[1]}" if n else f"rules-{first}" if kind == "rule" else f"{kind}-{fac.slug(head, 32)}"
            if eid in ids or eid.endswith("-"):
                raise Refused(f"{p.name}: {head!r} gives the id {eid!r}, empty or already another entry's")
            ids.add(eid)
            about = ABOUT.search(text)
            out.append({"id": eid, "text": text, "title": n[2] if n else head, "kind": kind,
                        "file": f"dev/knowledge/{p.name}", "areas": areas,
                        "about": [x for x in re.split(r"[,\s]+", about[1].strip().rstrip(".")) if x] if about else []})
    return out


def applied(es: list[dict], lessons: list[dict]) -> list[dict]:
    """The entries with the record's lesson items (lesson.py): each applied new lesson its own entry (lesson-N, numbered
    when applied), each applied "seen as" a line under its lesson, and a lesson retired by lesson.py retire (with its
    lines) left out. An entry's `items` are the lesson items it carries."""
    gone = {i["fields"].get("lesson") for i in lessons if i["state"] == "retired" and i["id"].startswith(
        "lesson/retire-")}
    got = sorted((i for i in lessons if i["state"] == "applied"), key=lambda i: int(i["fields"].get("number") or 0))
    seed = {e["id"] for e in es}
    for n, i in enumerate(got):         # a number the seed took too (a gap of before the queue): kept apart, and said
        if i["fields"].get("kind") == "entry" and i["fields"].get("lesson") in seed:
            print(f"{i['id']}: {i['fields']['lesson']} is the seed's too; carried as {i['fields']['lesson']}-record",
                  file=sys.stderr)
            got[n] = {**i, "fields": {**i["fields"], "lesson": f"{i['fields']['lesson']}-record"}}
    out = [*(dict(e) for e in es), *({"id": i["fields"]["lesson"], "title": str(i["fields"]["entry"]).split("\n")[0],
                                      "kind": "lesson", "file": f"record: {i['id']}", "areas": [], "about": [],
                                      "text": f"## {i['fields']['lesson'][7:]}. {i['fields']['entry']}", "items": [i["id"]]}
                                     for i in got if i["fields"].get("kind") == "entry")]
    by = {e["id"]: e for e in out}
    for i in got:
        if i["fields"].get("kind") == "seen" and i["fields"].get("lesson") in by:
            e = by[i["fields"]["lesson"]]
            head, sep, check = e["text"].partition("\n**Check:**")
            e["text"], e["items"] = f"{head}\nSeen as: {i['fields']['entry']}.{sep}{check}", [*e.get("items", []), i["id"]]
    return [e for e in out if e["id"] not in gone]


def decision_id(text: str) -> str:
    """ergostat's own id of a decision (ergostat.decisions.kinds.item_id): the same sentence, the same item."""
    ws = re.findall(r"[a-z0-9]+", text.lower())
    tail = "-".join([w for w in ws if w not in STOP][:6] or ["untitled"])[:48].strip("-")
    return f"{DECISION}/{tail}-{hashlib.sha1(' '.join(ws).encode()).hexdigest()[:4]}"


def decisions() -> dict[str, dict]:
    """decisions.md as proposals, by ergostat.decision id: its heading the decision, its body the owner's words, its
    *Areas* the scope. Refused like entries(), and two headings of one id too."""
    out = {}
    for _, head, text, areas in sections(fac.HERE / "knowledge" / "decisions.md"):
        iid = decision_id(head)
        if iid in out:
            raise Refused(f"decisions.md: {head!r} is the same decision as {out[iid]['decision']!r}")
        words = " ".join(re.sub(r"\*Areas:.*?\.\*", "", text.split("\n", 1)[-1], flags=re.S).split())
        out[iid] = {"decision": head, "scope": areas, "proposed_by": "knowledge-sync",
                    "words": [{"text": words or head, "file": "dev/knowledge/decisions.md"}]}
    return out


def held() -> list[dict]:
    """Every ergostat.decision item, in any state. A failed lookup raises, and one that did not give them all is
    refused: never taken as "none"."""
    got = json.loads(fac.ergostat("item", "--kind", DECISION, "--json").stdout)
    if got["total"] != len(got["items"]):
        raise Refused(f"the record gave {len(got['items'])} of {got['total']} {DECISION} items")
    return got["items"]


def shown(d: dict) -> str:
    """A decision item in a brief: the decision, the owner's first words, its scope and id; a proposed one marked."""
    f = d["fields"]
    words = str(((f.get("words") or [{}])[0]).get("text") or "")
    return (f"- **{f.get('decision')}**" + (" (proposed: not yet confirmed by the owner)" if d["state"] == "proposed"
                                            else "") + (f" {words}" if words != f.get("decision") else "")
            + f" *Areas: {', '.join(f.get('scope') or [])}.* ({d['id']})")


def first_line(src: str) -> str:
    try:
        doc = " ".join((ast.get_docstring(ast.parse(src)) or "").split())
    except SyntaxError:
        doc = ""
    doc = re.split(r"(?<=\.)\s", doc, maxsplit=1)[0]
    return (doc if len(doc) <= 140 else doc[:137].rsplit(" ", 1)[0] + "...") if doc else "(no docstring)"


def mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except FileNotFoundError:   # pruned by another session already: sorted oldest, and its unlink is a no-op
        return 0.0


def module_map(cfg: dict) -> tuple[str, dict[str, list[list[str]]]]:
    """(main's sha, {package: [[module, its docstring's first sentence]]}), read from the checkout's main with git,
    cached by its sha: a merge makes a new one. The last three are kept; only files named for a sha are removed.
    Safe with sessions starting together: one read (a missing or partial file is made again), a renamed whole write,
    and a prune that keeps its own sha's file and skips one already gone."""
    repo, d = fac.path(cfg, "checkout"), fac.run_dir(cfg, "modules")
    sha = fac.git(repo, "rev-parse", cfg["git"]["base"])
    try:                    # one read: a file another session removed or is half-way writing is made again
        return sha, json.loads((d / f"{sha}.json").read_text())
    except (FileNotFoundError, ValueError):
        pass
    there = fac.git(repo, "ls-tree", "--name-only", sha, "--", "ergostat", "dev/bin", "scripts").split()
    raw = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha, "--", *there], capture_output=True,
                         check=True, timeout=300).stdout if there else b""
    out: dict[str, list[list[str]]] = {}
    with tarfile.open(fileobj=io.BytesIO(raw or bytes(1024))) as tar:
        for m in sorted((m for m in tar if m.isfile() and m.name.endswith(".py")), key=lambda m: m.name):
            pkg, _, mod = m.name.rpartition("/")
            out.setdefault(pkg, []).append([mod, first_line(tar.extractfile(m).read().decode(errors="replace"))])
    tmp = ""
    try:                    # written whole, then renamed into place: no reader sees part of it
        fd, tmp = tempfile.mkstemp(dir=d, prefix=f".{sha}.", suffix=".tmp")
        os.fchmod(fd, 0o644)  # mkstemp makes 0600; readable by others as write_text left it
        with os.fdopen(fd, "w") as w:
            w.write(json.dumps(out))
        os.replace(tmp, d / f"{sha}.json")
    except OSError:         # a cache that cannot be written is not a failure: the map is still the map
        if tmp:
            Path(tmp).unlink(missing_ok=True)
    for p in sorted((p for p in d.glob("*.json") if re.fullmatch(r"[0-9a-f]{40}", p.stem) and p.stem != sha),
                    key=mtime)[:-2]:        # its own sha's file is never pruned; one already gone is skipped
        p.unlink(missing_ok=True)
    for p in d.glob(".*.tmp"):              # left by a session killed mid-write; a live write is seconds old
        if re.fullmatch(r"\.[0-9a-f]{40}\..+\.tmp", p.name) and time.time() - mtime(p) > 600:
            p.unlink(missing_ok=True)
    return sha, out


def render_map(mods: dict, touched: list[str], room: int) -> str:
    """The packages the gap touches in full, every other one by its modules' names; cut to ``room``."""
    near = {str(Path(t).parent) for t in touched}
    text = "".join([f"- `{p}/`\n" + "".join(f"  - {m}: {s}\n" for m, s in rows) for p, rows in mods.items() if p in near]
                   + [f"- `{p}/`: {', '.join(m for m, _ in rows)}\n" for p, rows in mods.items() if p not in near])
    return text if len(text) <= room else text[:max(0, room - 40)].rsplit("\n", 1)[0] + "\n- (cut to the budget)\n"


def related(cfg: dict, gap: dict) -> list[tuple[str, str]]:
    """The gaps near this one (what it depends on, its parent and siblings, its GAPS.md section): each one's
    definition, state and where it stopped."""
    import brief
    f, gaps = gap["fields"], {g["id"]: g for g in fac.items("gap")}
    mine = fac.ids(f.get("parent"))
    near = [*fac.ids(f.get("depends_on")), *mine] + [i for i, g in gaps.items() if (mine and fac.ids(
        g["fields"].get("parent")) == mine) or (f.get("section") and g["fields"].get("section") == f.get("section"))]
    out = []
    for gid in [n for n in dict.fromkeys(near) if n in gaps and n != gap["id"]][:6]:
        g = gaps[gid]["fields"]
        try:
            text = brief.definition_text(cfg, str(g.get("definition") or ""), fac.branch_of(gaps[gid]))
        except ValueError:
            text = ""
        stop = str(g.get("where_it_stopped") or "").strip()
        out.append((gid, f"### {gid} ({gaps[gid]['state']}): {g.get('title', '')}\n\n{text.strip()[:1500]}\n"
                         + (f"\n**Where it stopped:** {stop[:1500]}\n" if stop else "")))
    return out


def findings(touched: list[str]) -> list[tuple[str, str]]:
    """Past reviews' findings naming a file this gap touches (by path, or a .py by its name), the latest first."""
    keys = set(touched) | {Path(t).name for t in touched if t.endswith(".py")}
    out = []
    for r in sorted(fac.items("review"), key=lambda r: -float(r["fields"].get("written_at") or 0)):
        rf = r["fields"]
        hit = [x for x in (rf.get("blocking") or []) + (rf.get("non_blocking") or []) if any(k in x for k in keys)]
        if hit:
            out.append((r["id"], f"- {r['id']} ({rf.get('verdict')}):\n" + "".join(f"  - {x[:400]}\n" for x in hit[:4])))
    return out[:12]


def block(cfg: dict, role: str, gap: dict, text: str) -> tuple[str, dict]:
    """A brief's knowledge for ``role``, given the gap's own text (its definition, GAPS entry, a reviewer's diff), and
    what it carried: {knowledge: [ids], knowledge_dropped: [ids], knowledge_chars}."""
    k, unread = cfg.get("knowledge") or {}, ""
    budget, es = int(k.get(f"{role}_chars") or k.get("chars") or 24000), entries()
    try:
        es = applied(es, fac.items("lesson"))
    except (RuntimeError, ValueError, OSError) as e:                 # said in the brief, never carried as none
        unread = (f"\n\n**The applied lessons could not be read from the record** ({str(e)[:200]}): this brief "
                  "carries only the repository's.")
    touched = sorted(set(FILES.findall(text)))
    words = set(re.findall(r"[a-z]+", f"{text} {gap['fields'].get('title', '')}".lower()))
    rules = [e for e in es if e["kind"] == "rule" and role != "plan_reviewer"]
    lessons = [e for e in es if e["kind"] == "lesson"]
    parts = ["## The house rules\n\n" + "\n".join(e["text"].replace("## ", "**", 1).replace("\n", "**\n", 1)
                                                  for e in rules)] if rules else []
    parts.append("## What reviews keep finding (the review lessons, by id)\n\n" + "\n\n".join(
        e["text"].replace(f"## {e['id'][7:]}.", f"### {e['id']}:", 1) for e in lessons) + unread)
    ids = [e["id"] for e in rules + lessons] + [i for e in lessons for i in e.get("items", [])]
    dropped, used = [], sum(map(len, parts))
    for name in MORE.get(role, ()):
        if name == "decisions":
            ds = sorted((d for d in held() if d["state"] in ("confirmed", "proposed") and any(
                a in words or a + "s" in words for a in d["fields"].get("scope") or [])), key=lambda d: d["state"])
            got = [(d["id"], shown(d)) for d in ds]                      # the confirmed first
        elif name == "modules":
            sha, mods = module_map(cfg)
            got = [(f"modules@{sha[:12]}", render_map(mods, touched, budget - used - 80))] if budget - used > 500 \
                else [(f"modules@{sha[:12]}", " " * budget)]
        else:
            got = related(cfg, gap) if name == "related" else findings(touched) if touched else []
        took = []
        for eid, body in got:
            fits = used + len(body) + len(HEADS[name]) + 8 <= budget
            (took if fits else dropped).append(body if fits else eid)
            ids += [eid] if fits else []
            used += len(body) + 1 if fits else 0
        if took:
            parts.append(f"## {HEADS[name]}\n\n" + "\n".join(took))
            used += len(HEADS[name]) + 8
    out = "\n\n".join(parts)
    return out, {"knowledge": ids, "knowledge_dropped": dropped, "knowledge_chars": len(out),
                 **({"knowledge_unread": ["lessons"]} if unread else {})}


def short(text: str, most: int = 300) -> str:
    """An entry's text on one line, cut at a word to ``most`` characters."""
    text = " ".join(text.split())
    return text if len(text) <= most else text[:most - 3].rsplit(" ", 1)[0] + "..."


def carried() -> dict[str, int]:
    """How many briefs carried each id: the recorded brief contexts (on the gaps and the research questions)."""
    out: dict[str, int] = {}
    for kind in ("gap", "research"):
        for it in fac.items(kind):
            for c in it["fields"].get("contexts") or []:
                for k in set(c.get("knowledge") or []):
                    out[k] = out.get(k, 0) + 1
    return out


def sync() -> tuple[int, ...]:
    """The collector: each entry of the running version's dev/knowledge/, with the applied lessons (applied()), as an
    item knowledge/<id>. A new entry (or one
    back after it was retired) is knowledge.found, one whose fields differ from its item's is knowledge.changed with
    only those fields, and an active item no file holds any more is knowledge.retired; nothing else is said, so a
    second run says nothing. Each decision of decisions.md whose ergostat.decision id is in no state (never proposed,
    so never dismissed or superseded either) is proposed (ergostat.decision.proposed). All or nothing: everything is
    read first, and a file refused or decisions not read raise before a line is printed. Two overlapping runs that
    both propose one decision record it once: ergostat records the proposal under its own event id, checked inside
    the record's write lock, and adds words only when they differ (acts.propose). (found, changed, retired, proposed)"""
    es, ds, have = applied(entries(), fac.items("lesson")), decisions(), {d["id"] for d in held()}
    known, counts, now = {i["id"]: i for i in fac.items("knowledge")}, carried(), time.time()
    said: list[tuple[str, str, dict]] = []
    for e in es:
        iid = f"knowledge/{e['id']}"
        want = {"title": e["title"], "kind": e["kind"], "file": e["file"], "text": short(e["text"]),
                "carried": counts.get(e["id"], 0), **({"areas": e["areas"]} if e["areas"] else {}),
                **({"about": e["about"]} if e["about"] else {})}
        it = known.get(iid)
        if it is None or it["state"] != "active":
            again = {"about": []} if it is not None and it["fields"].get("about") and not e["about"] else {}
            said.append(("knowledge.found", iid, {**want, **again, "found_at": now}))  # found again: old about cleared
            continue
        diff = {k: v for k, v in want.items() if it["fields"].get(k) != v}
        for k in ("areas", "about"):                                       # taken out of the file: cleared
            if it["fields"].get(k) and not e[k]:
                diff[k] = []
        if diff:
            said.append(("knowledge.changed", iid, {**diff, "changed_at": now}))
    held_ids = {f"knowledge/{e['id']}" for e in es}
    said += [("knowledge.retired", iid, {"retired_at": now}) for iid, it in known.items()
             if it["state"] == "active" and iid not in held_ids]
    said += [(f"{DECISION}.proposed", iid, d) for iid, d in ds.items() if iid not in have]
    for event, iid, data in said:
        fac.say(event, iid, **data)
    return tuple(sum(e.endswith(x) for e, _, _ in said) for x in (".found", ".changed", ".retired", ".proposed"))


if __name__ == "__main__":
    if sys.argv[1:] == ["count"]:
        print(len(entries()))
    elif sys.argv[1:] == ["sync"]:
        try:
            print("knowledge: {} found, {} changed, {} retired, {} decisions proposed".format(*sync()), file=sys.stderr)
        except Refused as e:
            raise SystemExit(f"knowledge: refused, nothing recorded: {e}") from None
    elif sys.argv[1:] == ["map"]:
        print(render_map(module_map(fac.config())[1], [], 10**9))
    else:
        raise SystemExit(__doc__)
