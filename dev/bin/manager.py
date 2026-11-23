"""pipeline-manager: takes the situation pipeline-watch raised (watch.py) and has one AI session look at the whole
pipeline (dev/README.md, *The pipeline manager*): a brief of every trigger it carries (each gap's history, the broken
conditions), the pipeline around them, the velocity record and the researcher's answers, with the factory's
knowledge. The session's manage.py calls, from a fenced JSON block, are each run through manage.py's own checks as
`pipeline-manager`, at most [manager] most_actions; it says per trigger what it did or why it left it."""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import agents  # noqa: E402
import brief  # noqa: E402
import fac  # noqa: E402
import knowledge  # noqa: E402
import live  # noqa: E402
import load  # noqa: E402
import manage  # noqa: E402
import measure  # noqa: E402
import watch  # noqa: E402

ROLE = "pipeline_manager"
ANSWER = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
GOALS = (("queue-wait-hours", "queue-wait-short"), ("suite-minutes", "suites-in-time"),
         ("first-pass-yield", "first-pass-good"))      # the queue's goals and the review's, for the binding constraint
DETAILED = 6                                            # gaps given in full; the rest by their trigger's line
QUIET = 20 * 60                       # seconds with no merge while approved gaps wait: the brief names the queue's holder


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


def run_alive(cfg: dict, run: str) -> str:
    """Whether a lease's run still runs, from the engine's run record (runs/RUN.json: its pid and that pid's start, as
    ergostat/spec/runrecord.py writes them); a record or a start that cannot be read is unknown, never gone."""
    try:
        rec = json.loads((live.state_dir(cfg) / "runs" / f"{run}.json").read_text())
    except FileNotFoundError:
        return "no run record (the engine removes it when the run ends)"
    except (OSError, ValueError, AttributeError) as e:
        return f"unknown: its run record cannot be read ({type(e).__name__})"
    pid = int(rec.get("pid") or 0)
    try:
        if sys.platform.startswith("linux"):
            stat = Path(f"/proc/{pid}/stat")
            text = stat.read_text() if stat.exists() else ""
            rest = text[text.rfind(")") + 2:].split()               # (the name in brackets may hold spaces)
            start = rest[19] if len(rest) > 19 and rest[0] not in ("Z", "X") else None
        else:
            start = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                                   timeout=10).stdout.strip() or None
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return f"unknown: pid {pid} cannot be read ({type(e).__name__})"
    if not rec.get("start"):
        return f"unknown: its record has no start time for pid {pid}"
    return f"alive (pid {pid})" if start == rec["start"] else f"not running (pid {pid} ended, or is another process now)"


def queue_holder(cfg: dict, gaps: list[dict], now: float) -> str:
    """While approved gaps wait and nothing merged for QUIET: each lease the merge-queue block holds (its run, when
    taken, renewed and expiring, its item's state, whether its process lives) and the live readings of queue-when's
    inputs. "" otherwise."""
    approved = [g for g in gaps if g["state"] == "approved"]
    last = max([float(g["fields"].get("merged_at") or 0) for g in gaps] or [0])
    if not approved or now - last < QUIET:
        return ""
    rows = []
    for g in gaps:
        if (le := g["fields"].get("lease") or {}).get("holder") and le.get("block") == "merge-queue":
            merged = f", merged {utc(g['fields']['merged_at'])}" if g["fields"].get("merged_at") else ""
            rows.append(f"{g['id']} (state {g['state']}{merged}): run {le['holder']}, taken {utc(le.get('taken'))}, last "
                        f"renewed {utc(le.get('renewed'))} ({(now - float(le.get('renewed') or 0)) / 60:.0f} min ago), "
                        f"expires {utc(le.get('expires'))}; its process: {run_alive(cfg, le['holder'])}")
    inputs = [f"approved-gaps-landed: {len(approved)} approved gaps wait (hold <= 0)"]
    for w, goal in watch.INTERLOCK.items():
        try:
            inputs.append(f"{goal}: `load.py {w}` reads {load.reading(w):g} (hold <= {watch.hold('interlock.yaml', goal)})")
        except Exception as e:  # noqa: BLE001 - said as unreadable, never as within its limit
            inputs.append(f"{goal}: unreadable ({type(e).__name__}: {e})")
    try:
        got = subprocess.run([sys.executable, str(fac.HERE / "bin" / "queue.py"), "waiting"], capture_output=True,
                             text=True, timeout=60)
        inputs.append(f"push-waiting: `queue.py waiting` reads {got.stdout.strip()}" if got.returncode == 0 else
                      f"push-waiting: unreadable (exit {got.returncode}: {got.stderr.strip()[-200:]})")
    except (OSError, subprocess.SubprocessError) as e:
        inputs.append(f"push-waiting: unreadable ({type(e).__name__})")
    return (listed(f"What holds the merge queue (no merge for {(now - last) / 60:.0f} min while gaps wait)",
                   rows or ["no lease held by merge-queue"]) + "\n\n#" + listed("queue-when's inputs, read now", inputs))


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
              + tail(fac.run_dir(cfg, "queue"), "*.txt", 1000), queue_holder(cfg, gaps, time.time()),
              "## Main's recent commits\n\n```\n" + fac.git(repo, "log", "--oneline", "-12", cfg["git"]["base"],
                                                                check=False) + "\n```",
              listed("Open interventions", (f"{i['id']} ({i['fields'].get('class')}, by {i['fields'].get('by')}): "
                                            f"{str(i['fields'].get('reason'))[:300]}" for i in fac.items("intervention", "open"))),
              listed("Known flakes", (x["fields"].get("test", x["id"]) for x in fac.items("flake", "seen"))),
              listed("The pipeline (UTC)", (f"{g['id']} {g['state']} since {utc(g.get('entered'))}" for g in gaps
                                            if g["state"] not in ("merged", "parked", "closed", "open", "replan"))),
              f"## The velocity record\n\n```json\n{json.dumps(record, indent=1, default=str)}\n```"]
    return "\n\n".join(p for p in parts if p)


def reading(name: str):
    try:
        return measure.reading(name)
    except SystemExit:
        return None                                     # (no value yet)


def off(direction: str, sp: float, value: float) -> float:
    """How far a reading is from its goal, as a ratio: 1 on the setpoint, above 1 the wrong side of it. For a `>=` goal
    a reading of 0 is the worst case (setpoint over a hundredth), never on target."""
    eps = 0.01
    return round(sp / max(value, eps) if direction == ">=" else value / max(sp, eps), 2)


def velocity(cfg: dict, now: float | None = None) -> dict:
    """The merge pipeline's record: its measures, its batches, time in each state, each goal against its setpoint and
    the binding constraint, and the manager's own proposals and questions with their answers."""
    now = now or time.time()
    out: dict = {n: reading(n) for n in ("queue-wait-hours", "queue-minutes", "suite-minutes", "merges-per-hour",
                                         "first-pass-yield", "env-parks", "cycle-hours")}
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
    goals, unknown = {}, []
    for m, gname in GOALS:
        held = re.search(watch.HOLD.format(name=re.escape(gname)), (fac.HERE / "model" / "measures.yaml").read_text(),
                         re.M | re.S)
        if not held:                           # (renamed or reworded: said, and binding, never left out silently)
            goals[gname] = {"measure": m, "reading": out.get(m), "hold": None, "off": None,
                            "unknown": "no hold for this goal in dev/model/measures.yaml"}
            unknown.append(gname)
        elif out.get(m) is not None:
            goals[gname] = {"measure": m, "reading": out[m], "hold": f"{held[1]} {held[2]}",
                            "off": off(held[1], float(held[2]), float(out[m]))}
    out["goals"] = goals
    out["binding"] = unknown[0] if unknown else max((k for k in goals if goals[k]["off"] is not None),
                                                    key=lambda k: goals[k]["off"], default=None)
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
    prompt = (fac.HERE / "prompts" / f"{ROLE}.md").read_text().replace("{most}", str(most))
    know, carried = knowledge.block(cfg, ROLE, {"id": sit["id"], "fields": {"title": "the merge pipeline"}},
                                    f"{prompt}\n{text}")    # (the decisions the prompt names are matched by its words)
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
            finding=a["summary"][:2000],                   # (the attention list's: ergostat.yaml `attention: finding`)
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
