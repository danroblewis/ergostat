"""A daemon's lines, as one read gave them, put in the order they are taken (SPEC §9.7): each run's lines together, up
to ``BATCH`` at once, so a run printing thousands of lines is recorded in a few transactions, not thousands.

A **run line** is a JSON object whose ``run`` is a string and that has no ``done``: it waits in its run's list, which
is taken (``("take", run, lines)``, each line with ``run`` removed) once it holds ``BATCH`` lines. The ``run`` key
wins over any other, as ``Process.line`` has it: a request or a reading tagged with a run is that run's line. Every
other line is ``("one", text)``, handled by itself; a run's ``done`` comes after that run's earlier lines. What waits
at the end of the read is taken then, each run's in the order its first line came."""

from __future__ import annotations

import json

BATCH = 500           # the most lines of one run taken at once


def plan(texts: list[str]) -> list[tuple]:
    steps: list[tuple] = []
    pending: dict[str, list[str]] = {}            # (in the order of each run's first line in the read)
    for text in texts:
        try:
            obj = json.loads(text) if text.startswith("{") else None
        except ValueError:
            obj = None
        run = obj.get("run") if isinstance(obj, dict) else None
        if not isinstance(run, str):
            steps.append(("one", text))
            continue
        if "done" in obj:
            if pending.get(run):
                steps.append(("take", run, pending[run]))
                pending[run] = []
            steps.append(("one", text))
            continue
        got = pending.setdefault(run, [])
        got.append(json.dumps({k: v for k, v in obj.items() if k != "run"}))
        if len(got) >= BATCH:
            steps.append(("take", run, got))
            pending[run] = []
    steps += [("take", run, got) for run, got in pending.items() if got]
    return steps
