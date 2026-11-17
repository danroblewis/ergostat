"""Drafting the parity benchmark's cases from a session's transcript (``parity.py``): an AI pass reads the owner's
messages, in order and in parts, each with the end of the assistant's reply it answers, and writes questions only
someone who was in the session could answer, and small tasks the session did that the owner then corrected, each
with the ground truth quoted from the owner and the lines it came from.

Every quote is checked against the transcript: a case whose ground truth is not, piece by piece, in the owner's
messages at its source lines is marked ``verified: false``. The drafts are for a person to read and prune; the
transcript and the drafts stay private (they are the owner's conversation)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import contexts as cx
from .parity import KINDS, Case

PROMPT = """Below are the owner's messages from one long working session with an AI coding assistant, in order \
(part {part} of {parts}). Each is headed by its line number in the transcript; before it, in brackets, is the end of \
the assistant's reply it answered.

Write {questions} questions and {tasks} tasks for a benchmark that tests whether a NEW session, which was not in \
this conversation, knows what this session knew. Spread them over the whole part.

Questions, of these kinds (use each at least once): decision (what was decided, and why), meaning (what the owner \
means by a phrase or term they used), rejected (what was proposed and turned down, and why), preference (a rule or \
preference of the owner's), state (the state of something at a point in the session).
- Each must be answerable only from this conversation, not from general knowledge or by guessing.
- Each must be self-contained (name the thing it asks about) and must not give the answer away.
- The truth is the owner's own words, quoted exactly from the messages (several quotes joined with " … "); never \
paraphrase in the truth. Pick quotes that carry the answer.

Tasks: something the assistant was asked to do in this part that the owner then corrected or redirected (a brief \
for an agent, a design, a name, a plan, a piece of documentation). The question restates the task as a \
self-contained request, without the correction. The truth is the owner's correction, quoted exactly.

Where the answer is a specific word or name, add checks: {{"all": [regex], "none": [regex]}} (case-insensitive).

Output one JSON object per line and nothing else:
{{"id": "short-slug", "kind": "decision|meaning|rejected|preference|state|task", "question": "...", "truth": \
"exact quote … exact quote", "source": "line 123, line 456", "rubric": "what a correct answer must contain", \
"checks": {{}}}}

{messages}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def verified(truth: str, source: str, owner_at: dict[int, str]) -> bool:
    """Every quoted piece of the truth is in the owner's messages on the source lines."""
    lines = [int(x) for x in re.findall(r"\d+", source)]
    said = " ".join(_norm(owner_at[n]) for n in lines if n in owner_at)
    pieces = [p for p in re.split(r"\s*(?:…|\.\.\.)\s*", truth) if p.strip()]
    if not said or not pieces:
        return False
    return all(_norm(p).strip("\"' ") in said for p in pieces)


def parts(turns: list[cx.Turn], n: int, reply_chars: int = 600) -> list[str]:
    """The owner's messages in ``n`` parts of about equal size."""
    blocks = []
    prev = ""
    for t in turns:
        before = f"[...{prev[-reply_chars:]}]\n" if prev else ""
        blocks.append(f"{before}### line {t.line}\n{t.owner}\n")
        prev = "\n".join(t.replies)
    size = sum(len(b) for b in blocks) / max(1, n)
    out, cur, used = [], [], 0
    for b in blocks:
        if cur and len(out) < n - 1 and used + len(b) - size > size - used:   # nearer the size without it
            out.append("\n".join(cur))
            cur, used = [], 0
        cur.append(b)
        used += len(b)
    if cur:
        out.append("\n".join(cur))
    return out


def lines_of(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = line.strip().strip("`")
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("kind") in KINDS and d.get("question") and d.get("truth"):
            rows.append(d)
    return rows


def draft(transcript: Path, runner, n_parts: int = 3, questions: int = 14, tasks: int = 3, say=None) -> tuple[list[dict], float]:
    """Drafted cases (each with ``verified``) and what drafting cost."""
    ts = cx.turns(transcript)
    owner_at = {t.line: t.owner for t in ts}
    out, usd, seen = [], 0.0, set()
    ps = parts(ts, n_parts)
    for i, text in enumerate(ps, 1):
        r = runner.ask("You build benchmark datasets carefully, quoting exactly.",
                       PROMPT.format(part=i, parts=len(ps), questions=questions, tasks=tasks, messages=text))
        usd += r.usd
        if say:
            say(f"part {i}/{len(ps)}: {r.error or 'ok'} (${usd:.2f})")
        for d in lines_of(r.text):
            cid = str(d.get("id") or "case")
            while cid in seen:
                cid += "-2"
            seen.add(cid)
            d["id"] = cid
            Case.of({**d, "checks": d.get("checks") if isinstance(d.get("checks"), dict) else {}})
            d["verified"] = verified(str(d["truth"]), str(d.get("source", "")), owner_at)
            out.append(d)
    return out, usd
