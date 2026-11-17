"""``ergostat mcp``: ergostat as an MCP server (stdio, JSON-RPC 2.0, one message per line), so an
AI agent can read the model, check what it writes, explain any part, see what is happening and
what is worth a look, and report the work a person block was asked for.

Every call loads the model afresh from the project's files, so an agent editing ``ergostat.yaml``
sees its change at the next call. Nothing here starts or stops ergostat."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import __version__
from . import model as mdl

PROTOCOL = "2025-06-18"


def _text(x) -> dict:
    return {"content": [{"type": "text", "text": x if isinstance(x, str) else json.dumps(x, indent=2, default=str)}]}


def _obj(props: dict | None = None, required: list | None = None) -> dict:
    return {"type": "object", "properties": props or {}, **({"required": required} if required else {})}


TOOLS = [
    {"name": "check", "description": "Compile the project's ergostat.yaml and every file it includes. Returns the errors "
     "(each with file and line; ergostat will not run the model until they are fixed) and the findings (missing feedback, "
     "a block with no visible effect, an open loop, ...). Call it after every edit.", "inputSchema": _obj()},
    {"name": "explain", "description": "The model, or one part of it, in sentences: what it is, what measures it, what serves "
     "it, what it is doing now. part: a goal, block, stock, flow or auxiliary, as goal.x or just x; leave it out for the "
     "whole model, with its feedback loops (each R reinforcing, B balancing, or of unknown sign).",
     "inputSchema": _obj({"part": {"type": "string"}})},
    {"name": "status", "description": "Every goal now: its value, setpoint, error and status (holding or off), and whether "
     "a loop ergostat can see closes it.", "inputSchema": _obj()},
    {"name": "findings", "description": "What is worth a look, from the model and from the record: missing feedback, a stock "
     "heading for its limit (with the time left), blocks saturating or failing, a person not answering, a critical goal "
     "decaying. since: the window, like 6h (default).", "inputSchema": _obj({"since": {"type": "string"}})},
    {"name": "events", "description": "The record, newest last: loop.off and loop.holding (a goal crossing its setpoint), "
     "block.commanded, valve.opened (what a block moved), controller.decided, agent.ran, person.asked, ...",
     "inputSchema": _obj({"n": {"type": "integer"}, "type": {"type": "string", "description": "a type, or a prefix glob: loop.*"},
                          "item": {"type": "string"}})},
    {"name": "spec", "description": "The format's specification (docs/SPEC.md): read it before writing or changing "
     "ergostat.yaml.", "inputSchema": _obj()},
    {"name": "improve_model", "description": "How to review the model as system dynamics would and propose edits that "
     "improve its structure (missing stocks, outflows, delays, perceived values, converting auxiliaries): the "
     "improve-model skill, then the guidelines it applies (docs/MODELLING.md). Read it when asked to review or improve "
     "the model, or when check reports structure findings. It proposes edits; the owner approves each.",
     "inputSchema": _obj()},
    {"name": "residuals", "description": "What each stock's readings did over the window against what its known flows "
     "explain: changed, explained, unexplained, and whether the unexplained part is significant (evidence of a flow or "
     "stock the model is missing, or of a sensor reading wrongly). since: the window, like 6h (default 1h).",
     "inputSchema": _obj({"since": {"type": "string"}})},
    {"name": "fit", "description": "How well the model's replay follows the record (each stock integrated from its flows, "
     "every written equation worked out, everything else as measured): per stock and in total, R², MAPE and Theil's U_M "
     "(bias), U_S (unequal variation), U_C (unequal covariation); each equation against its own readings; and the "
     "proposals waiting for the owner (parameters estimated, equations fitted). Read only: the owner accepts. since: the "
     "window, like 6h (default 1h).",
     "inputSchema": _obj({"since": {"type": "string"}})},
    {"name": "report_done", "description": "Report the work a person block was asked for (type: person): how much was moved "
     "along its flow. The same as `ergostat block NAME --done N`.",
     "inputSchema": _obj({"block": {"type": "string"}, "moved": {"type": "number"}, "note": {"type": "string"}},
                         ["block", "moved"])},
    {"name": "read_sensor", "description": "Record a reading of a manual sensor (manual: true), named as its stock and sensor: "
     "inbox.eyes. The same as `ergostat sensor inbox.eyes --read V`.",
     "inputSchema": _obj({"sensor": {"type": "string"}, "value": {"type": "number"}}, ["sensor", "value"])},
    {"name": "items", "description": "The items (the record folded by id: ticket/12, github/pull_request/4231): each kind's "
     "count per state, and the items with their state and fields. kind and state filter; id gives one item with its "
     "moves between states and its events.",
     "inputSchema": _obj({"kind": {"type": "string"}, "state": {"type": "string"}, "id": {"type": "string"},
                          "n": {"type": "integer"}})},
    {"name": "record_event", "description": "Record something that happened outside: an event of a type (ticket.opened), "
     "about an item (ticket/12), with data (its fields: title, priority, ...). An item kind's on: map says which types move "
     "an item between states. The same as `ergostat event --add TYPE --item ID --data JSON`.",
     "inputSchema": _obj({"type": {"type": "string"}, "item": {"type": "string"}, "data": {"type": "object"},
                          "source": {"type": "string"}}, ["type"])},
]


class Server:
    def __init__(self, root: Path):
        self.root = root

    def project(self):
        from .store import Project
        m = mdl.load(self.root)
        if getattr(m, "spec", None) is None:
            raise RuntimeError("this project is still ergostat.toml; ergostat convert writes it as ergostat.yaml")
        return Project(m)

    def call(self, name: str, a: dict) -> dict:
        if name == "check":
            from .spec import read
            path = mdl.find(self.root)
            if path is None or path.name != mdl.YAML:
                return _text(f"no {mdl.YAML} here or above {self.root}")
            spec, problems = read(path)
            return _text({"ok": not any(p.level == "error" for p in problems),
                          "problems": [{"level": p.level, "code": p.code, "message": p.message, "about": p.about,
                                        "file": str(p.where.file) if p.where else None,
                                        "line": p.where.line if p.where else None} for p in problems],
                          "counts": {"stocks": len(spec.stocks), "flows": len(spec.flows), "auxiliaries": len(spec.auxiliaries),
                                     "goals": len(spec.goals),
                                     "blocks": len(spec.blocks), "files": len(spec.files)}})
        if name == "spec":
            from . import helpdocs
            return _text(helpdocs.read("spec") or "the specification is docs/SPEC.md in the ergostat repository")
        if name == "improve_model":
            from . import helpdocs
            skill, guide = helpdocs.read("improve-model"), helpdocs.read("modelling")
            return _text("\n\n".join(x for x in (skill, guide) if x) or "the guidelines are docs/MODELLING.md in the "
                         "ergostat repository")
        p = self.project()
        spec = p.model.spec
        if name == "explain":
            from .spec.explain import explain
            return _text(explain(spec, a.get("part") or None, p))
        if name == "status":
            from .spec.explain import Explainer
            e = Explainer(spec, p)
            goals = {}
            for g, x in spec.goals.items():
                goals[g] = {"of": str(x.of), "hold": str(x.hold), "tolerance": x.tolerance, "critical": x.critical,
                            "value": e.signals.get(str(x.of)), "error": e.signals.get(f"goal.{g}.error"),
                            "status": e.status.get(g, "unknown"), "closes": spec.loop(g).closes}
            from . import runner
            return _text({"running": bool(runner.running_pid(p, wait=False)), "goals": goals})
        if name == "findings":
            from .durations import parse_duration
            from .spec import watch
            window = parse_duration(a["since"], "since") if a.get("since") else watch.WINDOW
            found = [x for x in p.model.problems if x.level != "error"] + watch.find(p, spec, window)
            return _text([{"code": f.code, "about": f.about, "message": f.message,
                           "where": str(f.where) if f.where else None} for f in found])
        if name == "residuals":
            from . import state
            from .durations import parse_duration
            window = parse_duration(a["since"], "since") if a.get("since") else state.WINDOW
            return _text(state.snapshot(p, window, None)["residuals"])
        if name == "fit":
            import time as _t

            from . import state
            from .durations import parse_duration
            from .numbers import fit as ft
            from .numbers import proposals as pr
            if getattr(p.model, "spec", None) is None:
                return _text({"error": "the model is an ergostat.toml: equations are written in ergostat.yaml"})
            window = parse_duration(a["since"], "since") if a.get("since") else state.WINDOW
            oldest = min((t for t in (p.events.first_time(), p.measurements.first_time()) if t), default=None)
            _, run, got = ft.compute(p, {"at": _t.time(), "window": window, "starts": oldest})
            return _text({"total": ft._slim(got["total"]), "stocks": {r: ft._slim(x) for r, x in got["stocks"].items()},
                          "accounting": {r: ft._slim(x) for r, x in got["accounting"].items()},
                          "partial": {r: ft._slim(x) for r, x in got["partial"].items()},
                          "equations": {r: ft._slim(x) for r, x in got["equations"].items()},
                          "judged_by_stock": got["judged_by_stock"], "invalid": got["invalid"], "span": got["span"], "notes": run.notes,
                          "words": ft.WORDS, "proposals": pr.pending(p)})
        if name == "events":
            evs = p.events.query(n=min(int(a.get("n") or 30), 500), type=a.get("type") or None, item=a.get("item") or None)
            return _text([{"time": e["time"], "type": e["type"], "item": e.get("item"), "source": e.get("source"),
                           "data": e.get("data")} for e in evs])
        if name == "report_done":
            b = spec.blocks.get(a["block"])
            if b is None or b.type != "person":
                return {**_text(f"{a['block']!r} is not a person block"), "isError": True}
            from .spec.legacy import valve_name
            run = p.events.add("agent.ran", item=b.name, source="person", data={"done": a["moved"], "note": a.get("note", "")})
            flows = [t.name for t in b.targets() if t.kind == "flow"]
            if flows and float(a["moved"]) > 0:
                p.events.add("valve.opened", item=valve_name(spec, b.name, flows[0]), source=b.name, causedby=run["id"],
                             data={"amount": float(a["moved"]), "flow": flows[0]})
            return _text(f"recorded: {b.name} moved {a['moved']}")
        if name == "read_sensor":
            from .spec.ir import Ref
            of, _, sn = str(a["sensor"]).partition(".")
            s = next((x for k in ("stock", "flow", "auxiliary") if (x := spec.sensor(Ref(k, of, sn or "main")))), None)
            if s is None or not s.manual:
                return {**_text(f"{a['sensor']!r} is not a manual sensor"), "isError": True}
            p.measurements.add(s.series, float(a["value"]))
            return _text(f"recorded: {a['sensor']} = {a['value']}")
        if name == "items":
            from .spec import items as its
            if a.get("id"):
                d = its.detail(p.events, spec, a["id"])
                return _text(d) if d else {**_text(f"no item {a['id']!r}"), "isError": True}
            return _text(its.listing(p.events, spec, kind=a.get("kind") or None, state=a.get("state") or None,
                                     n=min(int(a.get("n") or 100), 500)))
        if name == "record_event":
            from .runner import OWN_TYPES, TYPE_NAME
            t, data = str(a.get("type", "")), a.get("data") or {}
            if not TYPE_NAME.match(t) or t.startswith((*OWN_TYPES, "block.", "person.")) or not isinstance(data, dict):
                return {**_text("type: lowercase words joined by dots (ticket.opened), not ergostat's own; data: an object"),
                        "isError": True}
            ev = p.events.add(t, item=a.get("item") or None, source=a.get("source") or "mcp", data=data)
            return _text({"recorded": ev["id"], "type": t, "item": ev["item"]})
        return {**_text(f"no tool {name!r}"), "isError": True}

    def handle(self, msg: dict) -> dict | None:
        mid, method = msg.get("id"), msg.get("method", "")
        if mid is None:                                     # a notification: no answer
            return None
        try:
            if method == "initialize":
                want = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
                result = {"protocolVersion": want, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "ergostat", "version": __version__},
                          "instructions": "ergostat runs control loops over scheduled work. Read the format with the "
                                          "spec tool before editing ergostat.yaml; run check after each edit; explain "
                                          "shows any part in sentences. To review or improve the model, read "
                                          "improve_model first."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = msg.get("params") or {}
                try:
                    result = self.call(params.get("name", ""), params.get("arguments") or {})
                except Exception as e:                      # a tool's failure is the agent's to read, not a protocol error
                    result = {**_text(f"{type(e).__name__}: {e}"), "isError": True}
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(root: Path, inp=None, out=None) -> int:
    inp, out = inp or sys.stdin, out or sys.stdout
    s = Server(root)
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}) + "\n")
            out.flush()
            continue
        reply = s.handle(msg) if isinstance(msg, dict) else None
        if reply is not None:
            out.write(json.dumps(reply, default=str) + "\n")
            out.flush()
    return 0
