"""Reading ``actions:``, an ``ai`` block's ``workdir:``, ``workspace:``, ``read:``, ``tools:`` and ``actions:``, and a
``program`` block's ``workspace:`` and ``actions:`` (SPEC §12k) into the spec, every mistake said with where it was
written. Called by the spec compiler with itself."""

from __future__ import annotations

import math
import re
import string

from ..spec.ir import GATES, NAME, Action
from .risk import HIGHEST, THRESHOLD

ACTION_KEYS = {"run", "gate", "class", "args", "timeout", "wait", "in", "description", "fenced", "risk"}
BUILT_IN = ("item", "branch", "workdir", "block", "run")      # what every action's template may name
TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\(.+\))?$")         # Read, Edit, Bash(python3:*)
SANDBOX_KEYS = ("workdir", "workspace", "read", "tools", "actions")


def actions(c, spec) -> None:
    for name, m, what in c.named("actions"):
        c.keys(m, ACTION_KEYS, what)
        if not m.get("run"):
            c.err(f"{what}: run: the command it runs, a template ({{branch}}, {{item}}, and its args: filled in, quoted)",
                  m.where, "missing-key")
            continue
        gate = str(m.get("gate") or "approve")
        if gate not in GATES:
            c.err(f"{what}.gate: auto (run at once), approve (held until the owner approves) or deny (never run)",
                  m.at("gate"), "bad-value")
            gate = "approve"
        args = m.get("args") or {}
        if not isinstance(args, dict):
            c.err(f"{what}.args: a map of each argument's name to what it is (title: the pull request's title)",
                  m.at("args"), "not-a-map")
            args = {}
        for a in args:
            if not isinstance(a, str) or not NAME.match(a.replace("_", "-")):
                c.err(f"{what}.args: {a!r}: an argument's name is lowercase letters, digits, - and _", m.at("args"), "bad-name")
            elif a in BUILT_IN:
                c.err(f"{what}.args.{a}: {{{a}}} is ergostat's own (the session's), not the session's to say: name it "
                      f"something else", m.at("args"), "reserved-name")
        try:
            used = {f for _, f, _, _ in string.Formatter().parse(str(m["run"])) if f is not None}
        except ValueError as e:
            c.err(f"{what}.run: a command template ({e}); write a literal brace as {{{{ or }}}}", m.at("run"), "bad-template")
            used = set()
        for f in sorted(used - set(args) - set(BUILT_IN)):
            c.err(f"{what}.run: {{{f}}} is neither one of its args: nor ergostat's own ({', '.join(BUILT_IN)})",
                  m.at("run"), "unknown-ref")
        cls = str(m.get("class") or name)
        if not NAME.match(cls):
            c.err(f"{what}.class: a name (lowercase letters, digits and -): the class it is counted in", m.at("class"),
                  "bad-name")
            cls = name
        where, fenced = m.get("in"), m.get("fenced", True)
        if not isinstance(fenced, bool):
            c.err(f"{what}.fenced: true (the default: not run once a later lease is taken on its item, or its own "
                  f"expired) or false (run once approved, whatever became of that lease)", m.at("fenced"), "bad-value")
            fenced = True
        spec.actions[name] = Action(name, str(m["run"]), gate, cls, {str(k): str(v) for k, v in args.items()},
                                    c.duration(m, "timeout", what, 120.0), c.duration(m, "wait", what, 300.0),
                                    str(where) if where else None, c.text(m, "description"), m.where, fenced,
                                    *risk(c, m, what))


def risk(c, m, what: str) -> tuple[int | None, float]:
    """``risk: {severity: 1..5, threshold: 1 < T ≤ 50}`` (SPEC §12k, ``risk.py``): a floor and a ceiling on each."""
    r = m.get("risk")
    if r is None:
        return None, THRESHOLD
    if not isinstance(r, dict):
        c.err(f"{what}.risk: a map, {{severity: 1 to 5, threshold: above 1, at most 50 (default 8)}}", m.at("risk"),
              "not-a-map")
        return None, THRESHOLD
    c.keys(r, {"severity", "threshold"}, f"{what}.risk")
    s, t = r.get("severity"), r.get("threshold", THRESHOLD)
    if isinstance(s, bool) or not isinstance(s, int) or not 1 <= s <= 5:
        c.err(f"{what}.risk.severity: a whole number from 1 to 5 (how much harm the act can do), not {s!r}",
              r.at("severity"), "bad-value")
        s = 5
    if isinstance(t, bool) or not isinstance(t, int | float) or not math.isfinite(t) or not 1 < t <= HIGHEST:
        c.err(f"{what}.risk.threshold: a number above 1 and at most {HIGHEST:g} (the score that steps its gate), "
              f"not {t!r}", r.at("threshold"), "bad-value")
        t = THRESHOLD
    return s, float(t)


def blocks(c, spec) -> None:
    """An ``ai`` block's directory and what its session may use: ``workdir:`` (a folder) or ``workspace:`` (a pool, a
    workspace per item); ``read:`` (more folders it may read); ``tools:`` (Claude Code's tools it may use) and
    ``actions:`` (the gated actions it may ask for). ``tools:`` or ``actions:`` puts its session in the sandbox. A
    ``program`` block may name ``workspace:`` (its item's workspace, in its environment) and ``actions:`` (asked for
    with ``ergostat act``); it has no session to sandbox."""
    for b in spec.blocks.values():
        if b.type not in ("ai", "program"):
            continue
        what = f"block {b.name}"
        p = b.params
        if p.get("workdir") is not None and p.get("workspace") is not None:
            c.err(f"{what}: workdir: or workspace:, not both (a workspace is the folder each item's run works in)",
                  b.where, "both-keys")
        if p.get("workdir") is not None and not isinstance(p["workdir"], str):
            c.err(f"{what}.workdir: a folder (from the model's folder, or a whole path)", b.where, "bad-path")
            p.pop("workdir")
        ws = p.get("workspace")
        if ws is not None and str(ws) not in spec.workspaces:
            c.err(f"{what}.workspace: {ws!r} is not a pool under workspaces:" + c.suggest(str(ws), spec.workspaces),
                  b.where, "unknown-ref", f"workspace.{ws}")
            p.pop("workspace")
        for key in ("read", "tools", "actions"):
            v = p.get(key)
            if v is None:
                continue
            if isinstance(v, str):
                v = [v]
            if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
                c.err(f"{what}.{key}: a list" + {"read": " of folders", "tools": " of Claude Code's tools (Read, Edit, "
                      "Bash(python3:*))", "actions": " of the actions: it may ask for"}[key], b.where, "bad-value")
                p.pop(key)
                continue
            p[key] = v
        for t in p.get("tools") or []:
            if not TOOL.match(t) or t.startswith("mcp__"):
                c.err(f"{what}.tools: {t!r}: one of Claude Code's tools, as its permission rules write it (Read, Edit, "
                      f"Bash, Bash(python3:*)); outward acts are actions:, not tools", b.where, "bad-value")
        for a in p.get("actions") or []:
            if a not in spec.actions:
                c.err(f"{what}.actions: {a!r} is not one of the actions:" + c.suggest(a, spec.actions), b.where,
                      "unknown-ref", f"action.{a}")
        if b.type == "ai" and "run" in p and p.get("tools") is not None and "session" not in str(p["run"]):
            c.err(f"{what}: tools: are given to the Claude Code session ergostat starts: without run:, or with a run: "
                  f"that starts it through ergostat session (actions: alone its run: may ask for with ergostat act)",
                  b.where, "sandbox-needs-session", "")
