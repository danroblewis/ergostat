"""The factory's measurements for Prometheus, at http://127.0.0.1:EXPORTER_PORT/metrics (./setup starts it, and
Prometheus scrapes it every 15 seconds).

From the record (read every 15 seconds):
    tf_tickets{state}                    tickets in each state
    tf_prs_awaiting_review               pull requests open and not approved
    tf_actions_waiting                   gated actions waiting for the owner
    tf_ci_failures_total                 CI failures, all tickets
    tf_repings_total                     reviewers asked again
    tf_review_rounds_total               reviews that asked for a change
    tf_ai_cost_usd_total                 dollars spent on AI sessions
    tf_ai_sessions_total                 AI sessions
    tf_ai_seconds_total                  seconds the AI sessions took
    tf_cycle_seconds_sum, _count         found to Done, of the tickets done (a summary: mean = sum / count)
    tf_step_seconds{state}               how long the ticket waiting longest in each state has waited
From the services (read every 60 seconds, so as not to load them):
    tf_jira_issues{status}               the labelled issues in Jira, by status
    tf_github_open_prs                   the factory's pull requests open on GitHub (its branch prefix)

    exporter.py [--once]                 serve (or print the page once)
"""

from __future__ import annotations

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import github
import jira
from tf import conf, items

PAGE = {"text": "# no reading yet\n"}
LOCK = threading.Lock()


def _line(name: str, value: float, **labels) -> str:
    lab = ",".join(f'{k}="{v}"' for k, v in labels.items())
    return f"{name}{{{lab}}} {value:g}" if lab else f"{name} {value:g}"


def from_record() -> list[str]:
    tickets = items("ticket")
    states: dict[str, int] = {}
    oldest: dict[str, float] = {}
    for t in tickets:
        states[t["state"]] = states.get(t["state"], 0) + 1
        if t["state"] not in ("done", "stopped") and t.get("entered"):
            oldest[t["state"]] = max(oldest.get(t["state"], 0), time.time() - t["entered"])

    def total(field):
        return sum(float(t["fields"].get(field) or 0) for t in tickets)
    done = [t for t in tickets if t["fields"].get("cycle_hours") is not None]
    out = ["# TYPE tf_tickets gauge"] + [_line("tf_tickets", n, state=s) for s, n in sorted(states.items())]
    out += ["# TYPE tf_prs_awaiting_review gauge",
            _line("tf_prs_awaiting_review", sum(states.get(s, 0) for s in ("pr-open", "review-asked", "changes-asked"))),
            "# TYPE tf_actions_waiting gauge", _line("tf_actions_waiting", len(items("ergostat.action", "requested")))]
    for name, field in (("ci_failures", "ci_failures"), ("repings", "repings"), ("review_rounds", "review_rounds"),
                        ("ai_cost_usd", "ai_cost_usd"), ("ai_sessions", "ai_runs"), ("ai_seconds", "ai_seconds")):
        out += [f"# TYPE tf_{name}_total counter", _line(f"tf_{name}_total", round(total(field), 6))]
    out += ["# TYPE tf_cycle_seconds summary",
            _line("tf_cycle_seconds_sum", round(sum(float(t["fields"]["cycle_hours"]) * 3600 for t in done), 1)),
            _line("tf_cycle_seconds_count", len(done)), "# TYPE tf_step_seconds gauge"]
    out += [_line("tf_step_seconds", round(v, 1), state=s) for s, v in sorted(oldest.items())]
    return out


def from_services() -> list[str]:
    out = ["# TYPE tf_jira_issues gauge"]
    try:
        out += [_line("tf_jira_issues", n, status=s) for s, n in sorted(jira.counts().items())]
    except Exception as e:                                       # noqa: BLE001: a service down is a gap, not a crash
        out.append(f"# jira: {type(e).__name__}")
    prefix = "ergostat/"                                         # the pool's branches (ergostat.yaml)
    try:
        n = sum(1 for p in github.open_prs(conf("GITHUB_REPO")) if p.get("headRefName", "").startswith(prefix))
        out += ["# TYPE tf_github_open_prs gauge", _line("tf_github_open_prs", n)]
    except Exception as e:                                       # noqa: BLE001
        out.append(f"# github: {type(e).__name__}")
    return out


def refresh(once: bool = False) -> None:
    services: list[str] = []
    last = 0.0
    while True:
        try:
            if time.time() - last >= 60:
                services, last = from_services(), time.time()
            text = "\n".join(from_record() + services) + "\n"
        except Exception as e:                                   # noqa: BLE001
            text = f"# reading failed: {type(e).__name__}: {e}\n"
        with LOCK:
            PAGE["text"] = text
        if once:
            return
        time.sleep(15)


class Page(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] != "/metrics":
            self.send_error(404)
            return
        with LOCK:
            body = PAGE["text"].encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> int:
    if "--once" in sys.argv:
        refresh(once=True)
        print(PAGE["text"], end="")
        return 0
    threading.Thread(target=refresh, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", int(conf("EXPORTER_PORT", "8796"))), Page).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
