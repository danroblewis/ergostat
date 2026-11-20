"""The briefs: what an implementor's or a reviewer's session is given, assembled from a template in dev/prompts/ and
the gap (its definition, its GAPS entry, the guides it names, the findings of its earlier reviews, the diff for a
reviewer), the factory's knowledge (knowledge.py: the rules, the lessons, decisions, related gaps, past findings, the
module map, within a budget), and the record of what went in, so the model can learn which context drives first-pass yield.

A reviewer is never given the implementor's reasoning: no session text, no transcript, only the work itself."""

from __future__ import annotations

import re
from pathlib import Path

import fac
import knowledge

ALWAYS = {"implementor": ["CLAUDE.md", "NOTES.md"], "reviewer": ["CLAUDE.md", "NOTES.md"]}
DOC = re.compile(r"\b((?:docs|examples|scripts|tests|ergostat)/[\w./-]+\.(?:md|py|yaml))\b")
DIFF_MOST = 60_000           # characters of the diff a reviewer is given whole; past it, the stat and the files


def definition_text(cfg: dict, where: str, branch: str) -> str:
    """A gap's definition, only from where the coordinator writes one: a file in the instance's run/defs/, or
    `REF:docs/roadmap/overnight/NAME.md` on main or the gap's own branch, in the checkout or the drop. Anything else
    (another path, the text itself) is refused: ""."""
    defs = fac.run_dir(cfg, "defs").resolve()
    p = Path(where)
    p = (p if p.is_absolute() else fac.MODEL / p).resolve()
    if defs in p.parents and p.suffix == ".md" and p.is_file():
        return p.read_text()
    m = re.fullmatch(r"([\w/.-]+):(docs/roadmap/overnight/[a-z0-9-]+\.md)", where)
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
        "definition_path": fac.definition_file(gap), "budget": str(fac.budget_of(definition)),
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
