"""``intake:`` as written (main file only), checked (docs/proposals/latency.md):

    intake:
      allow: [10.0.0.0/8]        # who may push besides this machine (default: nobody else)
      bind: 0.0.0.0              # where the page listens (default 127.0.0.1); others reach only the push paths
      hooks:                     # POST /api/hooks/NAME: a sender's payload made into an event (hooks.py)
        jira:
          event: {from: webhookEvent, map: {"jira:issue_created": ticket.found, "jira:issue_updated": ticket.changed}}
          item: "ticket/{issue.key}"
          id: "jira-{issue.id}-{timestamp}"
          data: {title: issue.fields.summary, status: issue.fields.status.name}
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field


@dataclass
class Hook:
    name: str
    event: str | None = None                      # a template ("pr.{action}"), or
    event_from: str | None = None                 # a path (or header:NAME) whose value ``event_map`` names the type of
    event_map: dict[str, str] = field(default_factory=dict)
    item: str | None = None                       # a template
    id: str | None = None                         # a template: the same delivery again is the same event
    data: dict[str, str] = field(default_factory=dict)   # field → a path, or a template
    each: str | None = None                       # a path to a list: one event per element (it is the payload then)
    source: str | None = None


@dataclass
class Intake:
    allow: list[str] = field(default_factory=list)
    bind: str = "127.0.0.1"
    hooks: dict[str, Hook] = field(default_factory=dict)


def parse(raw, problems: list[str]) -> Intake:
    out = Intake()
    if raw is None:
        return out
    if not isinstance(raw, dict):
        problems.append("intake: a map (allow:, bind:, hooks:)")
        return out
    for k in raw:
        if k not in ("allow", "bind", "hooks"):
            problems.append(f"intake: unknown key {k!r} (known: allow, bind, hooks)")
    allow = raw.get("allow") or []
    allow = [allow] if isinstance(allow, str) else allow
    for a in allow if isinstance(allow, list) else [allow]:
        try:
            ipaddress.ip_network(str(a), strict=False)
            out.allow.append(str(a))
        except ValueError:
            problems.append(f"intake.allow: {a!r} is not an address or a network (10.0.0.0/8)")
    if raw.get("bind") is not None:
        try:
            ipaddress.ip_address(str(raw["bind"]))
            out.bind = str(raw["bind"])
        except ValueError:
            problems.append(f"intake.bind: {raw['bind']!r} is not an address (0.0.0.0, 127.0.0.1)")
    hooks = raw.get("hooks") or {}
    if not isinstance(hooks, dict):
        problems.append("intake.hooks: a map of sender name to its mapping")
        hooks = {}
    for name, h in hooks.items():
        where = f"intake.hooks.{name}"
        if not isinstance(h, dict):
            problems.append(f"{where}: a map (event:, item:, id:, data:)")
            continue
        for k in h:
            if k not in ("event", "item", "id", "data", "each", "source"):
                problems.append(f"{where}: unknown key {k!r} (known: event, item, id, data, each, source)")
        hk = Hook(str(name), item=_s(h.get("item")), id=_s(h.get("id")), each=_s(h.get("each")),
                  source=_s(h.get("source")))
        ev = h.get("event")
        if isinstance(ev, dict):
            if not isinstance(ev.get("from"), str) or not isinstance(ev.get("map"), dict):
                problems.append(f"{where}.event: a type (\"pr.{{action}}\"), or {{from: PATH, map: {{VALUE: TYPE}}}}")
            else:
                hk.event_from, hk.event_map = ev["from"], {str(k): str(v) for k, v in ev["map"].items()}
        elif isinstance(ev, str):
            hk.event = ev
        else:
            problems.append(f"{where}.event: the event type to record (a template, or from: and map:)")
        data = h.get("data") or {}
        if not isinstance(data, dict):
            problems.append(f"{where}.data: a map of field to a path in the payload (issue.fields.summary)")
        else:
            hk.data = {str(k): str(v) for k, v in data.items()}
        out.hooks[str(name)] = hk
    return out


def _s(v) -> str | None:
    return None if v is None else str(v)
