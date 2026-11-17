"""The parts made of what was said (SPEC §12j): ``owner-words`` (the owner's messages, verbatim, most relevant
first), ``session`` (a session's turns: a fork of all of it, its last N, or those matching a pattern) and the
sessions in an item's history (their key turns).

What the owner said is read from transcript files (``from:``) or from the record: the owner's messages
(``ergostat.message.received``), and the user's turns of every Claude Code transcript the record holds whose session
no block started (a block's session is given ergostat's prompt, not the owner's words). A message the record keeps
only the head of is read whole from its file."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..bench.contexts import NOT_OWNER, Turn, turns
from .fit import For, content_words, cut, when


@dataclass
class Said:
    text: str
    where: str
    at: float | str | None = None
    order: float = 0.0                       # newest last
    words: set = field(default_factory=set)


# ---- the owner's words


def _paths(ctx: For, raw) -> list[Path]:
    out = []
    for x in [raw] if isinstance(raw, str) else raw:
        p = Path(x).expanduser()
        p = p if p.is_absolute() else ctx.spec.root / p
        out += sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    return out


def from_files(ctx: For, raw) -> list[Said]:
    out = []
    for path in _paths(ctx, raw):
        if not path.is_file():
            continue
        for i, t in enumerate(turns(path)):
            out.append(Said(t.owner, f"{path.stem[:8]}, line {t.line}", t.at[:16].replace("T", " "), i))
    return out


class _Lines:
    """Lines of a project's transcript files, read once each: the whole of a text the record keeps the head of."""

    def __init__(self, ctx: For):
        self.ctx, self.files = ctx, {}

    def text(self, m: dict) -> str:
        if not m.get("truncated") or not isinstance(m.get("full"), dict):
            return str(m.get("text") or "")
        f, n = m["full"].get("file"), m["full"].get("line")
        if f not in self.files:
            path = (self.ctx.p.repo / str(f)).resolve()
            try:
                self.files[f] = path.read_text(encoding="utf-8", errors="replace").splitlines() \
                    if path.is_relative_to(self.ctx.p.repo.resolve()) or path.is_relative_to(self.ctx.p.dir.resolve()) else []
            except OSError:
                self.files[f] = []
        lines = self.files[f]
        if isinstance(n, int) and 0 < n <= len(lines):
            try:
                content = (json.loads(lines[n - 1]).get("message") or {}).get("content")
            except ValueError:
                content = None
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        return str(m.get("text") or "")


def block_sessions(ctx: For) -> set[str]:
    """Session items a block started (their first event is from a block): their user turns are ergostat's prompts."""
    names = set(ctx.spec.blocks)
    out = set()
    for e in ctx.p.events.query(n=None, type="session.started"):
        if e.get("source") in names or (e.get("data") or {}).get("role") in names:
            out.add(e["item"])
    return out


def from_record(ctx: For) -> list[Said]:
    out = []
    for e in ctx.p.events.query(n=None, type="ergostat.message.received"):
        d = e.get("data") or {}
        if d.get("text"):
            out.append(Said(str(d["text"]), f"message {e['item'].split('/')[-1]}", e["time"], e["time"]))
    skip = block_sessions(ctx)
    lines = _Lines(ctx)
    for e in ctx.p.events.query(n=None, type="claude.message"):
        if e["item"] in skip:
            continue
        for m in (e.get("data") or {}).get("messages") or []:
            if m.get("role") != "user" or m.get("meta"):
                continue
            text = lines.text(m).strip()
            if not text or text.startswith(NOT_OWNER) or "<task-notification>" in text[:300]:
                continue
            out.append(Said(text, f"{e['item']}, line {m.get('line')}", e["time"], e["time"]))
    return out


def owner_words(ctx: For, params: dict, budget: int) -> str:
    src = params.get("from", "record")
    said = from_record(ctx) if src == "record" else from_files(ctx, src)
    topic = params.get("topic") or []
    topic = [topic] if isinstance(topic, str) else topic
    terms = content_words(" ".join(ctx.fill(t) for t in topic))
    if params.get("item", True):
        terms += [t for t in ctx.terms() if t not in terms]
        terms += [w for r in ctx.parts_of_item() for w in content_words(r.split(".", 1)[1]) if w not in terms]
    mention = ctx.item_id
    for s in said:
        s.words = set(content_words(s.text))
    scored = []
    for s in said:
        score = sum(1 for t in terms if t in s.words) + (3 if mention and mention in s.text else 0)
        scored.append((score, s))
    keep_rest = params.get("rest", False) or not terms
    chosen = [(n, s) for n, s in scored if n > 0 or keep_rest]
    chosen.sort(key=lambda x: (-x[0], -x[1].order))
    about = f" on {', '.join(terms[:8])}" if terms else ""
    order = "most relevant first, then the newest" if terms else "the newest first"
    head = f"## The owner's words{about}\n\nWhat the owner said, verbatim, {order}.\n\n"
    if not said:
        return head + "Nothing said yet.\n"
    if not chosen:
        return head + f"Nothing the owner said matches ({len(said)} messages in all).\n"
    used, parts, left = len(head), [], 0
    for _, s in chosen:
        lead = f"**The owner** ({s.where}{', ' + str(s.at) if isinstance(s.at, str) else (', ' + when(s.at) if s.at else '')}):\n\n"
        body = s.text.strip() + "\n"
        room = budget - used - len(lead) - 2 - 120          # (room kept for saying how many did not fit)
        if room < len(body):
            if room < 400 or parts and room < len(body) // 2:
                left += 1
                continue
            body = cut(body, room)
        parts.append(lead + body)
        used += len(lead) + len(body) + 2
    text = head + "\n".join(parts)
    if left:
        text += f"\n({left} more of the owner's messages{about} did not fit.)\n"
    return text


# ---- a session's turns


def session_turns(ctx: For, item_id: str) -> list[Turn]:
    """A session item's turns, from its folded conversation: each user message and what the assistant said and did
    until the next."""
    from ..spec import items as its
    it = its.one(ctx.p.events, ctx.spec, item_id)
    if it is None:
        return []
    lines = _Lines(ctx)
    rows = []
    for m in it.fields.get("messages") or []:
        if isinstance(m, dict):
            rows.append((m.get("line") or 0, "said", m))
    for c in it.fields.get("tool_calls") or []:
        if isinstance(c, dict):
            rows.append((c.get("line") or 0, "tool", c))
    rows.sort(key=lambda r: r[0])
    out: list[Turn] = []
    for line, what, m in rows:
        if what == "said" and m.get("role") == "user" and not m.get("meta"):
            out.append(Turn(int(line), "", lines.text(m).strip()))
        elif not out:
            continue
        elif what == "said" and m.get("role") == "assistant":
            out[-1].replies.append(lines.text(m).strip())
        elif what == "tool":
            out[-1].tools.append(str(m.get("name")))
    return out


def render_turn(t: Turn, who: str = "the owner", replies: int | None = None) -> str:
    tools = ""
    if t.tools:
        counts: dict[str, int] = {}
        for x in t.tools:
            counts[x] = counts.get(x, 0) + 1
        tools = "[tools: " + ", ".join(f"{k}×{v}" if v > 1 else k for k, v in counts.items()) + "]\n"
    said = t.replies if replies is None else t.replies[-replies:]
    at = f", {t.at[:16].replace('T', ' ')}" if t.at else ""
    return f"--- {who}, line {t.line}{at} ---\n{t.owner}\n--- the assistant ---\n{tools}" + "\n\n".join(said) + "\n"


def linked_sessions(ctx: For) -> list[str]:
    """The sessions that worked on the item, oldest first: session items whose fields name it, the sessions its claims
    were made in, and the sessions of the recipe uses about it."""
    if ctx.item is None:
        return []
    iid = ctx.item_id
    out: list[str] = []
    for e in ctx.p.events.query(n=None, type="session.started"):
        d = e.get("data") or {}
        if iid in (d.get("item"), *(d.get("items") or [])) and e["item"] not in out:
            out.append(e["item"])
    from ..claims import record
    for c in sorted(record.stored(ctx.p).values(), key=lambda c: c.get("time", 0)):
        if (c.get("about") or {}).get("item") == iid and c.get("session") and c["session"] not in out:
            out.append(c["session"])
    for e in ctx.p.events.query(n=None, type="ergostat.context.used"):
        d = e.get("data") or {}
        if d.get("item") == iid and d.get("session") and d["session"] not in out:
            out.append(d["session"])
    return out


def session(ctx: For, params: dict, budget: int) -> str:
    of = ctx.fill(params.get("of") or "item")
    if of == "item":
        ss = linked_sessions(ctx)
        if not ss:
            return "## A session\n\nNo session has worked on " + (f"{ctx.item_id} yet.\n" if ctx.item else
                                                                  "an item: this run was given none.\n")
        of = ss[-1]
    path = Path(of).expanduser()
    path = path if path.is_absolute() else ctx.spec.root / path
    if of.endswith(".jsonl") or path.is_file():
        if not path.is_file():
            return f"## A session\n\nNo transcript at {of}.\n"
        ts, name = turns(path), path.stem
    else:
        ts, name = session_turns(ctx, of), of
    total = len(ts)
    if params.get("match"):
        rx = re.compile(str(params["match"]), re.I)
        ts = [t for t in ts if rx.search(t.owner) or any(rx.search(r) for r in t.replies)]
    if params.get("last"):
        ts = ts[-int(params["last"]):]
    kept, used = [], 0
    for t in reversed(ts):
        r = render_turn(t)
        if used + len(r) > budget - 200:
            break
        kept.append(r)
        used += len(r)
    which = (f"the turns matching /{params['match']}/" if params.get("match") else "its turns") + \
        (f", the last {params['last']}" if params.get("last") else "")
    head = (f"## Session {name}\n\n{which[0].upper() + which[1:]}: {len(kept)} of {total}, in order (the tools' output "
            f"left out).\n\n")
    if len(kept) < len(ts):
        head += f"({len(ts) - len(kept)} earlier turns did not fit.)\n\n"
    return head + "\n".join(reversed(kept))


def key_turns(ctx: For, sid: str, n: int, budget: int) -> str:
    """A session's key turns: what it was asked, and what it said last in each, the last ``n``."""
    ts = session_turns(ctx, sid)[-n:]
    if not ts:
        return f"### {sid}\n\nNo conversation recorded.\n"
    kept, used = [], 0
    for t in reversed(ts):
        last = [cut(t.replies[-1], 1500)] if t.replies else []
        r = render_turn(Turn(t.line, t.at, cut(t.owner, 1200), last, t.tools), who="asked")
        if used + len(r) > budget:
            break
        kept.append(r)
        used += len(r)
    more = "(earlier turns did not fit)\n\n" if len(kept) < len(ts) else ""
    return f"### {sid}\n\n" + more + "\n".join(reversed(kept)) + "\n"
