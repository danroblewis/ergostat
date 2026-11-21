"""``ergostat mcp``: ergostat as an MCP server (stdio, JSON-RPC 2.0, one message per line), so an
AI agent can read the model, check what it writes, explain any part, see what is happening and
what is worth a look, and report the work a person block was asked for.

Every call loads the model afresh from the project's files, so an agent editing ``ergostat.yaml``
sees its change at the next call. Nothing here starts or stops ergostat."""

from __future__ import annotations

import json
import sys
import time
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
     "a block with no visible effect, an open loop, ...). Call it after every edit; once the model has run, coherence holds "
     "it against what really happened.", "inputSchema": _obj()},
    {"name": "coherence", "description": "The three views held against each other over the record: Process (how the items "
     "really moved), Dynamics (the stocks and flows that model it) and Blocks (what moves the work). Per item kind, a score "
     "(agreements of comparisons, or how much more record it needs) and each mismatch with its file and line, the fix when "
     "it is clear, the pair of views that disagrees, and the findings of check it is linked to. Run it after the model has "
     "run for a while (try_use, or the live record), and change the model (or the blocks) until the three agree. since: "
     "the record compared, like 6h (default 1d); project: a scratch copy try_use made, to read its record instead.",
     "inputSchema": _obj({"since": {"type": "string"}, "project": {"type": "string"}})},
    {"name": "explain", "description": "The model, or one part of it, in sentences: what it is, what measures it, what serves "
     "it, what it is doing now. part: a goal, block, stock, flow or auxiliary, as goal.x or just x; leave it out for the "
     "whole model, with its feedback loops (each R reinforcing, B balancing, or of unknown sign).",
     "inputSchema": _obj({"part": {"type": "string"}})},
    {"name": "status", "description": "Every goal now: its value, setpoint, error and status (holding, off, or stale), and whether "
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
    {"name": "try_change", "description": "Check a change to the model as a block's propose line would be checked, and keep "
     "it nowhere: the edit applied to a scratch copy, compiled, checked, replayed and refitted, each reason's evidence "
     "verified. propose: {kind (parameter, equation, structure), parts, title, edit, reasons: [{says, evidence}], confidence}. "
     "edit: {files: [{file, hunks: [{line, old: [lines], new: [lines]}]}]} or {file, replace: 'the lines now', with: 'the "
     "lines after'}, a file named from the model's folder. evidence: finding:CODE@PART (a finding check reports; its id), "
     "fit:total.nmse or fit:stock.NAME.r2|mape|um|us|uc, residual:stock.NAME, a document or code line (docs/MODELLING.md:120, "
     "bin/x.py:10-14) or a URL, or rule:NAME (a modelling rule). Says whether it would be proposed, and why not.",
     "inputSchema": _obj({"propose": {"type": "object"}}, ["propose"])},
    {"name": "measures", "description": "The model's own quality now: fit (the scaled error of its replay), unexplained "
     "(the share of the stocks' change their flows leave unexplained), loops-unidentified (closed loops whose process the "
     "model does not hold) and findings (what check reports). A model: sensor reads the same numbers.",
     "inputSchema": _obj()},
    {"name": "trust", "description": "How far the blocks' claims hold (claim lines: {\"claim\": {\"says\": \"tests pass\", "
     "\"about\": ...}}, checked by ergostat after each run against the record and the world): per block, rung and "
     "model, the claims made, verified, contradicted and unchecked, and the share contradicted, over the last week (or "
     "since); and the latest contradicted claims with why. Each claim is an item of kind ergostat.claim (items).",
     "inputSchema": _obj({"since": {"type": "string"}})},
    {"name": "report_done", "description": "Report the work a person block was asked for (type: person): how much was moved "
     "along its flow. The same as `ergostat block NAME --done N`.",
     "inputSchema": _obj({"block": {"type": "string"}, "moved": {"type": "number"}, "note": {"type": "string"}},
                         ["block", "moved"])},
    {"name": "inbox", "description": "Everything waiting on a person: gated actions held for approval, person blocks' "
     "requests, advised commands, step tests offered, changes to the model awaiting the owner. Each with its id, summary, "
     "age, link, why it waits, its answer verbs and its class's record this week. stats: true gives each class's record "
     "and what could move up the ladder instead.", "inputSchema": _obj({"stats": {"type": "boolean"}})},
    {"name": "answer", "description": "Answer an entry of the inbox, on the owner's behalf: only when the owner told you "
     "to, and as they said. id: the entry's id (or the start of its key); verb: approve, deny or done (with n, how much "
     "a person moved); note: why. The same as `ergostat inbox ID --approve | --deny | --done N`.",
     "inputSchema": _obj({"id": {"type": "string"}, "verb": {"type": "string", "enum": ["approve", "deny", "done"]},
                          "n": {"type": "number"}, "note": {"type": "string"}}, ["id", "verb"])},
    {"name": "read_sensor", "description": "Record a reading of a manual sensor (manual: true), named as its stock and sensor: "
     "inbox.eyes. The same as `ergostat sensor inbox.eyes --read V`.",
     "inputSchema": _obj({"sensor": {"type": "string"}, "value": {"type": "number"}}, ["sensor", "value"])},
    {"name": "items", "description": "The items (the record folded by id: ticket/12, github/pull_request/4231): each kind's "
     "count per state, and the items with their state and fields. kind and state filter; id gives one item with its "
     "moves between states, each field's latest changes (history: op, path, before, after, by which event), what was "
     "refused, and its events.",
     "inputSchema": _obj({"kind": {"type": "string"}, "state": {"type": "string"}, "id": {"type": "string"},
                          "n": {"type": "integer"}})},
    {"name": "context", "description": "A starting context, as Markdown: a projection recipe the model names under "
     "contexts: (its parts in order, each within its budget: decisions, corrections, the owner's words, an item's history, "
     "the state now, a session's turns, documents, the model's parts), rendered for item when given; or the built-ins "
     "decisions (the owner's confirmed decisions, most relevant to scope first) and corrections (what the owner corrected "
     "before, for kind: ui, docs, git, testing, ...). list: true gives the recipes; outcomes: true, how the work each "
     "started turned out. budget: characters (6000) or tokens (1500t). The same as `ergostat context RECIPE`.",
     "inputSchema": _obj({"recipe": {"type": "string"}, "item": {"type": "string"}, "scope": {"type": "string"},
                          "kind": {"type": "string"}, "budget": {"type": "string"}, "list": {"type": "boolean"},
                          "outcomes": {"type": "boolean"}})},
    {"name": "record_event", "description": "Record something that happened outside: an event of a type (ticket.opened), "
     "about an item (ticket/12), with data (its fields: title, priority, ...), folded by its kind's fold: rules (replace "
     "by default); or, in place of data, a patch (a JSON Patch, RFC 6902: [{\"op\": \"add\", \"path\": \"/tags/-\", "
     "\"value\": \"x\"}]), applied whole or refused with why, or set (the item's whole document). An item kind's on: map "
     "says which types move an item between states. The same as `ergostat event --add TYPE --item ID --data JSON` "
     "(or --patch, --set). To propose a decision or a correction the owner gave: ergostat.decision.proposed ({decision, "
     "words: [{text, session, line, time}], reasons, alternatives: [{option, why}], scope, supersedes}) or "
     "ergostat.correction.proposed ({correction, words, corrects, kind_of_work, scope}); the owner confirms it.",
     "inputSchema": _obj({"type": {"type": "string"}, "item": {"type": "string"}, "data": {"type": "object"},
                          "patch": {"type": "array", "items": {"type": "object"}}, "set": {"type": "object"},
                          "source": {"type": "string"}}, ["type"])},
    {"name": "message", "description": "Relay the owner's words to the work in flight, verbatim (an AI front-end passing on "
     "what the owner said): recorded as an ergostat.message item, routed to the items and block runs it concerns (about, "
     "when said: an item id like review/2041 or a part like block.developer; else the ids and names in its words; else "
     "the classifier), and delivered: a running Claude Code session gets it as its next turn, a block's next run in its "
     "context, finished work a follow-up. Returns where it went, or that it reached no work (unrouted: it needs "
     "attention). The same as `ergostat message TEXT --about X`.",
     "inputSchema": _obj({"text": {"type": "string"}, "about": {"type": "array", "items": {"type": "string"}},
                          "by": {"type": "string"}}, ["text"])},
    {"name": "report_upstream", "description": "Draft a report about ergostat itself, for the owner: when ergostat is "
     "wrong (it crashed, gave a wrong answer, or cannot express what the model needs). It is scrubbed first (the model's "
     "names, paths, hosts, URLs, emails, keys, ticket keys and the owner's denylist become stand-ins like stock-1) and "
     "written to the state directory's reports/ folder as a Markdown issue for the owner to read and submit by hand. "
     "Nothing is sent: never post it anywhere yourself; tell the owner where it is (the returned file, and `ergostat "
     "report ID`). says: what went wrong, in a line; details: more; parts: the parts involved (stock.x, block.y), from "
     "which a generic reproduction is made; findings: codes involved; repro: a tiny generic model you wrote that shows "
     "it (scrubbed too). Without says: the reports drafted so far.",
     "inputSchema": _obj({"says": {"type": "string"}, "details": {"type": "string"},
                          "parts": {"type": "array", "items": {"type": "string"}},
                          "findings": {"type": "array", "items": {"type": "string"}}, "repro": {"type": "string"},
                          "by": {"type": "string"}})},
    {"name": "templates", "description": "The templates a small control system is made from (respond-to, re-ping, "
     "daily-report, keep-under, steps, collect, and the owner's own from library: folders): each a reusable shape that "
     "expands into ordinary items, stocks, flows, goals and blocks, one system per use. Without name: the list. With name: "
     "its parameters (type, default, what stands in when left out), what it is in control theory and system dynamics, "
     "and an example uses: entry. Read it before add_use.",
     "inputSchema": _obj({"name": {"type": "string"}})},
    {"name": "add_use", "description": "Add a use of a template (an instance) to the model: uses: INSTANCE: {use: TEMPLATE, "
     "with: {params}}, written into file (default ergostat.yaml; a new file is created and included). Without write: true "
     "nothing is written: it returns the diff, what check says (errors point at the use: line), and the parts it makes "
     "(named INSTANCE-...). Parameters left out run on free stand-ins (said in the findings). replace: true rewrites an "
     "instance already in that file. project: another folder (a scratch copy try_use made) instead of this one.",
     "inputSchema": _obj({"instance": {"type": "string", "description": "lowercase name, like pr-pings"},
                          "template": {"type": "string"}, "with": {"type": "object"}, "file": {"type": "string"},
                          "within": {"type": "string", "description": "a system it is part of"},
                          "description": {"type": "string"}, "replace": {"type": "boolean"}, "write": {"type": "boolean"},
                          "project": {"type": "string"}}, ["instance", "template"])},
    {"name": "scaffold", "description": "Write a starting script for one of a template's commands, runnable as it is (a "
     "stand-in) with a TODO where the real work goes: role source (prints records as JSON, for command:), answer or step "
     "(works on one item from standard input), measure (prints a number), act (a correction, prints {\"moved\": n}), "
     "render (prints a report as Markdown), ping (sends one reminder). path: where (relative to the project, or absolute: "
     "a private folder outside any repository is fine). Returns the command to put under with:.",
     "inputSchema": _obj({"role": {"type": "string"}, "path": {"type": "string"}, "overwrite": {"type": "boolean"}},
                         ["role", "path"])},
    {"name": "try_use", "description": "Try a system on a scratch copy of the project, never the project itself: the "
     "copy is checked, then run for seconds (default 30) with a record of its own, each of the system's blocks run once "
     "more at the end; returns what moved (items by state, each block's runs and what it moved, each goal's crossings), "
     "what failed and why (sensor failures, block logs), and the scratch folder. Give the same arguments as add_use "
     "(instance, template, with, file) to try a use before it is written, or system: an instance already written. "
     "standins: true runs every template on its stand-ins.",
     "inputSchema": _obj({"instance": {"type": "string"}, "template": {"type": "string"}, "with": {"type": "object"},
                          "file": {"type": "string"}, "within": {"type": "string"}, "system": {"type": "string"},
                          "seconds": {"type": "number"}, "standins": {"type": "boolean"}})},
    {"name": "where_drawn", "description": "Where a system (an instance) is drawn: its parts, the diagram pages "
     "(/diagram?view=dynamics&system=NAME, the stock-and-flow view; view=blocks, the control view), with the page's address "
     "when ergostat is running, the system drawn as text (as ergostat system NAME, and its loops as blocks), and its "
     "shape: the pieces each view falls into (one per item kind when its states are chained) and check's chain findings. "
     "project: "
     "a scratch copy try_use made, to show it before it is written.",
     "inputSchema": _obj({"system": {"type": "string"}, "project": {"type": "string"}}, ["system"])},
    {"name": "messages", "description": "The owner's messages and what became of each (routed, delivered, unrouted, "
     "answered, missed), with the counts; or one (id) with its routing and deliveries.",
     "inputSchema": _obj({"id": {"type": "string"}})},
]


def _refused(p, spec, ev: dict) -> str | None:
    """Why the event just recorded did not change its item, when it did not (a patch whose test failed)."""
    from .spec import items as its
    it = its.one(p.events, spec, ev["item"]) if spec is not None else None
    return next((r["why"] for r in (it.refused if it else []) if r["event"] == ev["id"]), None)


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
                                        **({"id": f"{p.code}@{p.about}" if p.about else p.code} if p.level != "error" else {}),
                                        **({"items": p.items} if p.items else {}),
                                        "file": str(p.where.file) if p.where else None,
                                        "line": p.where.line if p.where else None} for p in problems],
                          "counts": {"stocks": len(spec.stocks), "flows": len(spec.flows), "auxiliaries": len(spec.auxiliaries),
                                     "goals": len(spec.goals),
                                     "blocks": len(spec.blocks), "files": len(spec.files)}})
        if name == "spec":
            from . import helpdocs
            return _text(helpdocs.read("spec") or "the specification is docs/SPEC.md in the ergostat repository")
        if name in ("templates", "add_use", "scaffold", "try_use", "where_drawn"):
            return self.author(name, a)
        if name == "coherence" and a.get("project"):        # a scratch copy try_use made: its own record
            from . import coherence as co
            from .durations import parse_duration
            from .store import Project
            sp = Project(mdl.load(Path(a["project"]).expanduser()))
            got = co.of_project(sp, sp.model.spec, parse_duration(a["since"], "since") if a.get("since") else co.WINDOW)
            return _text({"scores": [co.score_line(k, x) for k, x in got["kinds"].items()], **got})
        if name == "improve_model":
            from . import helpdocs
            skill, guide = helpdocs.read("improve-model"), helpdocs.read("modelling")
            return _text("\n\n".join(x for x in (skill, guide) if x) or "the guidelines are docs/MODELLING.md in the "
                         "ergostat repository")
        p = self.project()
        spec = p.model.spec
        if name == "try_change":
            from .numbers import improve as im
            return _text(im.trial(p, a.get("propose") or {}))
        if name == "measures":
            from .numbers import measures as ms
            return _text(ms.all_of(p))
        if name == "trust":
            import time as _t

            from .claims import trust
            from .durations import parse_duration
            since = _t.time() - parse_duration(a["since"], "since") if a.get("since") else None
            return _text(trust.table(p, since))
        if name == "coherence":
            from . import coherence as co
            from .durations import parse_duration
            got = co.of_project(p, spec, parse_duration(a["since"], "since") if a.get("since") else co.WINDOW)
            return _text({"scores": [co.score_line(k, x) for k, x in got["kinds"].items()], **got})
        if name == "explain":
            from .spec.explain import explain
            return _text(explain(spec, a.get("part") or None, p))
        if name == "status":
            from .spec.explain import Explainer
            e = Explainer(spec, p)
            from .spec.observer import shown_stale
            goals, now = {}, time.time()
            for g, x in spec.goals.items():
                goals[g] = {"of": str(x.of), "hold": str(x.hold), "tolerance": x.tolerance, "critical": x.critical,
                            "value": e.signals.get(str(x.of)), "error": e.signals.get(f"goal.{g}.error"),
                            "status": e.status.get(g, "unknown"), "closes": spec.loop(g).closes}
                if (stale := shown_stale(p, spec, g, goals[g]["status"], now)) is not None:   # (SPEC §9.6)
                    goals[g].update(status="stale", stale=round(stale, 1))
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
            from .inbox.answer import person_done
            return _text(person_done(p, spec, b, float(a["moved"]), a.get("note")))
        if name in ("inbox", "answer"):
            from .inbox import answer, stats
            if name == "answer":
                try:
                    return _text(answer.answer(p, spec, a["id"], a["verb"], a.get("n"), a.get("note"), by=stats.BY_AGENT))
                except answer.AnswerError as e:
                    return {**_text(str(e)), "isError": True}
            return _text(stats.by_class(p, spec) if a.get("stats") else stats.listing(p, spec))
        if name == "read_sensor":
            from .spec.ir import Ref
            of, _, sn = str(a["sensor"]).partition(".")
            s = next((x for k in ("stock", "flow", "auxiliary") if (x := spec.sensor(Ref(k, of, sn or "main")))), None)
            if s is None or not s.manual:
                return {**_text(f"{a['sensor']!r} is not a manual sensor"), "isError": True}
            p.measurements.add(s.series, float(a["value"]))
            return _text(f"recorded: {a['sensor']} = {a['value']}")
        if name == "context":
            from .decisions import context as cx
            from .decisions.kinds import CORRECTION, DECISION
            recipe = a.get("recipe")
            if a.get("list"):
                return _text({n: {"version": r.version, "description": r.description,
                                  "parts": [x.label() for x in r.parts]} for n, r in spec.contexts.items()})
            if a.get("outcomes"):
                from .recipes import uses
                return _text(uses.table(p, spec))
            if recipe not in ("decisions", "corrections"):
                from .recipes import render as rd
                try:
                    r = rd.render(p, spec, str(recipe or ""), a.get("item") or None,
                                  budget=cx.budget_of(a["budget"]) if a.get("budget") else None)
                except (rd.RecipeError, ValueError) as e:
                    return {**_text(str(e)), "isError": True}
                return _text(r.text)
            kind = DECISION if recipe == "decisions" else CORRECTION
            return _text(cx.render(p, kind, a.get("scope") if kind == DECISION else (a.get("kind") or a.get("scope")),
                                   cx.budget_of(a.get("budget"))))
        if name == "items":
            from .spec import items as its
            if a.get("id"):
                d = its.detail(p.events, spec, a["id"], history=20)     # each field's latest changes; all of them: the CLI
                return _text(d) if d else {**_text(f"no item {a['id']!r}"), "isError": True}
            return _text(its.listing(p.events, spec, kind=a.get("kind") or None, state=a.get("state") or None,
                                     n=min(int(a.get("n") or 100), 500)))
        if name == "message":
            from .messages import record, route
            try:
                got = route.send(p, spec, str(a.get("text") or ""), by=str(a.get("by") or "owner"), about=a.get("about"),
                                 via="mcp")
            except record.MessageError as e:
                return {**_text(str(e)), "isError": True}
            return _text({k: got.get(k) for k in ("id", "state", "matched", "why", "routed_to", "deliveries", "outcome")})
        if name == "messages":
            from .messages import measures, record
            if a.get("id"):
                got = record.get(p, str(a["id"]))
                return _text(got) if got else {**_text(f"no message {a['id']!r}"), "isError": True}
            ms = sorted(record.stored(p).values(), key=lambda m: -m["time"])[:30]
            return _text({"messages": [{k: m.get(k) for k in ("id", "state", "text", "by", "sent", "matched", "outcome")}
                                       for m in ms], "counts": measures.counts(p)})
        if name == "report_upstream":                       # drafted for the owner; never sent (SPEC §12m)
            from .reports import record
            if not str(a.get("says") or "").strip():
                return _text([{k: r.get(k) for k in ("id", "state", "title", "origin", "file")}
                              for r in sorted(record.stored(p).values(), key=lambda r: -r["time"])][:30])
            lists = {k: [str(x) for x in a[k]] if isinstance(a.get(k), list) else None for k in ("parts", "findings")}
            try:
                got = record.draft(p, str(a["says"]), origin="agent", by=str(a.get("by") or "mcp"), details=a.get("details"),
                                   parts=lists["parts"], findings=lists["findings"], repro=a.get("repro"))
            except record.ReportError as e:
                return {**_text(str(e)), "isError": True}
            return _text({"id": got["id"], "title": got["title"], "file": got["file"], "scrubbed": got["scrubbed"],
                          "tell_the_owner": f"A report is drafted for you to read, scrubbed: {got['file']} (ergostat report "
                                            f"{record.short(got['id'])}). Nothing was sent; submit it by hand if you choose.",
                          "text": got["text"]})
        if name == "record_event":
            from .runner import OWN_TYPES, TYPE_NAME
            t, data = str(a.get("type", "")), a.get("data") or {}
            if t.startswith(("ergostat.decision.", "ergostat.correction.")) and isinstance(data, dict):
                from .decisions import acts  # a proposal of the owner's intent, checked; never the owner's act
                try:
                    got = acts.take_line(p, t, a.get("item") or None, data, a.get("source") or "mcp")
                except acts.ActError as e:
                    return {**_text(str(e)), "isError": True}
                return _text(got)
            if not TYPE_NAME.match(t) or t.startswith((*OWN_TYPES, "block.", "person.")) or not isinstance(data, dict):
                return {**_text("type: lowercase words joined by dots (ticket.opened), not ergostat's own; data: an object"),
                        "isError": True}
            from .store import ChangesetError
            try:
                ev = p.events.add(t, item=a.get("item") or None, source=a.get("source") or "mcp", data=data,
                                  patch=a.get("patch"), set=a.get("set"))
            except ChangesetError as e:
                return {**_text(str(e)), "isError": True}
            out = {"recorded": ev["id"], "type": t, "item": ev["item"]}
            if ev["item"] and (why := _refused(p, spec, ev)):
                out["refused"] = why
            return _text(out)
        return {**_text(f"no tool {name!r}"), "isError": True}

    def author(self, name: str, a: dict) -> dict:
        """The authoring tools (ergostat/library/author.py): templates, add_use, scaffold, try_use, where_drawn."""
        from .library import author as au
        path = mdl.find(self.root)
        root = Path(a["project"]).expanduser() if a.get("project") else (path.parent if path else self.root)
        try:
            if name == "templates":
                return _text(au.library(root, a.get("name") or None))
            if name == "scaffold":
                return _text(au.scaffold(root, str(a.get("role") or ""), str(a.get("path") or ""), bool(a.get("overwrite"))))
            if name == "where_drawn":
                return _text(au.where(root, str(a["system"])))
            args = {"instance": a.get("instance"), "template": a.get("template"), "given": a.get("with") or {},
                    "file": a.get("file") or None, "within": a.get("within") or None}
            if name == "add_use":
                return _text(au.add(root, **args, description=a.get("description") or None, replace=bool(a.get("replace")),
                                    write=bool(a.get("write"))))
            change = args if a.get("instance") and a.get("template") else None
            if change:
                change["replace"] = True
            return _text(au.trial(root, a.get("system") or None, float(a.get("seconds") or 30), change,
                                  standins=bool(a.get("standins"))))
        except (au.AuthorError, KeyError, ValueError) as e:
            return {**_text(f"{type(e).__name__}: {e}" if not isinstance(e, au.AuthorError) else str(e)), "isError": True}

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
                                          "shows any part in sentences. A request for something to keep happening (as "
                                          "things come in, on a schedule, until answered, under a limit, step by step "
                                          "for each ticket) is never done once by hand here, even when its script or "
                                          "source is missing: it is built as a small control system from a template "
                                          "(the ergostat-author skill: templates, scaffold, add_use, try_use, "
                                          "where_drawn), tried on stand-ins, and shown to the owner before it is "
                                          "written. To review or improve the model, read improve_model first."}
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
