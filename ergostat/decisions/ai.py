"""The AI extractor: a model reads the owner's turns, with the assistant's turns around them, a batch at a time,
and answers with the decisions and corrections it finds, each resting on the owner's words quoted exactly.

What it says is checked, not trusted: every quote must be found, whitespace aside, in the owner's turn at the
line it names (or in another owner turn of the same batch, whose line it then takes); a quote not found is
dropped, and a finding with no quote left is dropped and counted. The batch's instructions are the block's
prompt when it runs as an ``ai`` block (so the prompt is the model's to improve), else ``prompt.md``; the
answer's form is always the one below. It stops before the cost cap would be passed, and says what it spent."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .transcript import Turn

PROMPT = Path(__file__).with_name("prompt.md")
BATCH_CHARS = 24000         # what one call reads, at most (about 6,000 tokens)
OWNER_CHARS = 8000          # one owner turn, at most (a pasted document is cut: quotes come from what is shown)
EARLIER = 80                # earlier findings listed in each batch, so a repeat or a supersession can name them
SYSTEM = "You extract a project owner's decisions and corrections from a conversation log. Answer only in JSON lines."
ANSWER = """

---
Answer with JSON lines only, one per finding, and nothing else (no prose, no code fences). Nothing found: no lines.
{"decision": {"decision": "one sentence: what was decided", "words": [{"line": N, "text": "the owner's words, copied exactly from the owner's turn at line N"}], "reasons": ["why, as the owner or the exchange gave it"], "alternatives": [{"option": "what was rejected", "why": "why not"}], "scope": ["the parts or topics it applies to"], "supersedes": ["the slug of an earlier decision it replaces, from the list above"], "confidence": 0.0}}
{"correction": {"correction": "one sentence: what to do differently from now on", "words": [{"line": N, "text": "exact quote"}], "corrects": "the behaviour or result it corrects", "kind_of_work": ["the kinds of work it applies to: ui, docs, git, testing, modelling, review, reporting, planning, ..."], "scope": ["parts or topics"], "repeats": "the slug of an earlier correction it gives again, from the list above", "confidence": 0.0}}
"""  # noqa: E501


@dataclass
class Spent:
    calls: int = 0
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    dropped: int = 0                 # findings with no quote found in the owner's words
    failed: int = 0                  # calls that gave nothing readable
    stopped: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"calls": self.calls, "cost_usd": round(self.cost_usd, 4), "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out, "dropped_unquoted": self.dropped, "failed_calls": self.failed,
                **({"stopped": self.stopped} if self.stopped else {})}


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(s.split())


def batches(exs: list[tuple[Turn, str, str]], size: int = BATCH_CHARS):
    cur, n = [], 0
    for ex in exs:
        k = min(len(ex[0].text), OWNER_CHARS) + len(ex[1]) + len(ex[2]) + 200
        if cur and n + k > size:
            yield cur
            cur, n = [], 0
        cur.append(ex)
        n += k
    if cur:
        yield cur


def render(batch, earlier: dict[str, list[tuple[str, str]]]) -> str:
    out = []
    for kind in ("decision", "correction"):
        xs = earlier.get(kind) or []
        if xs:
            out.append(f"Earlier {kind}s (slug: sentence):")
            out += [f"- {slug}: {text}" for slug, text in xs[-EARLIER:]]
            out.append("")
    for t, before, after in batch:
        text = t.text if len(t.text) <= OWNER_CHARS else t.text[:OWNER_CHARS] + "\n[... the rest of this turn is cut]"
        when = t.where().get("time")
        out.append(f"=== the owner's turn at line {t.line}" + (f" ({when})" if when else "") + " ===")
        if before:
            out.append(f"[the assistant, just before]\n{before}")
        out.append(f"[the owner, line {t.line}]\n{text}")
        if after:
            out.append(f"[the assistant, just after]\n{after}")
        out.append("")
    return "\n".join(out)


def command(model: str | None, budget: float | None, system: str | None = None) -> list[str]:
    cmd = shlex.split(os.environ.get("ERGOSTAT_AI", "claude -p"))
    if model:
        cmd += ["--model", model]
    if Path(cmd[0]).name == "claude":
        cmd += ["--output-format", "json", "--tools", "", "--no-session-persistence", "--system-prompt", system or SYSTEM]
        if budget:
            cmd += ["--max-budget-usd", f"{budget:.2f}"]
    return cmd


def call(prompt: str, model: str | None, budget: float | None, spent: Spent, timeout: float = 600,
         system: str | None = None) -> str:
    """One call: what it answered, and its cost added to ``spent`` (``system``: its system prompt, else the extractor's;
    the intent judge's is its own, SPEC §12i)."""
    try:
        r = subprocess.run(command(model, budget, system), input=prompt, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        spent.failed += 1
        spent.notes.append(f"call failed: {type(e).__name__}: {e}"[:300])
        return ""
    spent.calls += 1
    out = r.stdout
    try:
        d = json.loads(out)
    except ValueError:
        return out                                    # a plain command: its output is the answer
    if not isinstance(d, dict):
        return out
    spent.cost_usd += float(d.get("total_cost_usd") or 0)
    u = d.get("usage") or {}
    spent.tokens_in += sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    spent.tokens_out += int(u.get("output_tokens") or 0)
    if d.get("is_error"):
        spent.failed += 1
        spent.notes.append(f"error: {str(d.get('result') or d.get('subtype'))[:300]}")
    return str(d.get("result") or "")


def answers(text: str) -> list[tuple[str, dict]]:
    out = []
    for raw in text.splitlines():
        raw = raw.strip().rstrip(",")
        if not raw.startswith("{"):
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        for kind in ("decision", "correction"):
            if isinstance(obj, dict) and isinstance(obj.get(kind), dict):
                out.append((kind, obj[kind]))
    return out


def verified(kind: str, d: dict, batch, spent: Spent) -> dict | None:
    """The finding with each quote found in the owner's words (and its line, session and time from there), or None."""
    owners = {t.line: t for t, _, _ in batch}
    flat = {t.line: norm(t.text) for t, _, _ in batch}
    words = []
    for w in d.get("words") or []:
        if isinstance(w, str):
            w = {"text": w}
        if not isinstance(w, dict) or not isinstance(w.get("text"), str) or len(norm(w["text"])) < 3:
            continue
        q = norm(w["text"]).strip('"').strip()
        try:
            line = int(w.get("line"))
        except (TypeError, ValueError):
            line = None
        at = line if line in flat and q in flat[line] else next((n for n, s in flat.items() if q in s), None)
        if at is None:
            continue
        words.append({"text": q, **owners[at].where()})
    if not words:
        spent.dropped += 1
        return None
    d = {**d, "words": words}
    if kind == "correction":
        d["source"] = {"type": "transcript", **words[0]}
        d["source"].pop("text", None)
    return d


def extract(exs: list[tuple[Turn, str, str]], model: str | None, cap: float | None, instructions: str | None = None,
            earlier: dict | None = None, on_found=None) -> Spent:
    """Run over the exchanges a batch at a time; each finding, checked, goes to ``on_found(kind, data)``."""
    spent = Spent()
    head = (instructions or PROMPT.read_text(encoding="utf-8")).rstrip()
    earlier = earlier if earlier is not None else {"decision": [], "correction": []}
    for batch in batches(exs):
        if cap is not None:
            per = spent.cost_usd / spent.calls if spent.calls else 0.0
            if spent.cost_usd + per > cap:
                spent.stopped = f"the cost cap (${cap:.2f}) would be passed: stopped at line {batch[0][0].line}"
                break
        left = None if cap is None else max(0.05, min(2.0, cap - spent.cost_usd))
        text = call(head + "\n\n" + render(batch, earlier) + ANSWER, model, left, spent)
        for kind, d in answers(text):
            got = verified(kind, d, batch, spent)
            if got is None:
                continue
            got["extractor"] = {"name": "ai", **({"model": model} if model else {})}
            slug = on_found(kind, got) if on_found else None
            if slug:
                earlier.setdefault(kind, []).append((slug, str(got.get(kind) or "")[:160]))
    return spent


def strip_block_footer(text: str) -> str:
    """An ``ai`` block's prompt as the engine gave it (the prompt, its footer, the inputs): the prompt alone."""
    from ..spec.engine import AI_FOOTER
    i = text.find(AI_FOOTER.strip()[:40])
    head = text[:i] if i >= 0 else text
    return re.sub(r"\n-{3,}\s*$", "", head.rstrip()).rstrip()
