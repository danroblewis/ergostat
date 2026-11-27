"""``ergostat remote`` (SPEC §4c): this model's remote systems, each with where it runs, the version of its model
read, how it last answered and what of it this model names; ``ergostat remote token NAME`` makes a token another
ergostat reads this one with (printed once; ``--revoke`` removes it); ``ergostat remote events NAME`` the remote's
newest events, read in place."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from ..durations import human
from ..show import c, table
from .common import open_project, out_json


def register(sub, common) -> None:
    rp = sub.add_parser("remote", parents=[common], help="Remote systems: those this model reads (status), "
                        "token NAME (let another ergostat read this one), events NAME (a remote's newest events)",
                        description="Remote systems (SPEC §4c). ergostat remote [status | token NAME [--revoke] | "
                                    "tokens | events NAME [-n N] | refresh | proposals [NAME]]")
    rp.add_argument("what", nargs="?", default="status",
                    choices=["status", "token", "tokens", "events", "refresh", "proposals"])
    rp.add_argument("name", nargs="?", metavar="NAME",
                    help="token: the consumer it is for; events: the remote; proposals: only this remote's")
    rp.add_argument("--revoke", action="store_true", help="token NAME: remove it")
    rp.add_argument("-n", type=int, default=20, help="events: how many (default 20, at most 1000)")
    rp.set_defaults(fn=cmd_remote)


def _proposals(p, spec, remotes: dict, args) -> int:
    """``ergostat remote proposals [NAME]``: the changes found for remotes' parts, written as text for their owners
    (open and dismissed), each with the version it was written against and whether it is current. Read only: no lock
    taken, nothing superseded, nothing sent."""
    if args.revoke:
        print("--revoke is for ergostat remote token NAME", file=sys.stderr)
        return 2
    if args.name and args.name not in remotes:
        print(unknown(args.name, remotes), file=sys.stderr)
        return 2
    rows, unread = proposal_rows(p, spec, args.name)
    if args.json:
        return out_json(rows)
    for name in unread:
        print(c(f"remote {name}: its model's version can't be read, so nothing is written for it", "yellow"))
    if not rows:
        print("nothing written for a remote's owner" + (f" of {args.name}" if args.name else ""))
        return 0
    for i, x in enumerate(rows):
        fr = x["for_remote"]
        now = "current" if x["current"] else c(f"not current: {x['not_current_because']}", "yellow")
        print(("\n" if i else "") + f"{x['id']}  remote {fr['remote']}  written against version {fr['version']}  {now}"
              + (f"  (dismissed{': ' + x['dismissed_because'] if x.get('dismissed_because') else ''})"
                 if x["status"] == "dismissed" else ""))
        print(f"  {x['text']}")
    print(c("\nnever applied here, never sent by ergostat: sending it is the owner's act", "dim"))
    return 0


def unknown(name, remotes: dict) -> str:
    return f"no remote {name!r} (this model's: {', '.join(remotes) or 'none'})"


def proposal_rows(p, spec, name: str | None) -> tuple[list[dict], list[str]]:
    """The texts written for remotes' owners (open and dismissed, oldest first), as ``remote proposals --json`` lists
    them, and the remotes whose version can't be read. Read only."""
    from ..numbers import remote_text as rt
    return rt.listing(p, spec, name)


def status_row(name: str, r: dict) -> dict:
    """One remote as ``ergostat remote`` lists it, from the model's ``remotes:`` and its cache's status: read only."""
    from ..remote import cache
    st = cache.status(Path(r["dir"])) if r.get("dir") else {}
    return {"name": name, "url": r["url"], "version": r.get("version"), "read": r.get("fetched"),
            "ok": st.get("ok"), "why": st.get("why"), "checked": st.get("checked"),
            "readings": st.get("read"), "readings_ok": st.get("read_ok"), "readings_why": st.get("read_why"),
            "parts": len(r.get("parts") or {}), "missing": r.get("missing") or []}


def _ago(t) -> str:
    return human(max(0.0, time.time() - float(t))) + " ago" if t else "never"


def cmd_remote(args) -> int:
    p = open_project(args)
    if args.what in ("token", "tokens"):
        from ..remote import tokens
        if args.what == "tokens":
            rows = tokens.load(p.dir)
            if args.json:
                return out_json({k: {"made": v.get("made")} for k, v in rows.items()})
            if not rows:
                print("no tokens: the remote API is off (ergostat remote token NAME turns it on)")
            for k, v in sorted(rows.items()):
                print(f"{k}  made {_ago(v.get('made'))}")
            return 0
        if not args.name:
            print("ergostat remote token NAME: the consumer it is for (another ergostat, by its name)", file=sys.stderr)
            return 2
        if args.revoke:
            ok = tokens.revoke(p.dir, args.name)
            print(f"revoked {args.name}" if ok else f"no token {args.name}")
            return 0 if ok else 1
        tok = tokens.issue(p.dir, args.name)
        if args.json:
            return out_json({"name": args.name, "token": tok})
        print(tok)
        print(c(f"kept only as its hash; give it to {args.name}'s owner, who puts it in the file their remotes: entry "
                f"names (token-file:). This ergostat's page serves /api/remote/v1/ to it, read only.", "dim"), file=sys.stderr)
        return 0
    spec = getattr(p.model, "spec", None)
    remotes = getattr(spec, "remotes", None) or {}
    if args.what == "proposals":
        return _proposals(p, spec, remotes, args)
    if args.what == "refresh":
        from ..remote import cache
        for name, r in remotes.items():
            st = cache.refresh(Path(r["dir"]), r["url"], r.get("token_file"), spec.root, r["every"], force=True,
                               tls=r.get("tls"))
            print(f"{name}: " + (f"version {st.get('version')}" if st.get("ok") else f"did not answer: {st.get('why')}"))
        return 0
    if args.what == "events":
        if args.name not in remotes:
            print(unknown(args.name, remotes), file=sys.stderr)
            return 2
        from ..remote import events
        got, why = events.newest(spec, args.name, max(1, min(args.n, 1000)), force=True)
        if got is None:
            print(f"{args.name}: {why}", file=sys.stderr)
            return 1
        if args.json:
            return out_json(got)
        for e in got:
            print(f"{time.strftime('%H:%M:%S', time.localtime(e['time']))}  {e['type']:<28} {e.get('item') or ''}")
        return 0
    out = [status_row(name, r) for name, r in remotes.items()]
    if args.json:
        return out_json(out)
    if not out:
        print("no remotes: this model reads no other ergostat (remotes: in ergostat.yaml)")
        return 0
    rows = [[o["name"], o["url"], o["version"] or "-", f"{o['parts']}",
             ("answering" if o["ok"] else c("not answering", "red")) + f" (asked {_ago(o['checked'])})",
             _ago(o["readings"]) if o["readings_ok"] is not False else c(f"failing: {o['readings_why']}", "red")]
            for o in out]
    print(table(["remote", "url", "version", "parts", "model", "readings"], rows))
    for o in out:
        for m in o["missing"]:
            print(c(f"{o['name']}: {m['kind']}.{m['name']} is named here ({m['where']}) and not served by it", "yellow"))
    return 0
