"""The MCP server ergostat runs for a gated session (SPEC §12k): ``python -m ergostat.actions.server``, started by
Claude Code from the session's ``--mcp-config``, ``$ERGOSTAT_SANDBOX`` naming what the session was given. It serves each
action the block may ask for as a tool of that name (its arguments, its description), and ``action_status`` (an action
asked for before, as it stands now). A call is the gate's (``gate.request``): an ``approve`` action waits here for the
owner, up to its ``wait:``, and runs once approved, its output the call's answer; a wait that runs out says the action
is held, and its result goes to the block's next run."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from .. import __version__
from . import gate as gt
from . import record as rec
from . import sandbox as sb

PROTOCOL = "2025-06-18"


def _text(x, error: bool = False) -> dict:
    out = {"content": [{"type": "text", "text": x if isinstance(x, str) else json.dumps(x, indent=1, default=str)}]}
    return {**out, "isError": True} if error else out


class Server:
    def __init__(self, cfg: dict, session: str | None = None):
        self.cfg, self.session = cfg, session
        self._p = None

    def project(self):
        if self._p is None:
            from .. import model as mdl
            from ..store import Project
            self._p = Project(mdl.load(Path(self.cfg["root"])), Path(self.cfg["state"]))
        return self._p

    def spec(self):
        return self.project().model.spec

    def tools(self) -> list[dict]:
        spec = self.spec()
        out = []
        for name in self.cfg.get("actions") or []:
            a = spec.actions.get(name)
            if a is None:
                continue
            gate = {"auto": "it runs at once", "approve": "it is held until the owner approves it, then runs",
                    "deny": "it is denied: never run"}[a.gate] + \
                ("; held or denied when this act is riskier than its class" if a.severity is not None else "")
            out.append({"name": name, "description": f"{a.description or name} (gated: {gate}; its output is the answer). "
                        f"The only way to do this: do not try it any other way.",
                        "inputSchema": {"type": "object", "properties": {k: {"type": "string", "description": v}
                                                                         for k, v in a.args.items()},
                                        "required": list(a.args)}})
        out.append({"name": "action_status", "description": "An action asked for before, as it stands now (held, "
                    "approved, ran with its output, failed, denied), by its id (ergostat.action/...).",
                    "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}})
        return out

    def say(self, a: dict) -> dict:
        r = gt.result(a)
        if a["state"] in ("ran", "failed", "denied"):
            gt.delivered(self.project(), a["id"], "session", session=self.session, run=self.cfg.get("run"),
                         block=self.cfg.get("block"))
        if a["state"] == "requested":
            r["note"] = (f"held for the owner's approval as {a['id']}; it has not run. Go on with what does not need it; "
                         f"action_status tells you if it ran later, and the block's next run is told its result")
        return _text(r, error=a["state"] in ("failed", "denied"))

    def call(self, name: str, args: dict) -> dict:
        p = self.project()
        if name == "action_status":
            a = rec.get(p, str(args.get("id") or ""))
            if a is None or a.get("block") != self.cfg.get("block"):
                return _text(f"no action {args.get('id')!r} of this block", error=True)
            return self.say(a)
        if name not in (self.cfg.get("actions") or []):
            return _text(f"no action {name!r} for this session", error=True)
        spec = self.spec()
        ctx = {k: self.cfg.get(k) for k in ("block", "run", "item", "workdir", "branch", "lease")}
        ctx["session"] = self.session
        try:
            a = gt.request(p, spec, name, args or {}, ctx)
        except gt.GateError as e:
            return _text(str(e), error=True)
        if a["state"] == "requested":
            a = gt.wait(p, spec, a["id"], spec.actions[name].wait)
        return self.say(a)

    def handle(self, msg: dict) -> dict | None:
        mid, method = msg.get("id"), msg.get("method", "")
        if mid is None:
            return None
        try:
            if method == "initialize":
                result = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTOCOL,
                          "capabilities": {"tools": {}}, "serverInfo": {"name": "ergostat-actions", "version": __version__},
                          "instructions": "The outward acts this session may ask for (push, open a pull request, move a "
                                          "ticket, post a message), each gated: it runs only as its gate lets it. They "
                                          "are the only way to make these acts here."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                params = msg.get("params") or {}
                try:
                    result = self.call(params.get("name", ""), params.get("arguments") or {})
                except Exception as e:
                    result = _text(f"{type(e).__name__}: {e}", error=True)
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(cfg: dict, session: str | None = None, inp=None, out=None) -> int:
    """Line by line; a tool call answered on a thread of its own (it may wait for the owner), so the server goes on
    answering meanwhile."""
    inp, out = inp or sys.stdin, out or sys.stdout
    s = Server(cfg, session)
    lock = threading.Lock()
    calls: list[threading.Thread] = []

    def send(reply: dict | None) -> None:
        if reply is not None:
            with lock:
                out.write(json.dumps(reply, default=str) + "\n")
                out.flush()
    for line in inp:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}})
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("method") == "tools/call":
            t = threading.Thread(target=lambda m=msg: send(s.handle(m)), daemon=True)
            t.start()
            calls.append(t)
        else:
            send(s.handle(msg))
    for t in calls:
        t.join()
    return 0


def main() -> int:
    f = os.environ.get("ERGOSTAT_SANDBOX")
    if not f:
        print("ergostat.actions.server: $ERGOSTAT_SANDBOX names the session's sandbox file", file=sys.stderr)
        return 2
    return serve({**sb.load(f), "file": f}, os.environ.get("ERGOSTAT_SESSION") or None)


if __name__ == "__main__":
    sys.exit(main())
