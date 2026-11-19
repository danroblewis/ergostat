"""``notify:`` (main file only), checked, into ``spec.notify``; each channel becomes a gated action ``notify.NAME``
(SPEC §12o), so the owner's gate decides where anything may be sent. A webhook's URL is read from an environment
variable or a file when the message is sent, never written in the YAML."""

from __future__ import annotations

import os
import re
import shlex
import shutil
from dataclasses import dataclass, field

from ..spec.ir import GATES, NAME, Action

TYPES = ("macos", "email", "slack", "discord", "command")
KEYS = {"channels", "base-url", "group", "per-hour", "quiet", "wait-at-most", "escalate-to", "asks-per-day", "trend-window",
        "recurs", "verify", "standing"}
CHANNEL_KEYS = {"type", "gate", "to", "command", "url-env", "url-file", "run"}
QUIET = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ARGS = {"subject": "the message's first line", "text": "the message", "body": "the message as the channel takes it"}


@dataclass
class Notify:
    channels: dict[str, dict] = field(default_factory=dict)     # name → {type, to}
    base_url: str = ""
    group: float = 120.0
    per_hour: int = 6
    quiet: tuple[int, int] | None = None                        # minutes after midnight, from and to
    wait_at_most: float | None = None
    escalate_to: list[str] = field(default_factory=list)
    asks_per_day: int | None = None
    trend_window: float | None = None                           # the interventions loop's (SPEC §12p)
    recurs: int | None = None
    verify: float | None = None
    standing: float | None = None


def _brace(s: str) -> str:
    return s.replace("{", "{{").replace("}", "}}")


def command(kind: str, ch: dict) -> str:
    """The channel's command template: ``{subject}``, ``{text}`` and ``{body}`` filled, each shell-quoted."""
    if kind == "macos":
        if shutil.which("terminal-notifier"):
            return "terminal-notifier -title {subject} -message {text}"
        return ("osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' "
                "-e 'end run' {subject} {text}")
    if kind == "email":
        return "printf '%s' {body} | " + _brace(str(ch.get("command") or "sendmail -t"))
    if kind in ("slack", "discord"):
        url = (f'"${ch["url-env"]}"' if ch.get("url-env")
               else f'"$(cat {shlex.quote(os.path.expanduser(str(ch["url-file"])))})"')
        return "curl -sS -f -m 20 -X POST -H 'Content-Type: application/json' --data-binary {body} " + _brace(url)
    return "printf '%s\\n' {body} | " + _brace(str(ch["run"]))


def parse(c, spec) -> None:
    m = c.doc.notify
    if m is None:
        return
    if not isinstance(m, dict):
        c.err(f"notify: a map ({', '.join(sorted(KEYS))})", None, "not-a-map")
        return
    c.keys(m, KEYS, "notify")
    n = Notify(base_url=str(m.get("base-url") or "").rstrip("/"), group=c.duration(m, "group", "notify", 120.0),
               wait_at_most=c.duration(m, "wait-at-most", "notify"))
    for key in ("trend-window", "verify", "standing"):
        setattr(n, key.replace("-", "_"), c.duration(m, key, "notify"))
    for key, attr in (("per-hour", "per_hour"), ("asks-per-day", "asks_per_day"), ("recurs", "recurs")):
        v = c.number(m, key, "notify", positive=True)
        if v is not None:
            setattr(n, attr, int(v))
    if m.get("quiet") is not None:
        q = QUIET.match(str(m["quiet"]).replace(" ", ""))
        if not q or int(q[1]) > 23 or int(q[3]) > 23 or int(q[2]) > 59 or int(q[4]) > 59:
            c.err("notify.quiet: the hours nothing is sent, from-to in local time (22:00-07:00)", m.at("quiet"), "bad-value")
        else:
            n.quiet = (int(q[1]) * 60 + int(q[2]), int(q[3]) * 60 + int(q[4]))
    chans = m.get("channels") or {}
    if not isinstance(chans, dict):
        c.err("notify.channels: a map of each channel's name to its type: and settings", m.at("channels"), "not-a-map")
        chans = {}
    for name, ch in chans.items():
        what = f"notify.channels.{name}"
        if not isinstance(ch, dict) or not NAME.match(str(name)):
            c.err(f"{what}: a channel is named in lowercase letters, digits and -, and is a map (type: ...)",
                  chans.at(name), "bad-value")
            continue
        c.keys(ch, CHANNEL_KEYS, what)
        kind, gate = str(ch.get("type") or ""), str(ch.get("gate") or "auto")
        need = {"email": ["to"], "command": ["run"]}.get(kind, [])
        if kind not in TYPES:
            c.err(f"{what}.type: one of {', '.join(TYPES)}", ch.at("type"), "bad-value")
            continue
        if kind in ("slack", "discord") and bool(ch.get("url-env")) == bool(ch.get("url-file")):
            c.err(f"{what}: url-env: (an environment variable) or url-file: (a file) holding the webhook's URL; the URL "
                  "itself is never written in the model", ch.where, "missing-key")
            continue
        if ch.get("url-env") and not ENV.match(str(ch["url-env"])):
            c.err(f"{what}.url-env: the name of an environment variable", ch.at("url-env"), "bad-value")
            continue
        if any(not ch.get(k) for k in need):
            c.err(f"{what}: {kind} needs {', '.join(need)}:", ch.where, "missing-key")
            continue
        if gate not in GATES:
            c.err(f"{what}.gate: auto (sent), approve (held until the owner approves) or deny (never sent)",
                  ch.at("gate"), "bad-value")
            gate = "deny"
        n.channels[name] = {"type": kind, "to": str(ch.get("to") or "")}
        spec.actions[f"notify.{name}"] = Action(f"notify.{name}", command(kind, ch), gate, "notify", dict(ARGS), 30.0,
                                                0.0, None, f"a notification, by {kind}", ch.where)
    esc = m.get("escalate-to") or []
    for e in [esc] if isinstance(esc, str) else esc:
        if str(e) in n.channels:
            n.escalate_to.append(str(e))
        else:
            c.err(f"notify.escalate-to: {e!r} is not one of the channels:" + c.suggest(str(e), n.channels),
                  m.at("escalate-to"), "unknown-ref")
    spec.notify = n
