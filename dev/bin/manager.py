"""pipeline-manager: takes the situation pipeline-watch raised (watch.py) and has one AI session look at the whole
pipeline (dev/README.md, *The pipeline manager*): a brief of every trigger it carries (each gap's history, the broken
conditions), the pipeline around them, the velocity record and the researcher's answers, with the factory's
knowledge. The session's manage.py calls, from a fenced JSON block, are each run through manage.py's own checks as
`pipeline-manager`, at most [manager] most_actions; it says per trigger what it did or why it left it."""

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

ROLE = "pipeline_manager"
ANSWER = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
GOALS = (("queue-wait-hours", "queue-wait-short"), ("suite-minutes", "suites-in-time"),
         ("first-pass-yield", "first-pass-good"))      # the queue's goals and the review's, for the binding constraint
DETAILED = 6                                            # gaps given in full; the rest by their trigger's line


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


def brief_text(cfg: dict, sit: dict, record: dict) -> str:
    f = sit["fields"]
    trig = list(f.get("triggers") or [])
    repo = fac.path(cfg, "checkout")
    gaps = fac.items("gap")
    parts = [f"# This session ({sit['id']}): {f.get('reason')}", listed(
        "The triggers, each by its fingerprint (answer each)", (f"`{t['print']}` {t['trigger']} {t['subject']}: {t['why']}"
                                                              for t in trig)),
             listed("The merge pipeline broken", (f"{k} since {utc(v['since'])}: {v['why']}"
                                                  for k, v in (f.get("broken") or {}).items()))]
    subjects = list(dict.fromkeys(t["subject"] for t in trig if t["subject"].startswith("gap/")))
    parts += [about_gap(cfg, g) for g in subjects[:DETAILED]]
    parts += [f"## {i}\n\n```json\n{json.dumps(watch.detail(i)['fields'], indent=1, default=str)[:2000]}\n```"
              for i in dict.fromkeys(t["subject"] for t in trig if t["subject"].startswith("intervention/"))][:DETAILED]
    parts += [f"## The merge queue\n\n```json\n{json.dumps(watch.queue_state(cfg), indent=1, default=str)[:2000]}\n```"
              + tail(fac.run_dir(cfg, "queue"), "*.txt", 1000),
              "## Main's recent commits\n\n```\n" + fac.git(repo, "log", "--oneline", "-12", cfg["git"]["base"],
                                                                check=False) + "\n```",
              listed("Open interventions", (f"{i['id']} ({i['fields'].get('class')}, by {i['fields'].get('by')}): "
                                            f"{str(i['fields'].get('reason'))[:300]}" for i in fac.items("intervention", "open"))),
              listed("Known flakes", (x["fields"].get("test", x["id"]) for x in fac.items("flake", "seen"))),
              listed("The pipeline (UTC)", (f"{g['id']} {g['state']} since {utc(g.get('entered'))}" for g in gaps
                                            if g["state"] not in ("merged", "parked", "closed", "open", "replan"))),
              f"## The velocity record\n\n```json\n{json.dumps(record, indent=1, default=str)}\n```"]
    return "\n\n".join(parts)


def reading(name: str):
    try:
        return measure.reading(name)
    except SystemExit:
        return None                                     # (no value yet)


def velocity(cfg: dict, now: float | None = None) -> dict:
    """The merge pipeline's record: its measures, its batches, time in each state, each goal against its setpoint and
    the binding constraint, and the manager's own proposals and questions with their answers."""
    now = now or time.time()
    out: dict = {n: reading(n) for n in ("queue-wait-hours", "queue-minutes", "suite-minutes", "merges-per-hour",
                                         "first-pass-yield", "cycle-hours")}
    gaps = fac.items("gap")
    merged = [g["fields"] for g in gaps if g["state"] == "merged" and float(g["fields"].get("merged_at") or 0) >= now - measure.WINDOW]
    batches: dict = {}
    for f in merged:
        b = batches.setdefault(f.get("batch_id") or f.get("main_sha"), {"size": 0, "runs": 1, "minutes": 0.0})
        b["size"] += 1
        b["runs"], b["minutes"] = max(b["runs"], int(f.get("batch_runs") or 1)), float(f.get("queue_minutes") or 0)
    sizes = [b["size"] for b in batches.values()]
    out["batches"] = {"n": len(batches), "median-size": statistics.median(sizes) if sizes else None,
                      "bisected": sum(b["runs"] > 1 for b in batches.values()),
                      "minutes-per-batch": round(statistics.median([b["minutes"] for b in batches.values()]), 1) if sizes else None,
                      "minutes-per-merge": round(sum(b["minutes"] for b in batches.values()) / len(merged), 1) if merged else None}
    waits: dict = {}
    for g in gaps:
        waits.setdefault(g["state"], []).append((now - float(g.get("entered") or now)) / 3600)
    out["hours-in-state"] = {s: round(statistics.median(v), 2) for s, v in waits.items() if s in watch.STUCK}
    goals = {}
    for m, gname in GOALS:
        sp = watch.hold("measures.yaml", gname)
        if sp and out.get(m) is not None:
            goals[gname] = {"measure": m, "reading": out[m], "hold": sp,
                            "off": round(sp / out[m] if m == "first-pass-yield" and out[m] else out[m] / sp, 2)}
    out["goals"] = goals
    out["binding"] = max(goals, key=lambda k: goals[k]["off"], default=None)
    out["proposals"] = [f"{g['id']} ({g['state']})" for g in gaps if g["fields"].get("velocity")][-5:]
    out["research"] = [{"id": r["id"], "state": r["state"], "question": r["fields"].get("question"),
                        "summary": r["fields"].get("summary"), "report": r["fields"].get("report")}
                       for r in fac.items("research") if r["fields"].get("asked_by") == watch.BY][-5:]
    return out


def answer(said: str) -> dict:
    blocks = ANSWER.findall(said)
    if not blocks:
        raise RuntimeError("the pipeline manager gave no fenced JSON answer")
    got = json.loads(blocks[-1])
    return {"calls": [[str(x) for x in c] for c in got.get("calls") or [] if isinstance(c, list)],
            "answers": {str(k): str(v)[:1000] for k, v in (got.get("answers") or {}).items()},
            "summary": str(got.get("summary") or "")}


def handle(cfg: dict, sit: dict) -> int:
    if "prints" not in sit["fields"]:                # raised by the one-trigger watch: never run with no triggers
        fac.say("situation.superseded", superseded_at=time.time(), summary="raised before sessions carried every "
                "trigger: closed unrun; its trigger, if it still stands, is in the next session")
        return 0
    manage.BY[0], manage.SITUATION[0] = watch.BY, sit["id"]
    most = watch.settings(cfg)["most"]
    record = velocity(cfg)
    _, work = agents.clone(cfg, "pipeline-manager", ROLE, at=f"origin/{cfg['git']['base']}")
    text = brief_text(cfg, sit, record)
    know, carried = knowledge.block(cfg, ROLE, {"id": sit["id"], "fields": {"title": "the merge pipeline"}}, text)
    prompt = (fac.HERE / "prompts" / f"{ROLE}.md").read_text().replace("{most}", str(most))
    full = prompt.replace("{situation}", text).replace("{knowledge}", know).replace("{tools}", manage.__doc__)
    context = {"role": ROLE, "brief_chars": len(full), "model": cfg["ai"][f"{ROLE}_model"], **carried,
               "brief": brief.save(cfg, ROLE, {"id": sit["id"], "fields": {"branch": sit["id"].split("/")[1][:60]}}, full)}
    got = fac.attempt(cfg, ROLE, full, work)
    if got is None:
        return 0
    a = answer(str(got.get("result", "")))
    done = [manage.run(cfg, c) for c in a["calls"][:most]]
    done += [{"call": c, "ok": False, "said": f"not run: at most {most} calls a session"} for c in a["calls"][most:]]
    trig = sit["fields"].get("triggers") or []
    answers = [{"print": t["print"], "subject": t["subject"], "answer": a["answers"].get(t["print"], "(no answer)")}
               for t in trig]
    told = [x["print"] for x in answers if x["print"] in a["answers"]]      # (a trigger left unanswered comes back)
    fac.say("situation.handled", handled_at=time.time(), summary=a["summary"][:2000], actions=done, answers=answers,
            prints=told + [x for x in sit["fields"].get("prints") or [] if x.startswith("broken-")],
            actions_n=sum(d["ok"] for d in done), velocity=record, context=context,
            ai_cost_usd=round(float(got.get("total_cost_usd") or 0), 4))
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
