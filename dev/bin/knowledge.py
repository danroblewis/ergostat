"""The factory's knowledge in its briefs (dev/knowledge/README.md), put together by priority within a size budget
([knowledge] in dev/factory.toml): the house rules and the review lessons always; then, as they fit, the decisions whose
areas the gap's text names, related gaps, past review findings on the files it touches, and the module map of main.
Each brief records the ids it carried and dropped, so the model can relate what a brief carried to how its gap did.

    knowledge.py count | map     the entries (a sensor) | the module map (cached by main's sha in run/modules/)"""

from __future__ import annotations

import ast
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

sys.dont_write_bytecode = True
import fac  # noqa: E402

PATTERNS = {"house-rules": (r"^\*\*(\w+).*?\*\*\n(.*?)(?=^\*\*|\Z)", "rules"),
            "review-lessons": (r"^## (\d+)\. (.+?)\n(.*?)(?=^## |\Z)", "lesson"),
            "decisions": (r"^- \*\*(.+?)\*\*(.*?)(?=^- |\Z)", "decision")}
FILES = re.compile(r"\b((?:ergostat|dev|scripts|tests|docs|examples)/[\w./-]+\.(?:py|md|yaml|toml|sh))\b")
MORE = {"implementor": ("decisions", "related", "findings", "modules"),   # beyond the rules and the lessons, in order
        "reviewer": ("decisions", "findings", "related", "modules"), "planner": ("decisions", "related", "findings",
        "modules"), "researcher": ("decisions", "modules")}
HEADS = {"decisions": "The owner's decisions this gap touches", "related": "Related gaps", "findings": "Past review "
         "findings on the files this gap touches", "modules": "The module map (main; the packages it touches in full)"}


def entries() -> list[dict]:
    """Every entry of dev/knowledge/: {id (rules-process, lesson-3, decision-<slug>), title, text, areas}."""
    out = []
    for stem, (rx, kind) in PATTERNS.items():
        for m in re.finditer(rx, (fac.HERE / "knowledge" / f"{stem}.md").read_text().split("\n---\n", 1)[-1], re.M | re.S):
            areas = re.search(r"\*Areas:\s+(.+?)\.\*", m[0], re.S)
            out.append({"id": f"{kind}-{m[1].lower() if kind != 'decision' else fac.slug(m[1], 32)}", "text": m[0].strip(),
                        "title": m[2] if kind == "lesson" else m[1],
                        "areas": [a.strip() for a in " ".join(areas[1].split()).split(",")] if areas else []})
    return out


def first_line(src: str) -> str:
    try:
        doc = " ".join((ast.get_docstring(ast.parse(src)) or "").split())
    except SyntaxError:
        doc = ""
    doc = re.split(r"(?<=\.)\s", doc, maxsplit=1)[0]
    return (doc if len(doc) <= 140 else doc[:137].rsplit(" ", 1)[0] + "...") if doc else "(no docstring)"


def module_map(cfg: dict) -> tuple[str, dict[str, list[list[str]]]]:
    """(main's sha, {package: [[module, its docstring's first sentence]]}), read from the checkout's main with git,
    cached by its sha: a merge makes a new one. The last three are kept; only files named for a sha are removed."""
    repo, d = fac.path(cfg, "checkout"), fac.run_dir(cfg, "modules")
    sha = fac.git(repo, "rev-parse", cfg["git"]["base"])
    if (d / f"{sha}.json").is_file():
        return sha, json.loads((d / f"{sha}.json").read_text())
    there = fac.git(repo, "ls-tree", "--name-only", sha, "--", "ergostat", "dev/bin", "scripts").split()
    raw = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", sha, "--", *there], capture_output=True,
                         check=True, timeout=300).stdout if there else b""
    out: dict[str, list[list[str]]] = {}
    with tarfile.open(fileobj=io.BytesIO(raw or bytes(1024))) as tar:
        for m in sorted((m for m in tar if m.isfile() and m.name.endswith(".py")), key=lambda m: m.name):
            pkg, _, mod = m.name.rpartition("/")
            out.setdefault(pkg, []).append([mod, first_line(tar.extractfile(m).read().decode(errors="replace"))])
    (d / f"{sha}.json").write_text(json.dumps(out))
    for p in sorted((p for p in d.glob("*.json") if re.fullmatch(r"[0-9a-f]{40}", p.stem)),
                    key=lambda p: p.stat().st_mtime)[:-3]:
        p.unlink()
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
    k = cfg.get("knowledge") or {}
    budget, es = int(k.get(f"{role}_chars") or k.get("chars") or 24000), entries()
    touched = sorted(set(FILES.findall(text)))
    words = set(re.findall(r"[a-z]+", f"{text} {gap['fields'].get('title', '')}".lower()))
    rules = [e for e in es if e["id"].startswith("rules-") and role != "plan_reviewer"]
    lessons = [e for e in es if e["id"].startswith("lesson-")]
    parts = ["## The house rules\n\n" + "\n".join(e["text"] for e in rules)] if rules else []
    parts.append("## What reviews keep finding (the review lessons, by id)\n\n" + "\n\n".join(
        e["text"].replace(f"## {e['id'][7:]}.", f"### {e['id']}:", 1) for e in lessons))
    ids, dropped, used = [e["id"] for e in rules + lessons], [], sum(map(len, parts))
    for name in MORE.get(role, ()):
        if name == "decisions":
            got = [(e["id"], e["text"]) for e in es if e["id"].startswith("decision-")
                   and any(a in words or a + "s" in words for a in e["areas"])]
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
    return out, {"knowledge": ids, "knowledge_dropped": dropped, "knowledge_chars": len(out)}


if __name__ == "__main__":
    if sys.argv[1:] == ["count"]:
        print(len(entries()))
    elif sys.argv[1:] == ["map"]:
        print(render_map(module_map(fac.config())[1], [], 10**9))
    else:
        raise SystemExit(__doc__)
