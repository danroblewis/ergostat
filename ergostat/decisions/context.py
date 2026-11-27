"""The projections of the owner's intent, rendered as Markdown to put at the start of a session (harness parity
§2.10, its first two recipes): ``ergostat context decisions`` and ``ergostat context corrections``.

Each takes the confirmed items (``--proposed`` adds the ones still waiting, marked so), most relevant first, and
fits them in a budget: as many in full as fit (the sentence, the owner's words with where they were said, the
reasons, what was rejected, the scope), then the rest as one-line pointers by id, then a count of what did not
fit at all. Relevance is the scope asked for: an item whose scope or kind of work names it comes first, then one
whose words mention it, then the rest; within each, the newest first. A budget is characters (``6000``) or
tokens (``1500t``, at four characters a token)."""

from __future__ import annotations

import re

from . import acts
from .kinds import CORRECTION, DECISION, words_of

QUOTE = 600                 # the owner's words, at most, in one entry (cut with [...] and their source kept)
CHARS_PER_TOKEN = 4


def budget_of(text: str | int | None, default: int = 8000) -> int:
    if text is None or text == "":
        return default
    if isinstance(text, int):
        return text
    m = re.fullmatch(r"\s*(\d+)\s*(t|tok|tokens|c|chars)?\s*", str(text), re.I)
    if not m:
        raise ValueError(f"--budget: characters (6000) or tokens (1500t), not {text!r}")
    n = int(m.group(1))
    return n * CHARS_PER_TOKEN if (m.group(2) or "").lower().startswith("t") else n


def relevance(it, terms: list[str], keys: tuple[str, ...]) -> int:
    if not terms:
        return 0
    f = it.fields
    tagged = {w for k in keys for x in (f.get(k) or []) for w in words_of(str(x))}
    said = set(words_of(" ".join([str(f.get("decision") or f.get("correction") or ""), str(f.get("corrects") or "")] +
                                 [w.get("text", "") for w in f.get("words") or []])))
    return 2 * sum(1 for t in terms if t in tagged) + sum(1 for t in terms if t in said)


def chosen(p, kind: str, scope: str | None, proposed: bool) -> list:
    states = ("confirmed", "proposed") if proposed else ("confirmed",)
    its = [i for i in acts.items(p, kind) if i.state in states]
    terms = [w for w in words_of(scope or "") if len(w) > 1]
    keys = ("scope",) if kind == DECISION else ("kind_of_work", "scope")
    if kind == CORRECTION and terms:           # corrections for this kind of work, and those for any work
        its = [i for i in its if relevance(i, terms, keys) or "general" in (i.fields.get("kind_of_work") or [])]
    return sorted(its, key=lambda i: (-relevance(i, terms, keys), i.state != "confirmed", -i.last))


def _where(w: dict) -> str:
    bits = []
    if w.get("session"):
        bits.append(f"session {str(w['session'])[:8]}")
    if w.get("line"):
        bits.append(f"line {w['line']}")
    if w.get("time"):
        bits.append(str(w["time"])[:16].replace("T", " "))
    if w.get("event") and not bits:
        bits.append(f"event {str(w['event'])[:12]}")
    return ", ".join(bits)


def _quote(w: dict) -> str:
    t = " ".join(str(w.get("text") or "").split())
    if len(t) > QUOTE:
        t = t[:QUOTE].rsplit(" ", 1)[0] + " [...]"
    where = _where(w)
    return f"> {t}" + (f"\n> ({where})" if where else "")


def entry(it, kind: str, repeats: dict[str, int]) -> str:
    f = it.fields
    head = f.get("decision") if kind == DECISION else f.get("correction")
    mark = "" if it.state == "confirmed" else " (proposed, not yet confirmed)"
    out = [f"### {head}{mark}", ""]
    for w in (f.get("words") or [])[:2]:
        out += [_quote(w), ""]
    rows = []
    if kind == DECISION:
        if f.get("reasons"):
            rows.append(f"- Why: {'; '.join(f['reasons'])}")
        for a in f.get("alternatives") or []:
            rows.append(f"- Rejected: {a.get('option')}" + (f" ({a['why']})" if a.get("why") else ""))
        if f.get("supersedes"):
            rows.append(f"- Replaces: {', '.join(f['supersedes'])}")
    else:
        if f.get("corrects"):
            rows.append(f"- Corrects: {f['corrects']}")
        if f.get("kind_of_work"):
            rows.append(f"- Kind of work: {', '.join(f['kind_of_work'])}")
        n = repeats.get(it.id, 0)
        if n:
            rows.append(f"- Given {n + 1} times: it did not stick the first time")
    if f.get("scope"):
        rows.append(f"- Scope: {', '.join(f['scope'])}")
    rows.append(f"- Id: {it.id}")
    return "\n".join(out + rows) + "\n"


def render(p, kind: str, scope: str | None = None, budget: int = 8000, proposed: bool = False) -> str:
    its = chosen(p, kind, scope, proposed)
    word = "decisions" if kind == DECISION else "corrections"
    repeats: dict[str, int] = {}
    if kind == CORRECTION:
        for i in acts.items(p, CORRECTION):
            r = i.fields.get("repeats")
            if r and i.state != "dismissed":
                repeats[r] = repeats.get(r, 0) + 1
    title = "Decisions in force" if kind == DECISION else "Corrections to keep"
    about = f" for {scope}" if scope else ""
    lead = (f"# {title}{about}\n\n" +
            (f"The owner's confirmed {word}{', and those still proposed' if proposed else ''}, most relevant first. "
             f"Hold to them; one that no longer fits is superseded by the owner with a reason, never silently "
             f"broken.\n" if kind == DECISION else
             f"What the owner corrected before{about}, in their words. Do not make the owner say it again.\n"))
    if not its:
        return lead + f"\nNone {'confirmed' if not proposed else 'yet'}.\n"
    used = len(lead)
    full, short = [], []
    for it in its:
        e = entry(it, kind, repeats)
        if not short and used + len(e) + 2 <= budget:
            full.append(e.rstrip("\n"))
            used += len(e) + 2
        else:
            short.append(it)
    text = lead.rstrip("\n") + "\n\n" + "\n\n".join(full) + ("\n" if full else "")
    rest = 0
    if short:
        head = f"## Also {'decided' if kind == DECISION else 'corrected'} (`ergostat item ID` shows one in full)\n\n"
        lines = []
        used += len(head) + 1
        for it in short:
            f = it.fields
            line = f"- {f.get('decision') or f.get('correction')} ({it.id})\n"
            if used + len(line) > budget:
                rest += 1
                continue
            lines.append(line)
            used += len(line)
        if lines:
            text += "\n" + head + "".join(lines)
    if rest:
        text += f"\n{rest} more not shown: `ergostat item --projection {kind}` lists them.\n"
    return text
