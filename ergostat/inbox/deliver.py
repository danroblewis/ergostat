"""Sending what newly waits on a person to the channels ``notify:`` names (SPEC §12o), in a thread of its own (never
the engine's clock):

- entries new on a channel are held for ``group`` from the first of them, and then sent as one message;
- at most ``per-hour`` messages an hour per channel, and none in the ``quiet`` hours (what waits is sent after);
- each message is a gated action ``notify.CHANNEL``: its gate decides whether it is sent, held for the owner, or
  never sent (and then the entries count as told on that channel, so it is not asked again); one that failed is
  tried again with the next message (``notify-failing`` when the last three failed);
- a message says only each entry's id, kind, class, age and link, unless the channel says ``detail: full``: then its
  summary and why too, scrubbed as a report upstream is (``reports/scrub.py``);
- an entry waiting longer than ``wait-at-most`` is sent once more, to ``escalate-to`` (else every channel);
- each is recorded (``ergostat.notify.sent``: the channel, the entries, the action and how it went), and never about
  a ``notify.*`` action of its own: a held notification is not notified about."""

from __future__ import annotations

import json
import threading
import time

from ..durations import human
from . import entries as en

SENT = "ergostat.notify.sent"
HOUR = 3600.0
WORDS = {"action": "approval", "person": "request", "advise": "advised command", "steptest": "step test",
         "change": "model change", "request": "modelling request", "breaker": "tripped block"}
_SENDING = threading.Lock()


def quiet(n, now: float) -> bool:
    if not n.quiet:
        return False
    t = time.localtime(now)
    m, (a, b) = t.tm_hour * 60 + t.tm_min, n.quiet
    return a <= m < b if a <= b else (m >= a or m < b)


def message(n, es: list[dict], late: bool, base: str, scrub=None) -> tuple[str, str]:
    """The subject and the text: per entry its id, kind, class, age, link and how to answer it; with ``scrub`` (a
    channel's ``detail: full``) its summary and why too, scrubbed."""
    kinds: dict[str, int] = {}
    for e in es:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    subject = "ergostat: " + ", ".join(f"{k} {WORDS[w]}{'' if k == 1 else 's'}" for w, k in kinds.items()) + " waiting"
    if late:
        subject += f" longer than {human(n.wait_at_most)}"
    lines = [f"- {e['id']} ({WORDS[e['kind']]}, class {e['class']}), waiting {human(e['age'])}"
             + (f"\n  {e['warn']}" if e.get("warn") else "")              # (whatever the detail: SPEC §12r)
             + (f"\n  {scrub(e['summary'])}" + (f"\n  why: {scrub(e['why'])}" if e.get("why") else "") if scrub else "")
             + (f"\n  {base}{e['link']}" if base else "")
             + (f"\n  {en.command(e)}" if e["verbs"] else "") for e in es[:10]]
    if len(es) > 10:
        lines.append(f"... and {len(es) - 10} more: ergostat inbox")
    return subject, "\n".join(lines)


def body(kind: str, to: str, subject: str, text: str) -> str:
    if kind == "email":
        return f"To: {to}\nSubject: {subject}\n\n{text}\n"
    if kind == "slack":
        return json.dumps({"text": f"*{subject}*\n{text}"})
    if kind == "discord":
        return json.dumps({"content": f"**{subject}**\n{text}"[:2000]})
    return f"{subject}\n{text}"


def _send(p, spec, n, ch: str, es: list[dict], why: str, base: str) -> dict:
    from ..actions import gate
    c = n.channels[ch]
    scrub = None
    if c.get("detail") == "full":
        from ..reports.scrub import for_project
        scrub = for_project(p, spec).scrub
    subject, text = message(n, es, why == "late", base, scrub)
    a = gate.request(p, spec, f"notify.{ch}", {"subject": subject, "text": text,
                                               "body": body(c["type"], c["to"], subject, text)}, {"block": "ergostat"})
    return p.events.add(SENT, source="ergostat", data={"channel": ch, "entries": [e["id"] for e in es], "why": why,
                                                       "action": a["id"], "state": a["state"]})


def sweep(p, spec, now: float | None = None) -> int:
    """Send what is due; how many messages were asked for."""
    n, live = getattr(spec, "notify", None), now is None
    now = time.time() if live else now
    if n is None or not n.channels or quiet(n, now):
        return 0
    from ..runner import web_url
    es = [e for e in en.entries(p, spec, None if live else now) if not str(e.get("action") or "").startswith("notify.")]
    if not es:
        return 0
    sent = [e["data"] for e in p.events.query(n=2000, type=SENT) if e["data"].get("state") != "failed"]   # (retried)
    hour = [e["data"]["channel"] for e in p.events.query(n=None, type=SENT, since=now - HOUR)]
    base, k = n.base_url or (web_url(p) or "").rstrip("/"), 0
    for ch in n.channels:
        told = {i for s in sent if s["channel"] == ch for i in s["entries"]}
        new = [e for e in es if e["id"] not in told]
        if ch not in n.escalate_to and new and now - min(e["time"] for e in new) >= n.group and \
                hour.count(ch) < n.per_hour:
            _send(p, spec, n, ch, new, "new", base)
            hour.append(ch)
            k += 1
    late_told = {i for s in sent if s.get("why") == "late" for i in s["entries"]}
    late = [e for e in es if n.wait_at_most and e["age"] > n.wait_at_most and e["id"] not in late_told]
    for ch in (n.escalate_to or list(n.channels)) if late else []:
        if hour.count(ch) < n.per_hour:
            _send(p, spec, n, ch, late, "late", base)
            k += 1
    return k


def start(p, spec, say=print) -> None:
    """A sweep in a thread of its own, unless one is under way: a slow channel never holds up the engine."""
    if not _SENDING.acquire(blocking=False):
        return

    def run():
        try:
            sweep(p, spec)
        except Exception as e:
            say(f"notify: {type(e).__name__}: {e}")
        finally:
            _SENDING.release()
    threading.Thread(target=run, name="ergostat-notify", daemon=True).start()


def failing(p, spec) -> list[str]:
    """The channels whose last three messages failed (``notify-failing``)."""
    got: dict[str, list[str]] = {}
    for e in p.events.query(n=200, type=SENT):
        got.setdefault(e["data"]["channel"], []).append(e["data"].get("state"))
    return [ch for ch, st in got.items() if len(st) >= 3 and st[-3:] == ["failed"] * 3]
