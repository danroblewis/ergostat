"""The parity benchmark (docs/proposals/harness-parity-plan.md, F3): does a fresh session, started from a given
context, know what the long session knew?

A **case** is a question only the long session could answer (what was decided and why, what the owner means by a
phrase, what was rejected, a preference, the state of something at a point), or a small **task** it did, with the
ground truth in the owner's words and the line it came from. A **variant** is a starting context: plain text (a
file), from any projection; ``contexts.py`` has the built-ins. For each variant and case, a fresh session (``claude
-p``, no tools unless the case names read-only ones, no settings, CLAUDE.md or memory of its own) is given the context
as its system prompt (so every case of a variant reads it from the cache) and the case as its message. A judge, a
separate session, is given the ground truth, the rubric and the answer, and says correct, partly, wrong or
contradicts (the owner), with a one-line reason; a case may also carry exact checks (patterns the answer must or
must not contain). The scorecard, per variant, per kind and per case, with cost and tokens, is written as Markdown
and JSON. Answers are kept as they come (``answers.jsonl``), so a run stopped at its cost cap, or a variant added
later, runs only what is missing.

The dataset of the first run is the owner's conversation and lives outside the repository; the tests use made-up
cases."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERDICTS = ("correct", "partly", "wrong", "contradicts")
POINTS = {"correct": 1.0, "partly": 0.5, "wrong": 0.0, "contradicts": 0.0}
KINDS = ("decision", "meaning", "rejected", "preference", "state", "task")
READ_ONLY = {"Read", "Grep", "Glob"}

ANSWER = """You are a new Claude session joining a software project partway through, working for its owner. Everything \
you know about the project is below (it may be nothing). The owner will ask you a question or give you a small task.
- For a question: answer in at most 120 words, directly, with the reason when the question asks why. If what you \
know does not answer it, say plainly that you do not know; do not invent the owner's views.
- For a task: do it as you would for this owner, in at most 400 words."""

JUDGE = """You judge whether a new session's answer matches what the owner of a project actually said. You are \
given the question (or task), the ground truth in the owner's own words, sometimes a rubric, and the answer.
Verdicts:
- correct: the answer carries the ground truth's substance (wording may differ); for a task, it does what the owner \
meant and avoids every mistake the owner corrected;
- partly: some of the substance, or the right answer with a wrong reason, or vague where the truth is specific;
- wrong: misses it, or says it does not know, or answers something else, without asserting the opposite;
- contradicts: asserts what the owner rejected or the opposite of what the owner said (for a task: makes the \
mistake the owner corrected).
Judge only against the ground truth, not your own views. Reply with one line of JSON and nothing else:
{"verdict": "correct|partly|wrong|contradicts", "reason": "one line"}"""


@dataclass
class Case:
    id: str
    kind: str
    question: str
    truth: str
    source: str = ""
    rubric: str = ""
    checks: dict = field(default_factory=dict)       # {"all": [re], "any": [re], "none": [re]}, case-insensitive
    tools: list = field(default_factory=list)        # read-only tools the case needs (Read, Grep, Glob)

    @classmethod
    def of(cls, d: dict) -> Case:
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        c = cls(**known)
        if c.kind not in KINDS:
            raise ValueError(f"case {c.id}: kind {c.kind!r} is not one of {', '.join(KINDS)}")
        bad = set(c.tools) - READ_ONLY
        if bad:
            raise ValueError(f"case {c.id}: tools {sorted(bad)} are not read-only ({', '.join(sorted(READ_ONLY))})")
        return c


def load_cases(path: Path) -> list[Case]:
    """Cases from a JSON list or JSON lines."""
    text = Path(path).read_text(encoding="utf-8")
    rows = json.loads(text) if text.lstrip().startswith("[") else [json.loads(x) for x in text.splitlines() if x.strip()]
    cases = [Case.of(r) for r in rows]
    ids = [c.id for c in cases]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"cases named twice: {', '.join(dup)}")
    return cases


def load_variants(specs: list[str]) -> dict[str, str]:
    """``name=FILE`` each (``none`` alone: no context); the name is the file's stem when there is no ``=``."""
    out: dict[str, str] = {}
    for s in specs:
        if s == "none":
            out["none"] = ""
            continue
        name, _, path = s.partition("=") if "=" in s else (Path(s).stem, "", s)
        out[name] = Path(path).read_text(encoding="utf-8")
    return out


def check(case: Case, answer: str) -> bool | None:
    """The case's exact checks on the answer: None when it has none."""
    c = case.checks or {}
    if not any(c.get(k) for k in ("all", "any", "none")):
        return None

    def has(p):
        return re.search(p, answer, re.IGNORECASE) is not None

    return (all(has(p) for p in c.get("all") or []) and (not c.get("any") or any(has(p) for p in c["any"]))
            and not any(has(p) for p in c.get("none") or []))


@dataclass
class Reply:
    text: str = ""
    usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0
    error: str | None = None


class Claude:
    """A fresh ``claude -p`` session per call: the system prompt given (the context), no tools unless named, no
    settings, CLAUDE.md, memory, MCP servers or saved session; run in an empty directory unless a case reads a
    repository. ``ERGOSTAT_AI`` names another command (the tests' stand-in)."""

    def __init__(self, model: str = "sonnet", timeout: float = 300.0, repo: Path | None = None):
        self.model, self.timeout, self.repo = model, timeout, repo
        self.empty = Path(tempfile.mkdtemp(prefix="ergostat-parity-"))

    def ask(self, system: str, prompt: str, tools: list | tuple = ()) -> Reply:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(system)
        cmd = [os.environ.get("ERGOSTAT_AI") or "claude", "-p", "--model", self.model, "--output-format", "json",
               "--safe-mode", "--no-session-persistence", "--strict-mcp-config", "--tools", ",".join(tools),
               "--system-prompt-file", fh.name]
        cwd = self.repo if tools and self.repo else self.empty
        t0 = time.perf_counter()
        try:
            got = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, cwd=cwd)
            out = json.loads(got.stdout)
        except subprocess.TimeoutExpired:
            return Reply(error="timed out", seconds=round(time.perf_counter() - t0, 1))
        except (ValueError, OSError) as e:
            return Reply(error=f"{type(e).__name__}: {str(e)[:200]}", seconds=round(time.perf_counter() - t0, 1))
        finally:
            os.unlink(fh.name)
        u = out.get("usage") or {}
        tin = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        text = str(out.get("result") or "")
        err = None
        if out.get("is_error") or text.startswith("API Error"):
            err = text[:200] or "error"
        return Reply(text, float(out.get("total_cost_usd") or 0.0), tin, int(u.get("output_tokens") or 0),
                     round(time.perf_counter() - t0, 1), err)


def system_for(context: str) -> str:
    return ANSWER + (f"\n\n<context>\n{context}\n</context>" if context.strip() else "\n\n(You know nothing of it yet.)")


def judge_prompt(case: Case, answer: str) -> str:
    what = "Task" if case.kind == "task" else "Question"
    truth = "What the owner said (for a task: what they meant and how they corrected it)" if case.kind == "task" \
        else "Ground truth, in the owner's words"
    return (f"{what}:\n{case.question}\n\n{truth}:\n{case.truth}\n\n" + (f"Rubric:\n{case.rubric}\n\n" if case.rubric else "")
            + f"Answer to judge:\n{answer}\n")


def parse_verdict(text: str) -> tuple[str | None, str]:
    for line in reversed(text.strip().splitlines()):
        line = line.strip().strip("`")
        if line.startswith("{"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            v = str(d.get("verdict", "")).strip().lower()
            if v in VERDICTS:
                return v, str(d.get("reason", ""))[:300]
    m = re.search(r"\b(correct|partly|wrong|contradicts)\b", text.lower())
    return (m.group(1) if m else None), text.strip().splitlines()[-1][:300] if text.strip() else ""


def key(variant: str, context: str, case: Case) -> str:
    h = hashlib.sha1(f"{context}\n\0{case.question}\n\0{case.truth}".encode()).hexdigest()[:12]
    return f"{variant}/{case.id}/{h}"


class Budget:
    def __init__(self, usd: float | None, spent: float = 0.0):
        self.cap, self.spent, self.lock = usd, spent, threading.Lock()
        self.stopped = False

    def add(self, usd: float) -> None:
        with self.lock:
            self.spent += usd

    def ok(self) -> bool:
        with self.lock:
            if self.cap is not None and self.spent >= self.cap:
                self.stopped = True
            return not self.stopped


def _one(case: Case, variant: str, context: str, answerer, judge) -> dict:
    a = answerer.ask(system_for(context), case.question, case.tools)
    row = {"key": key(variant, context, case), "variant": variant, "case": case.id, "kind": case.kind,
           "answer": a.text, "answer_error": a.error, "answer_usd": a.usd, "tokens_in": a.tokens_in,
           "tokens_out": a.tokens_out, "seconds": a.seconds, "check": check(case, a.text) if not a.error else None,
           "verdict": None, "reason": "", "judge_usd": 0.0, "judge_tokens": 0}
    if a.error:
        row["reason"] = f"no answer: {a.error}"
        return row
    j = judge.ask(JUDGE, judge_prompt(case, a.text))
    row["judge_usd"], row["judge_tokens"] = j.usd, j.tokens_in + j.tokens_out
    if j.error:
        row["reason"] = f"no verdict: {j.error}"
        return row
    row["verdict"], row["reason"] = parse_verdict(j.text)
    return row


def run(cases: list[Case], variants: dict[str, str], answerer, judge, out: Path, workers: int = 4,
        max_usd: float | None = None, say=None) -> dict:
    """Every case under every variant, those not in ``out/answers.jsonl`` already; the scorecard written."""
    out.mkdir(parents=True, exist_ok=True)
    log = out / "answers.jsonl"
    done: dict[str, dict] = {}
    if log.exists():
        for x in log.read_text(encoding="utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                if r.get("verdict"):                  # judged: kept; an error or no verdict runs again
                    done[r["key"]] = r
    budget = Budget(max_usd, sum(r["answer_usd"] + r["judge_usd"] for r in done.values()))
    lock = threading.Lock()

    def go(case, name, ctx):
        if not budget.ok():
            return
        r = _one(case, name, ctx, answerer, judge)
        budget.add(r["answer_usd"] + r["judge_usd"])
        with lock:
            done[r["key"]] = r
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(r) + "\n")
        if say:
            say(f"{name:10s} {case.id:24s} {r['verdict'] or r['reason'][:40]}  (${budget.spent:.2f})")

    for name, ctx in variants.items():
        todo = [c for c in cases if key(name, ctx, c) not in done]
        if not todo:
            continue
        go(todo[0], name, ctx)                       # alone: the context is written to the cache once
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(lambda c, n=name, x=ctx: go(c, n, x), todo[1:]))
    card = scorecard(cases, variants, done, stopped=budget.stopped, cap=max_usd)
    (out / "scorecard.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    (out / "scorecard.md").write_text(markdown(card), encoding="utf-8")
    return card


def _score(rows: list[dict]) -> dict:
    n = len(rows)
    got = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
    judged = sum(got.values())
    checked = [r["check"] for r in rows if r["check"] is not None]
    return {"cases": n, **got, "unjudged": n - judged,
            "score": round(sum(POINTS[r["verdict"]] for r in rows if r["verdict"]) / n, 3) if n else None,
            "checks_passed": sum(checked), "checks": len(checked),
            "usd": round(sum(r["answer_usd"] + r["judge_usd"] for r in rows), 4),
            "answer_usd": round(sum(r["answer_usd"] for r in rows), 4),
            "tokens_in": sum(r["tokens_in"] for r in rows), "tokens_out": sum(r["tokens_out"] for r in rows),
            "judge_tokens": sum(r["judge_tokens"] for r in rows)}


def scorecard(cases: list[Case], variants: dict[str, str], done: dict[str, dict], stopped: bool = False,
              cap: float | None = None) -> dict:
    per: dict[str, dict] = {}
    rows_of: dict[str, list[dict]] = {}
    for name, ctx in variants.items():
        rows = [done[key(name, ctx, c)] for c in cases if key(name, ctx, c) in done]
        rows_of[name] = rows
        kinds = {k: _score([r for r in rows if r["kind"] == k]) for k in KINDS if any(r["kind"] == k for r in rows)}
        per[name] = {**_score(rows), "of": len(cases), "context_chars": len(ctx),
                     "by_kind": {k: v["score"] for k, v in kinds.items()}}
    table = []
    for c in cases:
        row = {"case": c.id, "kind": c.kind, "question": c.question, "source": c.source, "variants": {}}
        for name, ctx in variants.items():
            r = done.get(key(name, ctx, c))
            if r:
                row["variants"][name] = {"verdict": r["verdict"], "reason": r["reason"], "check": r["check"],
                                         "answer": r["answer"]}
        table.append(row)
    total = sum(v["usd"] for v in per.values())
    return {"variants": per, "cases": table, "usd": round(total, 4), "stopped_at_cap": stopped, "cap_usd": cap}


SIGN = {"correct": "✓", "partly": "½", "wrong": "✗", "contradicts": "‼", None: "·"}


def markdown(card: dict) -> str:
    vs = card["variants"]
    names = list(vs)
    out = ["# Parity benchmark", ""]
    if card.get("stopped_at_cap"):
        out += [f"**Stopped at the cost cap (${card['cap_usd']}): some cases did not run.**", ""]
    out += ["| Variant | Context (chars) | Score | Correct | Partly | Wrong | Contradicts | Unjudged | Checks | $ | Tokens in / out |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, v in vs.items():
        out.append(f"| {n} | {v['context_chars']} | {v['score']} | {v['correct']} | {v['partly']} | {v['wrong']} | "
                   f"{v['contradicts']} | {v['unjudged'] + v['of'] - v['cases']} | {v['checks_passed']}/{v['checks']} | "
                   f"{v['usd']} | {v['tokens_in']} / {v['tokens_out']} |")
    kinds = [k for k in KINDS if any(k in v["by_kind"] for v in vs.values())]
    out += ["", f"Total cost ${card['usd']}. Score: correct 1, partly ½, the rest 0, over the cases run.", "",
            "## By kind", "", "| Variant | " + " | ".join(kinds) + " |", "|---|" + "---|" * len(kinds)]
    for n, v in vs.items():
        out.append(f"| {n} | " + " | ".join(str(v["by_kind"].get(k, "–")) for k in kinds) + " |")
    out += ["", "## Per case", "", "✓ correct, ½ partly, ✗ wrong, ‼ contradicts the owner, · not judged.", "",
            "| Case | Kind | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for c in card["cases"]:
        out.append(f"| {c['case']} | {c['kind']} | " + " | ".join(SIGN[(c['variants'].get(n) or {}).get('verdict')]
                                                                  for n in names) + " |")
    out += ["", "## Not right, per variant", ""]
    for n in names:
        miss = [(c, c["variants"][n]) for c in card["cases"] if n in c["variants"]
                and c["variants"][n]["verdict"] not in ("correct",)]
        out.append(f"### {n} ({len(miss)})")
        out += [f"- {c['case']} ({r['verdict'] or 'not judged'}): {r['reason']}" for c, r in miss]
        out.append("")
    return "\n".join(out) + "\n"


def as_dict(c: Case) -> dict:
    return asdict(c)
