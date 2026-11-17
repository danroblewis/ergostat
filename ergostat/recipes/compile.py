"""Reading ``contexts:`` (SPEC §12j), and a block's ``context:`` and ``review:``, into the spec, every mistake said with
where it was written. Called by the spec compiler (``spec/compile.py``) with itself, for its ``named``, ``keys`` and
``err``."""

from __future__ import annotations

import re

from ..decisions.context import budget_of
from ..durations import DurationError, parse_duration
from .ir import DEFAULT_BUDGET, PARTS, RESERVED, Part, Recipe

RECIPE_KEYS = {"version", "description", "budget", "parts", "outcome"}
PICKS = ("oldest", "newest")
REVIEW_KEYS = {"when", "by", "depth"}
WHEN = re.compile(r"^\s*([A-Za-z0-9_.@:-]+)\s*(<=|>=|<|>|==|!=)\s*(-?[0-9.]+)\s*$")
OWN_TRUST = ("contradicted", "contradictions", "verified", "unchecked", "claims")   # short for the block's own trust


def contexts(c, spec) -> None:
    for name, m, what in c.named("contexts"):
        what = f"context {name}"
        c.keys(m, RECIPE_KEYS, what)
        if name in RESERVED:
            c.err(f"{what}: {name} is a built-in projection (ergostat context {name}); name the recipe something else",
                  m.where, "reserved-name")
            continue
        v = m.get("version", 1)
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            c.err(f"{what}.version: a whole number, 1 or more (raise it when the recipe changes)", m.at("version"),
                  "bad-number")
            v = 1
        total = None
        if m.get("budget") is not None:
            try:
                total = budget_of(m["budget"])
            except ValueError:
                c.err(f"{what}.budget: characters (24000) or tokens (6000t)", m.at("budget"), "bad-budget")
        r = Recipe(name, v, [], c.text(m, "description"), total, {}, m.where)
        raw = m.get("parts")
        if not isinstance(raw, list) or not raw:
            c.err(f"{what}.parts: a list of parts, each one of {', '.join(PARTS)} (- decisions: {{scope: ui}})",
                  m.at("parts") or m.where, "missing-key")
            continue
        for i, x in enumerate(raw):
            p = part(c, x, f"{what}.parts[{i}]", m.at("parts"), spec)
            if p:
                r.parts.append(p)
        out = m.get("outcome")
        if out is not None:
            if not isinstance(out, dict) or set(out) - {"success", "failure"}:
                c.err(f"{what}.outcome: success: and failure:, each a list of the states of the item it works on",
                      m.at("outcome"), "bad-outcome")
            else:
                r.outcome = {k: [str(s) for s in (out[k] if isinstance(out[k], list) else [out[k]])] for k in out}
        spec.contexts[name] = r


def part(c, x, what: str, w, spec) -> Part | None:
    if isinstance(x, str):
        kind, params = x, {}
    elif isinstance(x, dict) and len(x) == 1 and isinstance(next(iter(x.values())), dict | type(None)):
        kind, params = next(iter(x.items()))
        params = dict(params or {})
    else:
        c.err(f"{what}: a part's kind (- docs), or its kind with its keys (- decisions: {{scope: ui, budget: 1500t}})",
              getattr(x, "where", None) or w, "bad-part")
        return None
    w = getattr(x, "where", None) or w
    if kind not in PARTS:
        c.err(f"{what}: {kind!r} is not a part: one of {', '.join(PARTS)}" + c.suggest(str(kind), PARTS), w, "bad-part")
        return None
    allowed, _ = PARTS[kind]
    for k in params:
        if k not in allowed | {"budget"}:
            c.err(f"{what}: {kind} has no key {k!r} (its keys: {', '.join(sorted(allowed | {'budget'}))})", w, "unknown-key")
    budget = DEFAULT_BUDGET[kind]
    if params.get("budget") is not None:
        try:
            budget = budget_of(params.pop("budget"))
        except ValueError:
            c.err(f"{what}.budget: characters (6000) or tokens (1500t)", w, "bad-budget")
    else:
        params.pop("budget", None)

    def bad(key: str, why: str) -> None:
        c.err(f"{what}.{key}: {why}", w, "bad-part")
        params.pop(key, None)

    for k in ("proposed", "item", "rest", "sessions", "running", "findings", "goals"):
        if k in params and not isinstance(params[k], bool):
            bad(k, "true or false")
    for k in ("events", "turns", "commits", "last"):
        if k in params and (isinstance(params[k], bool) or not isinstance(params[k], int) or params[k] < 1):
            bad(k, "a whole number, 1 or more")
    for k in ("scope", "kind", "repo", "branch", "of"):
        if k in params and not isinstance(params[k], str):
            bad(k, "text")
    if "topic" in params and not (isinstance(params["topic"], str) or
                                  isinstance(params["topic"], list) and all(isinstance(t, str) for t in params["topic"])):
        bad("topic", "words, or a list of them")
    if "since" in params:
        try:
            params["since"] = parse_duration(params["since"], f"{what}.since")
        except DurationError as e:
            bad("since", str(e))
    if "match" in params:
        try:
            re.compile(str(params["match"]))
        except re.error as e:
            bad("match", f"a pattern over a turn's text ({e})")
    if kind == "owner-words" and "from" in params:
        f = params["from"]
        if not (f == "record" or isinstance(f, str) or isinstance(f, list) and all(isinstance(x, str) for x in f)):
            bad("from", "record (the default: the owner's turns the record holds), or transcript files or folders")
    if kind == "docs":
        files = params.get("files")
        if isinstance(files, str):
            files = params["files"] = [files]
        if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
            bad("files", "the files to include, a list of paths or globs from the model's folder")
        else:
            for f in files:
                if f.startswith("/") or ".." in f.split("/"):
                    bad("files", f"{f}: a path inside the model's folder, written from it")
                    break
                if not any(spec.root.glob(f)) and not (spec.root / f).exists():
                    c.err(f"{what}.files: {f} is not a file here", w, "docs-missing")
    if kind == "model" and "parts" in params:
        ps = params["parts"]
        ps = params["parts"] = [ps] if isinstance(ps, str) else ps
        if not isinstance(ps, list) or not all(isinstance(r, str) and "." in r for r in ps):
            bad("parts", "parts of the model, as references (stock.x, flow.y, goal.z) or system.NAME")
    if kind == "state" and "repo" in params:
        r = params["repo"]
        if r.startswith("/") or ".." in r.split("/"):
            bad("repo", "a folder inside the model's, written from it")
    return Part(str(kind), budget, params, w)


def blocks(c, spec) -> None:
    """Each block's ``context:`` (an ``ai`` block: the recipe its sessions start from) and ``review:`` (any machine
    block: who reviews its work, by a measure)."""
    from ..spec.ir import Ref, is_measure
    for b in spec.blocks.values():
        raw = b.params.pop("context", None)
        what = f"block {b.name}.context"
        if raw is not None:
            if isinstance(raw, str):
                raw = {"recipe": raw}
            if not isinstance(raw, dict) or set(raw) - {"recipe", "item"} or not isinstance(raw.get("recipe"), str):
                c.err(f"{what}: a recipe's name (context: developer), or {{recipe: developer, item: ...}}", b.where,
                      "bad-context")
            elif raw["recipe"] not in spec.contexts:
                c.err(f"{what}: {raw['recipe']!r} is not a recipe under contexts:" + c.suggest(raw["recipe"], spec.contexts),
                      b.where, "unknown-ref", f"context.{raw['recipe']}")
            else:
                it = raw.get("item")
                if it is not None and not (isinstance(it, str) or isinstance(it, dict) and isinstance(it.get("kind"), str)
                                           and set(it) <= {"kind", "state", "pick"} and it.get("pick", "oldest") in PICKS):
                    c.err(f"{what}.item: the item its run works on when its command names none: an id ({{item}} and "
                          f"{{run}} filled in), or {{kind: K, state: [S, ...], pick: oldest|newest}}", b.where, "bad-context")
                elif isinstance(it, dict) and it["kind"] not in spec.items:
                    c.err(f"{what}.item.kind: {it['kind']!r} is not a kind of item" + c.suggest(it["kind"], spec.items),
                          b.where, "unknown-ref")
                else:
                    if isinstance(it, dict) and isinstance(it.get("state"), str):
                        it = {**it, "state": [it["state"]]}
                    b.params["context"] = {"recipe": raw["recipe"], "item": it}
        raw = b.params.pop("review", None)
        if raw is None:
            continue
        what = f"block {b.name}.review"
        rules = raw if isinstance(raw, list) else [raw]
        out = []
        for i, r in enumerate(rules):
            w = f"{what}[{i}]" if isinstance(raw, list) else what
            if not isinstance(r, dict) or set(r) - REVIEW_KEYS:
                c.err(f"{w}: a rule {{when: \"contradicted > 0.2\", by: reviewer, depth: deep}} (keys: when, by, depth)",
                      b.where, "bad-review")
                continue
            by = r.get("by")
            if by in (None, "none", False):
                by = None
            elif not isinstance(by, str) or by not in spec.blocks or not spec.blocks[by].machine:
                c.err(f"{w}.by: the machine block that reviews {b.name}'s work, or none" +
                      (c.suggest(str(by), spec.blocks) if isinstance(by, str) else ""), b.where, "unknown-ref",
                      f"block.{by}")
                continue
            elif by == b.name:
                c.err(f"{w}.by: a block does not review its own work", b.where, "bad-review")
                continue
            when = r.get("when")
            cond = None
            if when is not None:
                mm = WHEN.match(str(when))
                if not mm:
                    c.err(f"{w}.when: a measure, a comparison and a number (\"contradicted > 0.2\", "
                          f"\"ergostat.trust.contradicted@developer >= 0.1\")", b.where, "bad-review")
                    continue
                name, op, num = mm.groups()
                if name in OWN_TRUST:
                    name = f"ergostat.trust.{name}@{b.name}"
                if not is_measure(name):
                    c.err(f"{w}.when: {name} is not a built-in measure (ergostat.trust.*, ergostat.context.*, "
                          f"ergostat.model.*)", b.where, "bad-measure")
                    continue
                try:
                    cond = (name, op, float(num))
                except ValueError:
                    c.err(f"{w}.when: {num} is not a number", b.where, "bad-review")
                    continue
            out.append({"when": cond, "by": by, "depth": str(r.get("depth") or ("review" if by else "none")),
                        "text": str(when) if when is not None else None})
        if out:
            b.params["review"] = out
            for by in sorted({r["by"] for r in out if r["by"]}):     # drawn: the block commands its reviewer
                b.outputs.setdefault(f"review-{by}", [Ref("block", by)])
