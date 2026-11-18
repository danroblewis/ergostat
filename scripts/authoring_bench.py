"""How well a small model adds a small control system from a request in plain words.

    uv run python scripts/authoring_bench.py ROUND [--model haiku] [--only 1,3] [--out /tmp/ergostat-bench]

For each request below: a scratch copy of examples/the-job with the ergostat-author skill in .claude/skills/ and
ergostat's MCP server, and Claude Code (``claude -p``, the model asked) given the request text alone (the harness
says only that the owner is away and approves writing it to the copy). Then, independently of what the agent said:
did the model check, was an instance written, and does it run (a 30-second trial of each new system). Per request:
whether its first add_use passed check and its first try_use ran without a failure, the turns, the cost, and the
trial's verdict. Writes ROUND/results.json and prints a table."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUESTS = [
    ("respond", "Questions for me land in our team's shared help queue. bin/help-queue.sh prints the open ones as JSON "
                "(one object per line, each with an id, a title and who asked). Draft an answer for each new one as it "
                "comes in, into outbox/, and let me know if any question has gone four hours without an answer."),
    ("reping", "When I ask someone for a review of my pull request and they haven't answered within a day, remind "
               "them. Remind at most three times, then hand it back to me so I can chase them in person."),
    ("report", "Every weekday at 8:30 in the morning, write me a short report of what's open right now: the goals "
               "that are off and the items still waiting."),
    ("keep", "Keep the build cache directory (~/.cache/build) under 20 GB. When it goes over, delete the oldest "
             "artifacts until it's back under 15 GB."),
    ("steps", "When a regression ticket arrives from our tracker (https://tracker.example.internal/api/issues?type="
              "regression, a JSON list; the token is in $TRACKER_TOKEN), work it through these steps in order: "
              "label it, find the commit that probably caused it, and draft a revert description into outbox/."),
]
HARNESS = ("The owner is away and cannot answer questions: make reasonable assumptions and list them at the end. The "
           "owner has approved turning the result on in this folder (a scratch copy), once it checks and runs.")
TOOLS = ["mcp__ergostat", "Read", "Write", "Edit", "Glob", "Grep", "Bash", "Skill"]


def setup(base: Path, n: int) -> Path:
    copy = base / f"{n}" / "the-job"
    if copy.parent.exists():
        shutil.rmtree(copy.parent)
    shutil.copytree(ROOT / "examples" / "the-job", copy, ignore=shutil.ignore_patterns("run", "outbox", "__pycache__"))
    skill = copy / ".claude" / "skills" / "ergostat-author"
    skill.mkdir(parents=True)
    shutil.copy(ROOT / "docs" / "skills" / "ergostat-author" / "SKILL.md", skill / "SKILL.md")
    py = ROOT / ".venv" / "bin" / "python"
    (copy.parent / "mcp.json").write_text(json.dumps({"mcpServers": {"ergostat": {
        "command": str(py), "args": ["-m", "ergostat", "-C", str(copy), "mcp"],
        "env": {"ERGOSTAT_HOME": str(copy.parent / "home")}}}}))
    subprocess.run(["git", "init", "-q"], cwd=copy)       # a repository of its own, so nothing reaches the real one
    return copy


def calls(stream: list[dict]) -> list[tuple[str, dict, str]]:
    """(tool, input, result text) in order."""
    pending: dict = {}
    out = []
    for m in stream:
        if m.get("type") == "assistant":
            for c in (m.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    pending[c["id"]] = (c["name"], c.get("input") or {})
        elif m.get("type") == "user":
            for c in (m.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                    body = c.get("content")
                    text = body if isinstance(body, str) else "".join(x.get("text", "") for x in body or [] if isinstance(x, dict))
                    out.append((*pending.pop(c["tool_use_id"]), text))
    return out


def first(cs, name: str):
    return next(((i, r) for t, i, r in cs if t == f"mcp__ergostat__{name}"), None)


def grade(copy: Path, before: set[str]) -> dict:
    py = str(ROOT / ".venv" / "bin" / "python")
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "grade-home")}
    chk = subprocess.run([py, "-m", "ergostat", "-C", str(copy), "check"], capture_output=True, text=True, env=env)
    code = ("import json,sys; from pathlib import Path; from ergostat.spec.load import load; "
            "d=load(Path(sys.argv[1])/'ergostat.yaml'); "
            "print(json.dumps({k:{'template':v['template'],'values':v['values'],'standins':v['standins'],'where':str(v['where'])} "
            "for k,v in d.uses.items()}))")
    got = subprocess.run([py, "-c", code, str(copy)], capture_output=True, text=True, env=env)
    uses = json.loads(got.stdout or "{}") if got.returncode == 0 else {}
    new = {k: v for k, v in uses.items() if k not in before}
    trials = {}
    for inst in new:
        for how, standins in (("as_written", False), ("on_stand_ins", True)):
            t = subprocess.run([py, "-c", "import json,sys; from pathlib import Path; from ergostat.library import author; "
                                "r=author.trial(Path(sys.argv[1]), sys.argv[2], seconds=30, standins=sys.argv[3]=='1'); "
                                "print(json.dumps({'verdict': r.get('verdict'), 'check': r.get('check'), 'error': r.get('error')}))",
                                str(copy), inst, "1" if standins else "0"], capture_output=True, text=True, env=env, timeout=400)
            try:
                trials.setdefault(inst, {})[how] = json.loads(t.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                trials.setdefault(inst, {})[how] = {"error": (t.stderr or t.stdout)[-800:]}
    return {"check_ok": chk.returncode == 0, "check": chk.stdout.strip().splitlines()[:1] + [
                x for x in chk.stdout.splitlines() if x.startswith("error")][:8],
            "uses": new, "trials": trials}


def run_one(base: Path, n: int, model: str, timeout: float) -> dict:
    key, text = REQUESTS[n - 1]
    copy = setup(base, n)
    began = time.time()
    cmd = ["claude", "-p", text, "--model", model, "--mcp-config", str(copy.parent / "mcp.json"), "--strict-mcp-config",
           "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
           "--allowedTools", *TOOLS, "--append-system-prompt", HARNESS, "--max-turns", "80"]
    env = {**os.environ, "ERGOSTAT_HOME": str(copy.parent / "home")}
    try:
        p = subprocess.run(cmd, cwd=copy, capture_output=True, text=True, timeout=timeout, env=env)
        out = p.stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    stream = []
    for line in out.splitlines():
        try:
            stream.append(json.loads(line))
        except ValueError:
            pass
    (copy.parent / "transcript.jsonl").write_text(out)
    result = next((m for m in reversed(stream) if m.get("type") == "result"), {})
    cs = calls(stream)
    fa, ft = first(cs, "add_use"), first(cs, "try_use")

    def ok_add(r):
        try:
            return json.loads(r)["ok"]
        except (ValueError, KeyError, TypeError):
            return False

    def ok_try(r):
        try:
            d = json.loads(r)
        except (ValueError, TypeError):
            return False
        ran = d.get("ran")
        return bool(d.get("check", {}).get("ok")) and isinstance(ran, dict) and not ran.get("sensor_failures") and \
            not any(b.get("failed") for b in ran.get("blocks", {}).values()) and bool(ran.get("items") or ran.get("stocks"))
    skill_used = any(t == "Skill" for t, _, _ in cs) or any("ergostat-author" in json.dumps(i) for t, i, _ in cs if t == "Read")
    graded = grade(copy, set())
    return {"n": n, "request": key, "seconds": round(time.time() - began), "turns": result.get("num_turns"),
            "cost_usd": result.get("total_cost_usd"), "stopped": result.get("subtype"), "skill_used": skill_used,
            "tools": [t.replace("mcp__ergostat__", "") for t, _, _ in cs],
            "first_add_ok": ok_add(fa[1]) if fa else None, "first_try_ok": ok_try(ft[1]) if ft else None,
            "first_add": fa[0] if fa else None, "final_text": (result.get("result") or "")[-1500:], **graded,
            "folder": str(copy)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("round")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--only")
    ap.add_argument("--out", default="/tmp/ergostat-bench")
    ap.add_argument("--timeout", type=float, default=1500)
    a = ap.parse_args()
    base = Path(a.out) / a.round
    base.mkdir(parents=True, exist_ok=True)
    which = [int(x) for x in a.only.split(",")] if a.only else list(range(1, len(REQUESTS) + 1))
    with cf.ThreadPoolExecutor(len(which)) as ex:
        got = list(ex.map(lambda n: run_one(base, n, a.model, a.timeout), which))
    (base / "results.json").write_text(json.dumps(got, indent=1, default=str))
    print(f"{'#':<3}{'request':<9}{'skill':<7}{'add 1st':<9}{'try 1st':<9}{'check':<7}{'written':<18}{'runs':<6}{'stand-ins':<10}"
          f"{'turns':<7}{'cost':<8}")

    def runs(t: dict) -> bool:
        return bool(t) and not t.get("error") and t.get("check", {}).get("ok") and \
            not any("failed" in v for v in t.get("verdict") or [])
    for r in got:
        ts = r["trials"].values()
        print(f"{r['n']:<3}{r['request']:<9}{str(r['skill_used']):<7}{str(r['first_add_ok']):<9}{str(r['first_try_ok']):<9}"
              f"{str(r['check_ok']):<7}{','.join(r['uses']) or '-':<18}{str(bool(ts) and all(runs(t.get('as_written')) for t in ts)):<6}"
              f"{str(bool(ts) and all(runs(t.get('on_stand_ins')) for t in ts)):<10}{str(r['turns']):<7}{(r['cost_usd'] or 0):<8.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
