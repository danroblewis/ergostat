"""The guides shipped with ergostat, by name, for ``ergostat help NAME`` and the MCP tools: the
guides in ``help/``, the format (``spec``, docs/SPEC.md), the guidelines for improving a model
(``modelling``, docs/MODELLING.md), the model tools and where each shows up (``model-tools``,
docs/MODEL-TOOLS.md), claims and trust (``claims``, docs/CLAIMS.md), the owner's decisions and corrections
(``decisions``, docs/DECISIONS.md), messages (``messages``, docs/MESSAGES.md), adding a small control system from
templates (``adding``, docs/ADDING.md), and the skills for AI agents (``skills/NAME/SKILL.md``, and
docs/skills/NAME/SKILL.md). An
installed ergostat has the three documents copied into ``help/``; a clone reads them from ``docs/``."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = {"spec": "SPEC.md", "modelling": "MODELLING.md", "model-tools": "MODEL-TOOLS.md",   # a guide that is a document in docs/
        "claims": "CLAIMS.md", "decisions": "DECISIONS.md", "messages": "MESSAGES.md", "adding": "ADDING.md"}


def guides() -> dict[str, Path]:
    out = {p.stem: p for p in sorted((HERE / "help").glob("*.md")) if p.stem not in DOCS}
    for name, doc in DOCS.items():
        here = HERE / "help" / f"{name}.md"
        out[name] = here if here.is_file() else HERE.parent / "docs" / doc
    for p in sorted((HERE / "skills").glob("*/SKILL.md")):
        out[p.parent.name] = p
    for p in sorted((HERE.parent / "docs" / "skills").glob("*/SKILL.md")):    # a clone's (an install has them in skills/)
        out.setdefault(p.parent.name, p)
    return dict(sorted(out.items()))


def read(name: str) -> str | None:
    p = guides().get(name)
    return p.read_text(encoding="utf-8") if p is not None and p.is_file() else None
