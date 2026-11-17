"""Running an extractor over Claude Code transcripts: ``ergostat decisions extract FILE|DIR|ITEM ... [--since]``.

It reads the owner's turns (and the assistant's around them), proposes the decisions and corrections it finds,
and either records them (the default: as ``extractor``, or ``--as``) or prints them as event lines
(``--print``), for a block that runs it: ``{"event": "ergostat.decision.proposed", "item": ..., "data": ...}``,
recorded by the engine as from that block, checked like every proposal. Without ``--model`` it is the stand-in
(``standin.py``); with one, the AI extractor (``ai.py``). ``--new`` reads only what was added to each file since
the last run (kept in the state directory), so a block on a schedule reads each new session once."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from . import acts, ai, standin
from .kinds import CORRECTION, DECISION, item_id
from .transcript import exchanges, lines_in, turns, turns_of_item

READ = "decisions-read.json"     # in the state directory: each transcript's lines already read


def files_of(paths: list[str], p=None) -> list[Path | str]:
    """Each transcript named: a file, every ``.jsonl`` in a folder, or an item whose session the record holds
    (``session/x``: its ``claude.*`` events, ingested by ``transcripts.py``), kept as its id."""
    out: list[Path | str] = []
    for x in paths:
        f = Path(x).expanduser()
        if f.is_dir():
            out += sorted(f.glob("*.jsonl"), key=lambda q: q.stat().st_mtime)
        elif f.is_file():
            out.append(f)
        elif p is not None and "/" in x and not x.startswith((".", "/", "~")) and \
                p.events.query(n=1, item=x, type="claude.message"):
            out.append(x)
        else:
            raise FileNotFoundError(f"{x}: no such transcript, folder, or session in the record")
    return out


def since_of(text: str | None) -> tuple[int, float | None]:
    """``--since``: a line number (``4000``), a time (``2026-11-16``, ``2026-11-16T09:00``), or how long ago (``2d``)."""
    if not text:
        return 0, None
    t = text.strip()
    if t.isdigit():
        return int(t), None
    try:
        return 0, datetime.fromisoformat(t).timestamp()
    except ValueError:
        pass
    from ..durations import parse_duration
    return 0, time.time() - parse_duration(t, "--since")


def earlier_of(p) -> dict:
    """The decisions and corrections already in the record, oldest first, as the AI is shown them."""
    out = {}
    for kind, key in ((DECISION, "decision"), (CORRECTION, "correction")):
        its = sorted(acts.items(p, kind), key=lambda i: i.first)
        out[key] = [(i.id.split("/", 1)[1], str(i.fields.get(key) or "")[:160]) for i in its if i.state != "dismissed"]
    return out


def run(p, paths: list[str], since: str | None = None, model: str | None = None, cap: float | None = None,
        instructions: str | None = None, print_lines: bool = False, new: bool = False, source: str = "extractor",
        out=None) -> dict:
    out = out or sys.stdout
    files = files_of(paths, p)
    line0, t0 = since_of(since)
    state = p.dir / READ
    try:
        read = json.loads(state.read_text()) if new else {}
    except (OSError, ValueError):
        read = {}
    got = {"transcripts": [], "owner_turns": 0, "proposed": {"decision": 0, "correction": 0}, "known": 0,
           "refused": [], "repeats": 0, "extractor": "ai" if model else "standin", **({"model": model} if model else {})}
    earlier = earlier_of(p)

    def found(kind: str, data: dict) -> str | None:
        full = DECISION if kind == "decision" else CORRECTION
        if print_lines:
            try:
                d = acts.check_proposal(full, data, source)
            except acts.ActError as e:
                got["refused"].append(str(e))
                return None
            id = item_id(full, d[kind])
            print(json.dumps({"event": f"{full}.proposed", "item": id, "data": d}), file=out)
            got["proposed"][kind] += 1
            return id.split("/", 1)[1]
        try:
            r = acts.propose(p, full, data, source)
        except acts.ActError as e:
            got["refused"].append(str(e))
            return None
        if r["status"] == "known":
            got["known"] += 1
        else:
            got["proposed"][kind] += 1
            got["repeats"] += 1 if r.get("repeats") else 0
        return r["item"].split("/", 1)[1]

    spent = ai.Spent()
    for f in files:
        key = f if isinstance(f, str) else str(f.resolve())
        start = max(line0, int(read.get(key, 0)))
        ts = turns_of_item(p, f, start, t0) if isinstance(f, str) else turns(f, since_line=start, since_time=t0)
        exs = list(exchanges(ts))
        got["owner_turns"] += len(exs)
        got["transcripts"].append({"file": str(f), "from_line": start + 1, "owner_turns": len(exs)})
        if model:
            left = None if cap is None else cap - spent.cost_usd
            if left is not None and left <= 0:
                spent.stopped = spent.stopped or "the cost cap was reached"
                break
            s = ai.extract(exs, model, left, instructions, earlier, found)
            for k in ("calls", "tokens_in", "tokens_out", "dropped", "failed"):
                setattr(spent, k, getattr(spent, k) + getattr(s, k))
            spent.cost_usd += s.cost_usd
            spent.notes += s.notes
            if s.stopped:
                spent.stopped = s.stopped
                break
        else:
            for t, before, after in exs:
                for kind, data in standin.read(t, before, after):
                    found(kind, data)
        if new:
            read[key] = (max((t.line for t in ts), default=start) if isinstance(f, str) else lines_in(f))
    if new:
        state.write_text(json.dumps(read, indent=1))
    if model:
        got["spent"] = spent.as_dict()
        if spent.notes:
            got["notes"] = spent.notes[:10]
    summary = {k: v for k, v in got.items() if k != "refused"} | {"refused": len(got["refused"])}
    if "spent" in got:
        summary["cost_usd"] = got["spent"]["cost_usd"]
    if print_lines:
        print(json.dumps({"event": "extractor.ran", "data": summary}), file=out)
    else:
        p.events.add("extractor.ran", source=source, data=summary)
    return got
