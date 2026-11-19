"""A run's AI usage: tokens, models and dollars, from what Claude Code says when a session ends.

Claude Code's result message (``claude -p --output-format json``, or the last line of ``stream-json``) carries
``total_cost_usd``, ``usage`` (``input_tokens``, ``output_tokens``, ``cache_read_input_tokens``,
``cache_creation_input_tokens``) and ``modelUsage`` (the same, by model, with ``costUSD``). A run collects them from:

- an ``ai`` block's own ``claude -p`` (its result message, which the engine reads in place of plain text);
- a session started by the run's program (``ergostat session``): its ``session.ran`` / ``session.failed`` line, whose
  ``ai`` is this record made by the session helper, so a session inside a ``run:`` program is the run's;
- any line a program prints that is a Claude Code result message (a program that runs ``claude -p --output-format
  json`` and passes its output on).

Dollars Claude Code reported are ``reported``; tokens with no dollars are priced by ``prices.py`` and ``estimated``;
tokens on a model with no price leave the cost unknown (``unpriced``)."""

from __future__ import annotations

import json
import os
import shlex

from . import prices

TOKENS = ("input", "output", "cache_read", "cache_write")
ALL = (*TOKENS, "cache_write_1h")      # (of the cache writes, those kept an hour: priced higher)


def is_result(obj: dict) -> bool:
    """A Claude Code result message (not one of ergostat's output lines)."""
    return (obj.get("type") == "result" and "out" not in obj and "event" not in obj
            and any(k in obj for k in ("total_cost_usd", "usage", "modelUsage", "session_id", "num_turns")))


def tokens_of(usage: dict | None) -> dict:
    u = usage if isinstance(usage, dict) else {}
    def n(*keys):
        return int(sum(float(u.get(k) or 0) for k in keys if isinstance(u.get(k), (int, float))))
    return {"input": n("input_tokens", "inputTokens", "input"), "output": n("output_tokens", "outputTokens", "output"),
            "cache_read": n("cache_read_input_tokens", "cacheReadInputTokens", "cache_read"),
            "cache_write": n("cache_creation_input_tokens", "cacheCreationInputTokens", "cache_write"),
            "cache_write_1h": n("cacheCreationEphemeral1hInputTokens", "cache_write_1h")
            or int(float(((u.get("cache_creation") or {}) if isinstance(u.get("cache_creation"), dict) else {})
                         .get("ephemeral_1h_input_tokens") or 0))}


def part_of_result(d: dict, model: str | None = None) -> dict:
    """One session's usage from its result message: by model when Claude Code says it (``modelUsage``), else whole."""
    by = d.get("modelUsage") if isinstance(d.get("modelUsage"), dict) else {}
    if by:
        toks = {k: 0 for k in ALL}
        models = {}
        for m, u in by.items():
            t = tokens_of(u)
            for k in ALL:
                toks[k] += t[k]
            models[m] = {**t, **({"cost_usd": float(u["costUSD"])} if isinstance(u.get("costUSD"), (int, float)) else {})}
    else:
        toks = tokens_of(d.get("usage"))
        models = {model: dict(toks)} if model else {}
    cost = d.get("total_cost_usd")
    if isinstance(cost, (int, float)):
        return {"cost_usd": float(cost), "how": "reported", "tokens": toks, "models": models,
                "turns": int(d.get("num_turns") or 0)}
    return priced(toks, models, model, int(d.get("num_turns") or 0))


def priced(toks: dict, models: dict, model: str | None, turns: int = 0) -> dict:
    """Tokens with no dollars said: estimated from the price table, by model where known."""
    total, unpriced = 0.0, False
    if models:
        for m, t in models.items():
            c = t.get("cost_usd") if isinstance(t.get("cost_usd"), (int, float)) else prices.estimate(m, t)
            if c is None:
                unpriced = unpriced or any(t.get(k) for k in TOKENS)
            else:
                total += c
    else:
        c = prices.estimate(model, toks)
        if c is None:
            unpriced = any(toks.values())
        else:
            total = c
    return {"cost_usd": None if unpriced and not total else total, "how": "unpriced" if unpriced else "estimated",
            "tokens": toks, "models": models, "turns": turns}


class Usage:
    """What a run's sessions used, added up as they report."""

    def __init__(self, model: str | None = None):
        self.model = model                    # the model the block asked for: for tokens that name none
        self.parts: list[dict] = []

    def add_result(self, d: dict, model: str | None = None) -> None:
        self.parts.append(part_of_result(d, model or self.model))

    def add_session(self, data: dict) -> None:
        """A ``session.ran`` / ``session.failed`` line's data: its ``ai`` record, or (an older helper) its cost alone."""
        if not isinstance(data, dict):
            return
        a = data.get("ai")
        if isinstance(a, dict):
            toks = {k: int((a.get("tokens") or {}).get(k) or 0) for k in ALL}
            models = a.get("models") if isinstance(a.get("models"), dict) else {}
            how = a.get("cost") if a.get("cost") in ("reported", "estimated", "unpriced", "partly estimated") else "reported"
            cost = a.get("cost_usd")
            if cost is None and any(toks.values()):
                self.parts.append(priced(toks, models, a.get("model") or self.model, int(a.get("turns") or 0)))
                return
            self.parts.append({"cost_usd": float(cost) if isinstance(cost, (int, float)) else None,
                               "how": "estimated" if how == "partly estimated" else how, "tokens": toks, "models": models,
                               "turns": int(a.get("turns") or 0), **({"mixed": True} if how == "partly estimated" else {})})
        elif isinstance(data.get("cost_usd"), (int, float)):
            self.parts.append({"cost_usd": float(data["cost_usd"]), "how": "reported", "tokens": {k: 0 for k in ALL},
                               "models": {}, "turns": int(data.get("turns") or 0)})

    def record(self) -> dict | None:
        """What is recorded on the run's end event (``ai``), or None when it used no AI that said so."""
        if not self.parts:
            return None
        toks = {k: sum(int(p["tokens"].get(k) or 0) for p in self.parts) for k in ALL}
        models: dict[str, dict] = {}
        for p in self.parts:
            for m, t in (p.get("models") or {}).items():
                acc = models.setdefault(m, {k: 0 for k in ALL})
                for k in ALL:
                    acc[k] += int(t.get(k) or 0)
                if isinstance(t.get("cost_usd"), (int, float)):
                    acc["cost_usd"] = round(acc.get("cost_usd", 0.0) + float(t["cost_usd"]), 6)
        hows = {p["how"] for p in self.parts}
        if any(p.get("mixed") for p in self.parts):
            hows.add("reported")
        known = [p["cost_usd"] for p in self.parts if p["cost_usd"] is not None]
        how = ("unpriced" if hows == {"unpriced"} else hows.pop() if len(hows) == 1
               else "partly estimated")
        main = max(models, key=lambda m: sum(models[m][k] for k in TOKENS)) if models else self.model
        return {"cost_usd": round(sum(known), 6) if known else None, "cost": how,
                "tokens": {**toks, "total": sum(toks[k] for k in TOKENS)}, "model": main,
                **({"models": models} if models else {}), "sessions": len(self.parts),
                "turns": sum(int(p.get("turns") or 0) for p in self.parts),
                **({"unpriced": True} if "unpriced" in {p["how"] for p in self.parts} and how != "unpriced" else {})}


def expand(usage: Usage, got: list[str]) -> list[str]:
    """A run's lines as they arrive, with what they say about AI usage taken: a Claude Code result message is counted
    and replaced by its text (its lines, as ``claude -p`` would have printed them as text); a session's end
    (``session.ran``, ``session.failed``) is counted and passed on."""
    out: list[str] = []
    for raw in got:
        s = raw.strip()
        if not s.startswith("{") or ('"result"' not in s and '"session.' not in s):
            out.append(raw)
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            out.append(raw)
            continue
        if isinstance(obj, dict) and is_result(obj):
            usage.add_result(obj)
            text = obj.get("result")
            out += [x + "\n" for x in text.splitlines()] if isinstance(text, str) else []
            continue
        if isinstance(obj, dict) and obj.get("event") in ("session.ran", "session.failed"):
            usage.add_session(obj.get("data"))
        out.append(raw)
    return out


def is_claude(cmd: str) -> bool:
    """Whether a command runs Claude Code itself (``claude -p``), so it can be asked for its result as JSON."""
    try:
        first = shlex.split(cmd)[0]
    except (ValueError, IndexError):
        return False
    return os.path.basename(first) == "claude"
