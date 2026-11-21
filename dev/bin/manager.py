"""pipeline-manager: takes a situation raised by watch.py and has an AI session look at it (dev/README.md, *The
pipeline manager*): a brief of the situation, its subject and the pipeline around it, with the factory's knowledge; the
session's manage.py calls, from a fenced JSON block, each run through manage.py's own checks as `pipeline-manager`.
A heartbeat first reads the velocity, and files a gap when a queue goal is off (one of them open at a time)."""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import knowledge  # noqa: E402
import manage  # noqa: E402
import measure  # noqa: E402
import watch  # noqa: E402

ROLE, MOST_CALLS = "pipeline_manager", 6
ANSWER = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
GOAL = r"^  {name}:\s*$.*?hold: \"<= ([\d.]+)\"\s*tolerance: ([\d.]+)"
PROPOSALS = {                    # a measure off: (its goal, the gap proposed)
    "queue-wait-hours": ("queue-wait-short", "merge-batching", "The merge queue tests approved gaps in batches and "
                         "bisects a failing batch", "approved gaps wait for the queue one at a time"),
    "suite-minutes": ("suites-in-time", "queue-suites-faster", "The queue's suites within their time budget",
                      "the queue's suites take longer than their budget"),
}


def tail(d: Path, pattern: str, n: int = 1500) -> str:
    """The end of the latest log matching, under a heading ("" when there is none)."""
    got = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime)
    return f"\n\n### The tail of {fac.rel(got[-1])}\n\n```\n{got[-1].read_text(errors='replace')[-n:]}\n```" if got else ""


def utc(t) -> str:
    return time.strftime("%m-%d %H:%M", time.gmtime(float(t or 0)))


def listed(head: str, rows) -> str:
    return f"## {head}\n\n" + ("\n".join(f"- {r}" for r in rows) or "(none)")


def about_gap(cfg: dict, gid: str) -> str:
    g = watch.detail(gid)
    f, b = g["fields"], watch.branch(g)
    keep = ("title", "branch", "continues", "depends_on", "blocked_reason", "where_it_stopped", "findings", "failed_suite",
            "failed_tests", "suites_fast", "sent_back_by", "failed_gates", "build_failures", "retries", "head",
            "reviewed_head", "push", "last_error", "time_in")
    moves = "\n".join(f"- {utc(m['time'])} {m.get('from')} -> {m['to']} ({m.get('type')})" for m in (g.get("moves") or [])[-20:])
    reviews = [f"{r} ({(x := watch.detail(r)['fields']).get('verdict')}): {x.get('blocking')}"[:1500]
               for r in fac.ids(f.get("reviews"))[-3:]]
    sessions = [f"{s['id']} ({s['state']}, {s['fields'].get('role')}, ${s['fields'].get('cost')})" for s in
                fac.items("session") if gid in fac.ids(s["fields"].get("gap"))][-8:]
    return (f"## {gid} ({g['state']})\n\n```json\n{json.dumps({k: f[k] for k in keep if k in f}, indent=1, default=str)[:6000]}"
            f"\n```\n\n### Its moves (UTC)\n\n{moves}\n\n#{listed('Its reviews', reviews)}\n\n#"
            f"{listed('Its sessions', sessions)}" + tail(fac.run_dir(cfg, "logs"), f"{b}-*.txt")
            + tail(fac.run_dir(cfg, "queue"), f"{b}-*.txt"))


def situation(cfg: dict, sit: dict, readings: dict) -> str:
    f, subject = sit["fields"], str(sit["fields"].get("subject") or "")
    gaps = fac.items("gap")
    repo = fac.path(cfg, "checkout")
    parts = [f"# The situation ({sit['id']}): {f.get('trigger')}\n\n{f.get('why')}"]
    if subject.startswith("gap/"):
        parts.append(about_gap(cfg, subject))
    elif subject.startswith("intervention/"):
        parts.append(f"## {subject}\n\n```json\n{json.dumps(watch.detail(subject)['fields'], indent=1, default=str)[:3000]}\n```")
    parts += [f"## The merge queue\n\n```json\n{json.dumps(watch.queue_state(cfg), indent=1, default=str)[:2000]}\n```"
              + tail(fac.run_dir(cfg, "queue"), "*.txt", 1000),
              "## Main's recent commits\n\n```\n" + fac.git(repo, "log", "--oneline", "-12", cfg["git"]["base"],
                                                                check=False) + "\n```",
              listed("Open interventions", (f"{i['id']} ({i['fields'].get('class')}, by {i['fields'].get('by')}): "
                                            f"{str(i['fields'].get('reason'))[:300]}" for i in fac.items("intervention", "open"))),
              listed("Known flakes", (x["fields"].get("test", x["id"]) for x in fac.items("flake", "seen"))),
              listed("The pipeline (UTC)", (f"{g['id']} {g['state']} since {utc(g.get('entered'))}" for g in gaps
                                            if g["state"] not in ("merged", "parked", "closed", "open", "replan"))),
              f"## Velocity\n\n```json\n{json.dumps(readings, indent=1)}\n```"]
    return "\n\n".join(parts)


def goal(name: str) -> float:
    """A goal's setpoint plus its tolerance, from dev/model/measures.yaml."""
    m = re.search(GOAL.format(name=re.escape(name)), (fac.HERE / "model" / "measures.yaml").read_text(), re.M | re.S)
    return float(m[1]) + float(m[2]) if m else float("inf")


def velocity(cfg: dict) -> dict:
    """The readings, and the gap filed when a queue goal is off (none while another of the watch's is open)."""
    out: dict = {}
    for name in ("queue-wait-hours", "suite-minutes", "cycle-hours", "queue-minutes"):
        try:
            out[name] = measure.reading(name)
        except SystemExit:
            out[name] = None
    now, waits, gaps = time.time(), {}, fac.items("gap")
    for g in gaps:
        waits.setdefault(g["state"], []).append((now - float(g.get("entered") or now)) / 3600)
    out["hours-in-state"] = {s: round(statistics.median(v), 2) for s, v in waits.items() if s in watch.STUCK}
    if any(g["fields"].get("velocity") and g["state"] not in watch.ENDED for g in gaps):
        return out
    for name, (gname, branch, title, why) in PROPOSALS.items():
        if (out.get(name) or 0) > goal(gname) and not any(watch.branch(g) == branch for g in gaps):
            text = (f"# {branch}: {title}\n\ndepends-on: []\n\nBranch `{branch}`, from main. Filed by the pipeline "
                    f"manager's velocity watch: {why} ({name} reads {out[name]}, the goal {gname} holds it at "
                    f"{goal(gname):g} with its tolerance).\n\n## Definition of done\n\n{title}, and {name} back within "
                    f"its goal on the factory's own record.\n\n## Acceptance tests\n\n- a test that shows {name} falls "
                    "on a fixture with the change.\n\n## Size budget\n\n300 net lines.\n")
            out["filed"] = manage.file_gap(cfg, title, text, branch=branch, why=f"velocity: {name} off ({out[name]})",
                                           cls="velocity", velocity=name)
            break
    return out


def calls(said: str) -> tuple[list[list[str]], str]:
    blocks = ANSWER.findall(said)
    if not blocks:
        raise RuntimeError("the pipeline manager gave no fenced JSON answer")
    got = json.loads(blocks[-1])
    return [[str(x) for x in c] for c in got.get("calls") or [] if isinstance(c, list)], str(got.get("summary") or "")


def handle(cfg: dict, sit: dict) -> int:
    manage.BY[0], manage.SITUATION[0] = "pipeline-manager", sit["id"]
    readings = velocity(cfg) if sit["fields"].get("trigger") == "heartbeat" else {}
    _, work = agents.clone(cfg, "pipeline-manager", ROLE, at=f"origin/{cfg['git']['base']}")
    text = situation(cfg, sit, readings)
    know, carried = knowledge.block(cfg, ROLE, {"id": sit["id"], "fields": {"title": sit["fields"].get("why", "")}}, text)
    prompt = (fac.HERE / "prompts" / f"{ROLE}.md").read_text()
    full = prompt.replace("{situation}", text).replace("{knowledge}", know).replace("{tools}", manage.__doc__)
    context = {"role": ROLE, "brief_chars": len(full), "model": cfg["ai"][f"{ROLE}_model"], **carried,
               "brief": brief.save(cfg, ROLE, {"id": sit["id"], "fields": {"branch": sit["id"].split("/")[1][:60]}}, full)}
    got = fac.attempt(cfg, ROLE, full, work)
    if got is None:
        return 0
    todo, summary = calls(str(got.get("result", "")))
    done = [manage.run(cfg, c) for c in todo[:MOST_CALLS]]
    done += [{"call": c, "ok": False, "said": f"not run: at most {MOST_CALLS} calls a session"} for c in todo[MOST_CALLS:]]
    fac.say("situation.handled", handled_at=time.time(), summary=summary[:2000], actions=done, velocity=readings,
            context=context, ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4))
    return 0


def main() -> int:
    fac.stop_on_term()
    cfg = fac.config()
    given = fac.read_input()
    if fac.drain_holds(cfg):
        return 0
    try:
        return handle(cfg, given["item"])
    except agents.Refused as e:
        fac.nack(str(e), after="1h", count=False)
        return 0
    except Exception as e:  # noqa: BLE001 - failed on its last attempt, never a dead letter
        if fac.last_attempt(given):
            fac.say("situation.failed", failed_at=time.time(), error=f"{type(e).__name__}: {e}"[:1000])
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
