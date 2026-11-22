"""The intent judge on a model (SPEC §12i, ``model:`` on the judge): a reviewer that reads the work cold against what
the owner meant, one call per piece of work, on a cheap model (``haiku``).

It is given the brief (``brief.py``) as Markdown: the work (its fields, its done-when, its change), then each thing it
is held to, with its id; and asked for one verdict line. What it answers is checked, not trusted: an unmet or
contradicted verdict must name, for each point, something it was given (an id, or ``done-when``) and quote the work
exactly (a line of the diff or a field's value, whitespace aside); points that do not are dropped, and a verdict left
with none is **unjudged** (``unsupported``). A met verdict needs no quote. Its cost is capped per call
(``--max-budget-usd``) and recorded with the verdict. The model runs as ``$ERGOSTAT_AI`` (``claude -p`` by
default), with no tools, so it reads only what it is given."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..decisions.ai import Spent, call, norm

PROMPT = Path(__file__).with_name("prompt.md")
SYSTEM = "You judge whether finished work is done as its owner meant. Answer only in JSON lines."
ANSWER = """

---
Answer with one JSON line and nothing else (no prose, no code fences):
{"verdict": "met|unmet|contradicted", "why": "one or two sentences", "evidence": [{"against": "an id listed above, or done-when", "says": "what goes against it", "quote": "text copied exactly from the work"}]}
"""  # noqa: E501


def render(brief: dict) -> str:
    w = brief["work"]
    out = [f"# The work: {w['id']} ({w['kind']})", "",
           f"It entered `{w['at']}` (it says it is done); it is now `{w['state']}`.", ""]
    if w.get("done_when"):
        out += ["## Done when (the owner's words, verbatim)", "", f"> {w['done_when']}", ""]
    out += ["## Its fields", ""]
    for k, v in w["fields"].items():
        out.append(f"- {k}: {v if isinstance(v, str) else json.dumps(v, default=str)}")
    out.append("")
    if brief.get("diff"):
        out += [f"## Its change ({brief['change'].get('rev')}, against {brief['change'].get('base')})", "", "```diff",
                brief["diff"].rstrip(), "```", ""]
    elif brief.get("change", {}).get("note"):
        out += [f"(Its change is not shown: {brief['change']['note']}.)", ""]
    out += ["# What it is held to", ""]
    for x in brief["against"]:
        if x["type"] == "done-when":
            continue
        head = {"decision": "Decision", "correction": "Correction", "message": "The owner's message"}[x["type"]]
        out.append(f"## {head} `{x['id']}`")
        out.append("")
        out.append(x["text"])
        for q in x.get("words") or []:
            out.append(f"> {q}")
        for r in x.get("reasons") or []:
            out.append(f"- Why: {r}")
        for a in x.get("rejected") or []:
            out.append(f"- Rejected: {a.get('option')}" + (f" ({a['why']})" if a.get("why") else ""))
        if x.get("corrects"):
            out.append(f"- Corrects: {x['corrects']}")
        out.append("")
    return "\n".join(out)


def answer(text: str) -> dict | None:
    for raw in reversed((text or "").splitlines()):
        raw = raw.strip().strip("`").strip()
        if not raw.startswith("{"):
            continue
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("verdict"), dict):
            d = d["verdict"]
        if isinstance(d, dict) and d.get("verdict") in ("met", "unmet", "contradicted"):
            return d
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict) and d.get("verdict") in ("met", "unmet", "contradicted"):
                return d
        except ValueError:
            pass
    return None


def checked(d: dict, brief: dict) -> tuple[str, str, list[dict], int]:
    """The verdict with its evidence checked: (verdict, why, evidence kept, points dropped)."""
    verdict, why = d["verdict"], str(d.get("why") or "")[:1000]
    ids = {x["id"] for x in brief["against"]} | {"done-when"}
    work_text = norm((brief.get("diff") or "") + "\n" + "\n".join(
        f"{k}: {v if isinstance(v, str) else json.dumps(v, default=str)}" for k, v in brief["work"]["fields"].items()))
    plain = norm(re.sub(r"(?m)^[+\- ]", "", brief.get("diff") or ""))
    kept, dropped = [], 0
    for e in d.get("evidence") or []:
        if not isinstance(e, dict):
            continue
        q = norm(str(e.get("quote") or "")).strip('"').strip()
        q = re.sub(r"^[+\-] ?", "", q)
        ok_id = str(e.get("against") or "") in ids
        ok_quote = len(q) >= 3 and (q in work_text or q in plain)
        if verdict == "met":
            kept.append({k: str(v)[:500] for k, v in e.items() if k in ("against", "says", "quote")})
        elif ok_id and ok_quote:
            kept.append({"against": str(e["against"]), "says": str(e.get("says") or "")[:500], "quote": q[:300]})
        else:
            dropped += 1
    if verdict != "met" and not kept:
        return "unjudged", f"unsupported: the model said {verdict} ({why[:300]}), but none of its evidence named what " \
            f"it was held to and quoted the work", [], dropped
    return verdict, why, kept, dropped


def judge(brief: dict, model: str, cap: float | None, instructions: str | None = None,
          permit: dict | None = None) -> tuple[str, str, list[dict], dict]:
    """(verdict, why, evidence, spent). ``permit``: the day's budget's, taken by the pass (SPEC §9.9)."""
    spent = Spent()
    head = (instructions or PROMPT.read_text(encoding="utf-8")).rstrip()
    text = call(head + "\n\n" + render(brief) + ANSWER, model, cap, spent, timeout=300, system=SYSTEM, permit=permit)
    d = answer(text)
    cost = {"cost_usd": round(spent.cost_usd, 5), "tokens_in": spent.tokens_in, "tokens_out": spent.tokens_out,
            "calls": spent.calls}
    if d is None:
        why = "; ".join(spent.notes) or f"no verdict in its answer: {text.strip()[:200]!r}"
        return "unjudged", f"the model gave no verdict ({why})", [], cost
    verdict, why, ev, dropped = checked(d, brief)
    if dropped:
        cost["dropped_evidence"] = dropped
    return verdict, why, ev, cost
