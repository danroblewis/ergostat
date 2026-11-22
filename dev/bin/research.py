"""researcher: takes a research item at asked (a question, from the coordinator's `dev/bin/ask.py`, a
`research.asked` event, or a planner) and answers it. In a read-only clone of main, a session reads the code, the docs
and, where its session allows it, the web; its report, with sources, is written to run/research/<name>.md and its
summary said on the item (research.answered). A planner waiting on it is given the report.

Each source line is checked first (``check``): a `path` or `path:line` must be in the clone at the sha it was cloned
at, the line within the file; a URL must be one the session opened (``opened``, from its transcript). An answer with
no checked source is research.unsourced and given back to be asked again, the why in its next brief; the second is
research.dead. Each is given back counted: the researcher's lease has two attempts, so the engine, which never lets
a run's own events leave an item dead, ends the second one a dead letter."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import sessions  # noqa: E402

URL = re.compile(r"https?://[^\s`'\"<>()\[\]\\]+")


def report(cfg: dict, item: dict) -> str:
    """An answered item's report, read only from run/research/ (anything else is refused: "")."""
    d = fac.run_dir(cfg, "research").resolve()
    p = (fac.MODEL / str(item["fields"].get("report") or "")).resolve()
    return p.read_text() if d in p.parents and p.is_file() else ""


def norm(url: str) -> str:
    return url.rstrip(".,;:").rstrip("/")


def opened(transcript: Path | None) -> set[str]:
    """The URLs the session opened: a WebFetch's (or a walker's goto's) url whose result came back without an error,
    and the urls in a WebSearch's results. Read from its transcript, the lines its session item folds as tool_calls
    and tool_results; none when there is no transcript, and none for a call with no result."""
    calls, got = {}, set()
    for raw in transcript.read_text(errors="replace").splitlines() if transcript and transcript.is_file() else []:
        try:
            msg = json.loads(raw).get("message")
        except (ValueError, AttributeError):
            continue
        for b in msg.get("content") if isinstance(msg, dict) and isinstance(msg.get("content"), list) else []:
            if not isinstance(b, dict):
                continue
            name, inp = str(b.get("name") or ""), b.get("input") if isinstance(b.get("input"), dict) else {}
            if b.get("type") == "tool_use" and (name in ("WebFetch", "WebSearch") or name.endswith("goto")):
                calls[b.get("id")] = None if name == "WebSearch" else str(inp.get("url") or "")
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in calls and not b.get("is_error"):
                url = calls[b["tool_use_id"]]
                got |= {url} if url is not None else set(URL.findall(json.dumps(b.get("content"))))
    return {norm(u) for u in got if u}


def check(work: Path, sha: str, source: str, urls: set[str]) -> str | None:
    """Why a source line is not checked; None when it is: a URL the session opened, or a file (and its line, or
    lines a-b) in the clone at ``sha``."""
    if u := URL.search(source):
        return None if norm(u[0]) in urls else f"{u[0]}: the session never opened it"
    m = re.match(r"`([^`]+)`", source.strip())
    where = m[1] if m else (source.split() or [""])[0].rstrip(":,;")
    got = re.fullmatch(r"(?:/work/|\./)?([^:\s]+?)(?::(\d+)(?:-(\d+))?)?:?", where)
    if not got or got[1].startswith("/") or ".." in got[1].split("/"):
        return f"{where!r}: not a file of the clone, a file:line or a URL"
    kind = fac.git(work, "cat-file", "-t", f"{sha}:{got[1]}", check=False)
    if kind not in ("blob", "tree"):
        return f"{got[1]}: no such file at {sha[:12]}"
    lines = [int(x) for x in got.groups()[1:] if x]
    if not lines:
        return None
    if kind != "blob":
        return f"{got[1]}: a folder, not a file with lines"
    n = len(subprocess.run(["git", "-C", str(work), "cat-file", "-p", f"{sha}:{got[1]}"], capture_output=True,
                           timeout=60, check=True).stdout.splitlines())
    return None if all(1 <= x <= n for x in lines) else f"{got[1]}: line {max(lines)} past the end ({n} lines)"


def transcript(cfg: dict, item: str) -> Path | None:
    """This run's session's transcript: the item's researcher session with the highest number (pool 1, leased)."""
    got = sessions.find(cfg, item, "researcher")
    return max(got, key=lambda p: int(sessions.ROLE.match(p.name)["n"]), default=None)


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    item = fac.read_input()["item"]
    if fac.drain_holds(cfg):
        return 0
    f = item["fields"]
    name =fac.slug(item["id"].split("/", 1)[1], 64)
    _, work = agents.clone(cfg, name, "researcher", at=f"origin/{cfg['git']['base']}")
    sha = fac.git(work, "rev-parse", "HEAD")
    asked = {**item, "fields": {**f, "branch": name, "title": str(f.get("question") or "")}}
    again = (f"\n\nAsked again: the last answer had no source that could be checked ({f.get('unsourced_why')}). "
             "Cite files and lines of the clone, or URLs this session opens." if f.get("unsourced") else "")
    text, context = brief.assemble(cfg, "researcher", asked, work, definition="", branch=name,
                                   question=str(f.get("question") or "") + again)
    context["brief"] = brief.save(cfg, "researcher", asked, text)
    got = fac.attempt(cfg, "researcher", text, work)
    if got is None:
        return 0
    said = str(got.get("result", ""))
    body = re.search(r"<report>\s*(.*?)</report>", said, re.S)
    if not body:
        raise RuntimeError("the researcher wrote no <report>")
    summary = re.search(r"<summary>\s*(.*?)</summary>", said, re.S)
    p = fac.run_dir(cfg, "research") / f"{name}.md"
    p.write_text(body[1].strip() + "\n")
    sources = re.findall(r"^- (.+)$", body[1].split("## Sources", 1)[-1] if "## Sources" in body[1] else "", re.M)
    urls, checked, unchecked = opened(transcript(cfg, item["id"])), [], []
    for s in sources[:30]:
        why = check(work, sha, s, urls)
        (unchecked.append({"source": s, "why": why}) if why else checked.append(s))
    data = dict(summary=" ".join((summary[1] if summary else "").split())[:1000], sources=sources[:30],
                sources_checked=checked, sources_unchecked=unchecked, contexts=[context],
                ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4))
    if checked:
        fac.say("research.answered", report=fac.rel(p), answered_at=time.time(), **data)
        return 0
    why = ("; ".join(u["why"] for u in unchecked) or "the report has no ## Sources lines")[:900]
    fac.say("research.dead" if f.get("unsourced") else "research.unsourced", unsourced_report=fac.rel(p), unsourced=1,
            unsourced_why=why, **data)
    fac.nack(f"unsourced: {why}", after="1m")       # (counted: the second unsourced answer is its lease's last attempt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
