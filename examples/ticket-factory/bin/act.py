"""Gated actions: the only way the factory acts on Jira or GitHub.

Every outward act is a named action (jira.transition, github.open-pr, ...), and each name has a gate in
gates.conf: `auto` (done at once), `approve` (asked, and done once the owner approves it) or `deny` (never
done; the step says so and goes on, or stops). gates.local.conf, ignored by git, overrides it: that is
where the owner promotes a gate on one laptop. Each action is an item, action/<ticket>.<step>.<name>.<hash>,
so what was asked, approved, done, denied or failed is in the record, and the same act is never done twice:
a step that runs again finds its action done and takes the result.

    act.py list                   the actions waiting for approval
    act.py approve ID ... | --all approve them (as the owner); the step that asked does it on its next run
    act.py deny ID ... [--why W]  deny them
    act.py gates                  every action's gate, as it stands here

PLUG POINT (branch `workspaces`, SPEC 12k): ergostat's `actions:` (a command template each, with `gate: auto |
approve | deny`, approved with `ergostat actions ID --approve`) replace this file, one name for one name; the
steps' act(name, ...) calls then ask ergostat, and the gates move from gates.conf into the model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from tf import OFFLINE, ROOT, item, items, record

GATES = ("auto", "approve", "deny")


class Pending(Exception):
    """The action waits for the owner's approval."""


class Denied(Exception):
    """The action's gate is `deny`, or the owner denied it."""


class Failed(Exception):
    pass


def gates() -> dict[str, str]:
    """Each action's gate: gates.conf (its second column offline), then gates.local.conf over it."""
    out: dict[str, str] = {}
    for name in ("gates.conf", "gates.local.conf"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            words = line.split("#", 1)[0].split()
            if len(words) < 2:
                continue
            gate = words[2] if OFFLINE and len(words) > 2 else words[1]
            if gate not in GATES:
                sys.exit(f"{name}: {words[0]}: the gate is auto, approve or deny, not {gate!r}")
            out[words[0]] = gate
    return out


def gate_of(name: str) -> str:
    return gates().get(name, "approve")                    # an action no one listed asks first


def action_id(ticket: str, step: str, name: str, extra: str = "") -> str:
    h = hashlib.sha1(f"{ticket}|{step}|{name}|{extra}".encode()).hexdigest()[:6]
    return f"action/{ticket}.{step}.{name.replace('.', '-')}.{h}"


def act(name: str, ticket: str, step: str, what: str, fn, *args, extra: str = ""):
    """Do `fn(*args)`, the action `name`, under its gate; `what` says it in a sentence for the owner. Returns
    what it returned (or what it returned the first time). Raises Pending, Denied or Failed."""
    aid = action_id(ticket, step, name, extra)
    known = item(aid)
    state = known["state"] if known else None
    fields = known["fields"] if known else {}
    if state == "done":
        return fields.get("result")
    if state == "denied":
        raise Denied(f"{what}: denied ({fields.get('why') or 'its gate is deny'})")
    if state == "requested":
        raise Pending(f"{what}: waiting for approval ({aid})")
    gate = gate_of(name)
    about = {"name": name, "ticket": f"ticket/{ticket}", "step": step, "what": what, "gate": gate}
    if state is None and gate == "deny":
        record("action.denied", aid, {**about, "why": "its gate is deny"}, by="gate")
        raise Denied(f"{what}: its gate is deny")
    if state is None and gate == "approve":
        record("action.requested", aid, about, by="gate")
        raise Pending(f"{what}: waiting for approval ({aid})")
    if state == "failed" and gate != "auto" and not fields.get("approved_by"):
        raise Pending(f"{what}: failed before; waiting for approval to try again")
    try:
        result = fn(*args)
    except Exception as e:                                               # noqa: BLE001: recorded, then raised
        record("action.failed", aid, {**about, "error": str(e)[:500]}, by="gate")
        raise Failed(f"{what}: {e}") from None
    if isinstance(result, (dict, list)):
        result = json.loads(json.dumps(result))
    record("action.done", aid, {**about, "result": result}, by="gate")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=["list", "approve", "deny", "gates"])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--why", default="denied by the owner")
    a = ap.parse_args()
    if a.what == "gates":
        for name, gate in sorted(gates().items()):
            print(f"{name:24} {gate}")
        return 0
    waiting = items("action", "requested")
    if a.what == "list":
        for it in waiting:
            print(f"{it['id']}\n    {it['fields'].get('what')}  (gate {it['fields'].get('gate')})")
        print(f"{len(waiting)} waiting for approval" + (": bin/act.py approve ID, or --all" if waiting else ""))
        return 0
    ids = [w["id"] for w in waiting] if a.all else a.ids
    for aid in ids:
        if not aid.startswith("action/"):
            aid = "action/" + aid
        if a.what == "approve":
            record("action.approved", aid, {"approved_by": "owner"}, by="owner")
        else:
            record("action.denied", aid, {"why": a.why, "denied_by": "owner"}, by="owner")
        print(f"{'approved' if a.what == 'approve' else 'denied'} {aid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
