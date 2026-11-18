"""The daily summary and the OKR, from the counts in the record (the reporter block, every 30 seconds).

- report/<date>: reports/<date>.md (shown rendered on the Items page), and its numbers as fields;
- okr/<year>-Q<n>: the objective, each key result against its target, and the status (on-track, at-risk,
  off-track: the item's state).

Targets: OKR_DONE (tickets Done this quarter, default 3), OKR_CYCLE_HOURS (median cycle time, 1),
OKR_REPINGS (re-pings per pull request, 1), OKR_FIRST_PASS (the share passing CI first time, 0.5) and
OKR_COST (AI dollars per ticket, 0.25), in factory.conf or TF_<KEY>."""

from __future__ import annotations

import statistics
import sys
import time

from tf import REPORTS, conf, item, items, say

OBJECTIVE = "Labelled tickets go from pick-up to Done with no hands on the keyboard"


def day_of(t: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(t))


def quarter_of(t: float) -> str:
    lt = time.localtime(t)
    return f"{lt.tm_year}-Q{(lt.tm_mon - 1) // 3 + 1}"


def money(x: float) -> str:
    return f"${x:.4f}"


def key_results(tickets: list[dict]) -> list[dict]:
    q = quarter_of(time.time())
    done = [t for t in tickets if t["state"] == "done" and quarter_of(t["fields"].get("done_at") or 0) == q]
    cycles = [float(t["fields"].get("cycle_hours") or 0) for t in done]
    prs = [t for t in tickets if t["fields"].get("pr")]
    repings = sum(int(t["fields"].get("repings") or 0) for t in prs)
    first = [t for t in done if not t["fields"].get("ci_failures")]
    cost = sum(float(t["fields"].get("ai_cost_usd") or 0) for t in done)

    def kr(name, value, target, better, shown):
        met = None if value is None else (value >= target if better == "more" else value <= target)
        return {"kr": name, "value": value, "target": target, "met": met, "shown": shown}
    return [
        kr("tickets Done this quarter", len(done), float(conf("OKR_DONE", "3")), "more", f"{len(done)}"),
        kr("median cycle time (h)", statistics.median(cycles) if cycles else None, float(conf("OKR_CYCLE_HOURS", "1")),
           "less", f"{statistics.median(cycles):.2f} h" if cycles else "no ticket done"),
        kr("re-pings per pull request", repings / len(prs) if prs else None, float(conf("OKR_REPINGS", "1")), "less",
           f"{repings / len(prs):.2f}" if prs else "no pull request"),
        kr("share passing CI first time", len(first) / len(done) if done else None,
           float(conf("OKR_FIRST_PASS", "0.5")), "more", f"{len(first) / len(done):.0%}" if done else "no ticket done"),
        kr("AI dollars per ticket", cost / len(done) if done else None, float(conf("OKR_COST", "0.25")), "less",
           money(cost / len(done)) if done else "no ticket done"),
    ]


def status(krs: list[dict]) -> tuple[str, str]:
    met = sum(1 for k in krs if k["met"])
    known = sum(1 for k in krs if k["met"] is not None)
    if known <= 1:
        return "at-risk", "nothing Done yet this quarter"
    if met >= 4:
        return "on-track", f"{met} of 5 key results met"
    return ("at-risk" if met >= 2 else "off-track"), f"{met} of 5 key results met"


def summary(today: str, tickets: list[dict], krs: list[dict], okr_state: str) -> str:
    done = [t for t in tickets if t["state"] == "done" and day_of(t["fields"].get("done_at") or 0) == today]
    flight = {}
    for t in tickets:
        if t["state"] not in ("done",):
            flight[t["state"]] = flight.get(t["state"], 0) + 1
    waiting = items("ergostat.action", "requested")
    lines = [f"# The ticket factory, {today}", "", f"_Written {time.strftime('%H:%M')}, from the record._", "",
             f"## Done today: {len(done)}", ""]
    for t in done:
        f = t["fields"]
        lines.append(f"- **{f.get('key')}** {f.get('title', '')}: [pull request]({f.get('pr_url', '')}), "
                     f"{'merged' if f.get('merged') else 'not merged'}; {float(f.get('cycle_hours') or 0) * 60:.1f} min; "
                     f"{int(f.get('repings') or 0)} re-ping(s); {int(f.get('ci_failures') or 0)} CI failure(s); "
                     f"AI {money(float(f.get('ai_cost_usd') or 0))}")
    lines += ["", "## In flight", "", "| state | tickets |", "|---|---|"]
    lines += [f"| {s} | {n} |" for s, n in flight.items()] or ["| (none) | 0 |"]
    if waiting:
        lines += ["", f"## Waiting for your approval: {len(waiting)}", ""]
        lines += [f"- `{a['id']}`: {a['fields'].get('action')}, `{(a['fields'].get('command') or '')[:120]}`"
                  for a in waiting]
    stopped = [t for t in tickets if t["state"] == "stopped"]
    if stopped:
        lines += ["", f"## Stopped: {len(stopped)}", ""]
        lines += [f"- **{t['fields'].get('key')}** at {t['fields'].get('stopped_at')}: {t['fields'].get('stopped_why')}"
                  for t in stopped]
    spent = sum(float(t["fields"].get("ai_cost_usd") or 0) for t in tickets)
    runs = sum(int(t["fields"].get("ai_runs") or 0) for t in tickets)
    lines += ["", "## AI", "", f"{runs} session(s), {money(spent)} in all ({conf('AI')}"
              + (f", {conf('AI_MODEL')}" if conf("AI") == "claude" else "") + ")."]
    lines += ["", f"## OKR ({okr_state})", "", f"**{OBJECTIVE}**", "", "| key result | now | target | |", "|---|---|---|---|"]
    lines += [f"| {k['kr']} | {k['shown']} | {k['target']:g} | {'met' if k['met'] else ('-' if k['met'] is None else 'not yet')} |"
              for k in krs]
    return "\n".join(lines) + "\n"


def main() -> int:
    tickets = items("ticket")
    today = day_of(time.time())
    krs = key_results(tickets)
    state, note = status(krs)
    text = summary(today, tickets, krs, state)
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"{today}.md"
    new_day = not path.exists()
    path.write_text(text)
    done_today = sum(1 for t in tickets if t["state"] == "done" and day_of(t["fields"].get("done_at") or 0) == today)
    fields = {"summary": f"file:reports/{today}.md", "done": done_today,
              "repings": sum(int(t["fields"].get("repings") or 0) for t in tickets),
              "ci_failures": sum(int(t["fields"].get("ci_failures") or 0) for t in tickets),
              "ai_cost_usd": round(sum(float(t["fields"].get("ai_cost_usd") or 0) for t in tickets), 6),
              "cycle_hours_median": krs[1]["value"]}
    rid = f"report/{today}"
    was = item(rid)
    if not was or any(was["fields"].get(k) != v for k, v in fields.items()):
        say({"event": "report.written", "item": rid, "data": fields})
    oid = f"okr/{quarter_of(time.time())}"
    okr = {"objective": OBJECTIVE, "done": krs[0]["value"], "target": krs[0]["target"], "status_note": note,
           "key_results": [{k: v for k, v in kr.items() if k != "value"} for kr in krs]}
    was = item(oid)
    if not was or was["state"] != state or any(was["fields"].get(k) != v for k, v in okr.items()):
        say({"event": f"okr.{state}", "item": oid, "data": okr})
    say({"moved": 1 if new_day else 0})
    return 0


if __name__ == "__main__":
    sys.exit(main())
