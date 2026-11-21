"""The briefs: what an implementor's or a reviewer's session is given, assembled from a template in dev/prompts/ and
the gap (its definition, its GAPS entry, the guides it names, the findings of its earlier reviews, the diff for a
reviewer), the factory's knowledge (knowledge.py: the rules, the lessons, decisions, related gaps, past findings, the
module map, within a budget), and the record of what went in, so the model can learn which context drives first-pass yield.

A reviewer is never given the implementor's reasoning: no session text, no transcript, only the work itself."""

from __future__ import annotations

import re
import time
from pathlib import Path

import fac
import knowledge

ALWAYS = {"implementor": ["CLAUDE.md", "NOTES.md"], "reviewer": ["CLAUDE.md", "NOTES.md"]}
DOC = re.compile(r"\b((?:docs|examples|scripts|tests|ergostat)/[\w./-]+\.(?:md|py|yaml))\b")
DIFF_MOST = 60_000           # characters of the diff a reviewer is given whole; past it, the stat and the files
PATH = re.compile(r"^[\w.-]+(?:/[\w.-]+)+/?$|^[\w.-]+\.(?:py|md|yaml|yml|toml|sh|js|css|html|json)$")
ACTIVE = ("fix", "building", "built", "in-review", "approved", "queued", "push-pending", "queue-failed")


def definition_text(cfg: dict, where: str, branch: str) -> str:
    """A gap's definition, only from where the coordinator writes one: a file in the instance's run/defs/, or
    `REF:dev/records/NAME.md` (or the old `REF:docs/roadmap/overnight/NAME.md`) on main or the gap's own branch, in
    the checkout or the drop. Anything else (another path, the text itself) is refused: ""."""
    defs = fac.run_dir(cfg, "defs").resolve()
    p = Path(where)
    p = (p if p.is_absolute() else fac.MODEL / p).resolve()
    if defs in p.parents and p.suffix == ".md" and p.is_file():
        return p.read_text()
    m = fac.REF.fullmatch(where)
    if m and m.group(1) in (cfg["git"]["base"], branch, fac.git_branch(branch)):
        for repo in (fac.path(cfg, "checkout"), fac.path(cfg, "live") / "drop.git"):
            ref = m.group(1) if m.group(1) == cfg["git"]["base"] else fac.git_branch(branch)
            if repo.exists() and fac.git_ok(repo, "cat-file", "-e", f"{ref}:{m.group(2)}"):
                return fac.git(repo, "show", f"{ref}:{m.group(2)}")
    return ""


def gaps_entry(cfg: dict, title: str) -> str:
    """The gap's whole entry in GAPS.md on main (the bullet and what is indented under it)."""
    if not title:
        return ""
    text = fac.git(fac.path(cfg, "checkout"), "show", f"{cfg['git']['base']}:docs/GAPS.md", check=False)
    lines, out = text.splitlines(), []
    for i, line in enumerate(lines):
        if line.startswith(f"- **{title}"):
            out.append(line)
            for nxt in lines[i + 1:]:
                if nxt.startswith(("- ", "#")) or not nxt.strip():
                    break
                out.append(nxt)
            break
    return "\n".join(out)


def findings_text(findings: list) -> str:
    if not findings:
        return "(none: this is the first round)"
    return "\n".join(f"- {f}" for f in findings)


def assemble(cfg: dict, role: str, gap: dict, worktree: Path, **extra) -> tuple[str, dict]:
    """(the brief, what it was made of)."""
    f = gap["fields"]
    template = fac.HERE / "prompts" / f"{role}.md"
    definition = extra.pop("definition", None) or definition_text(cfg, str(f.get("definition", "")),
                                                                  fac.branch_of(gap))
    entry = gaps_entry(cfg, f.get("title", ""))
    named = sorted({m for m in DOC.findall(definition + "\n" + entry) if (worktree / m).exists()})
    always = ALWAYS.get(role, ["CLAUDE.md"])
    guides = always + [g for g in named if g not in always]
    know, carried = knowledge.block(cfg, role, gap, f"{definition}\n{entry}\n{extra.get('diff', '')}")
    findings = list(f.get("findings") or [])
    values = {
        "gap": gap["id"], "title": f.get("title", gap["id"]), "branch": fac.git_branch(fac.branch_of(gap)), "worktree": "/work",
        "base": cfg["git"]["base"], "definition": definition.strip(), "gaps_entry": entry or "(not in GAPS.md)",
        "guides": "\n".join(f"- {g}" for g in guides), "findings": findings_text(findings),
        "definition_path": fac.definition_file(gap, worktree), "budget": str(fac.budget_of(definition)),
        "round": str(int(f.get("rounds") or 0) + 1), "knowledge": know, **{k: str(v) for k, v in extra.items()},
    }
    text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template.read_text())
    context = {"role": role, "template": f"dev/prompts/{role}.md", "guides": guides, "files": named,
               "findings": len(findings), "definition_chars": len(definition), "gaps_entry": bool(entry),
               "brief_chars": len(text), "brief_tokens": len(text) // 4,
               "diff_chars": len(extra.get("diff", "")), "model": cfg["ai"][f"{role}_model"], **carried}
    return text, context


def save(cfg: dict, role: str, gap: dict, text: str) -> str:
    """Kept in the instance's run/ folder (never in git): a file field of the item."""
    d = fac.run_dir(cfg, "briefs")
    n = len(list(d.glob(f"{fac.branch_of(gap)}-{role}-*.md"))) + 1
    p = d / f"{fac.branch_of(gap)}-{role}-{n}.md"
    p.write_text(text)
    try:
        return f"file:{p.relative_to(fac.MODEL)}"
    except ValueError:
        return str(p)


def section(body: str, name: str) -> str | None:
    """The text under a definition's `## NAME` heading (to the next one), or None when it has none."""
    m = re.search(rf"^## {re.escape(name)}[^\n]*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return m[1] if m else None


def files_of(body: str) -> list[tuple[str, bool]]:
    """The paths under `## Files to touch` (backticked, or a bullet's first word), each with whether its line says
    it is new."""
    out = []
    for line in (section(body, "Files to touch") or "").splitlines():
        got = [x.rstrip(",;:") for x in re.findall(r"`([^`\s]+)`", line) or re.findall(r"^\s*[-*]\s+(\S+)", line)]
        new = bool(re.search(r"\bnew\b", line, re.I))
        out += [(x.rstrip("/"), new) for x in got if PATH.match(x)]
    return list(dict.fromkeys(out))


def touches(cfg: dict, g: dict) -> list[str]:
    """The files a gap's definition (or, while planned, its plan) names to touch."""
    try:
        text = definition_text(cfg, str(g["fields"].get("definition") or ""), fac.branch_of(g))
        p = fac.run_dir(cfg, "plans") / f"{fac.branch_of(g)}.md"
    except ValueError:
        return []
    return [f for f, _ in files_of(text or (p.read_text() if p.is_file() else ""))]


def graph(cfg: dict, gap: dict, most: int = 40, days: float = 3) -> str:
    """The task graph around a gap, for the planner and the plan reviewer: gaps merged in the last ``days`` (the files
    their merge changed), gaps active (held by a run, or building to queued: the files they touch) and gaps ready or
    planned (the same, and what they depend on). At most ``most`` lines: each section its share, the rest counted."""
    repo, since = fac.path(cfg, "checkout"), time.time() - days * 86400
    gaps = [g for g in fac.items("gap") if g["id"] != gap["id"]]

    def names(fs: list[str]) -> str:
        return ", ".join(fs[:8]) + (f" (+{len(fs) - 8} more)" if len(fs) > 8 else "") if fs else "(none named)"

    def row(g: dict, what: str) -> str:
        f = g["fields"]
        return f"- {g['id']} ({g['state']}, `{f.get('branch', '')}`): {str(f.get('title', ''))[:90]}. {what}"[:300]

    def changed(g: dict) -> list[str]:
        sha = str(g["fields"].get("main_sha") or "")
        return fac.git(repo, "diff", "--name-only", f"{sha}^1", sha, check=False).split() if sha else []

    held = lambda g: bool((g["fields"].get("lease") or {}).get("holder")) and g["state"] in ("open", "replan", "planned")  # noqa: E731
    merged = sorted((g for g in gaps if g["state"] == "merged" and float(g["fields"].get("merged_at") or 0) >= since),
                    key=lambda g: -float(g["fields"]["merged_at"]))
    parts = [(f"Merged in the last {days:g} days (never plan these again)",
              [row(g, "Changed: " + names(changed(g))) for g in merged]),
             ("Active (being planned or built: a file here is a conflict risk)",
              [row(g, "Touches: " + names(touches(cfg, g))) for g in gaps if g["state"] in ACTIVE or held(g)]),
             ("Ready or planned (to be built next)",
              [row(g, f"Touches: {names(touches(cfg, g))}. Depends on: "
                      f"{', '.join(fac.ids(g['fields'].get('depends_on'))) or 'none'}")
               for g in gaps if g["state"] in ("ready", "planned") and not held(g)])]
    out, room = [], most - len(parts)                   # each section its share of what is left, its header apart
    for i, (head, rows) in enumerate(parts):
        cap = max(1, room // (len(parts) - i))
        shown = rows if len(rows) <= cap else rows[:cap - 1] + [f"- ... and {len(rows) - cap + 1} more not shown"]
        out += [f"### {head}", *(shown or ["(none)"])]
        room -= max(1, len(shown))
    return "\n".join(out)
