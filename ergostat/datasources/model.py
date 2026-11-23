"""The model as a data source (SPEC §4e, *Data sources*): a transfer function, from a goal's process as the model declares
it or as the record identifies it (ergostat/control: ``loop``, ``ident`` and ``lti``), or as the query writes it. Its
answer is a ``response`` frame: the exact frequency response, which Bode and Nyquist draw, and the system with its poles
and zeros, which the pole-zero map draws. Its connection is the project itself, so a source named ``model`` is there
without declaring it (``datasources._sources``); it reads nothing outside the project.

Its language, one line:

- ``goal NAME``: the goal's declared process, or the one its record identifies when it declares none;
- ``goal NAME declared`` / ``goal NAME identified``: the one asked for, or why there is none;
- ``fopdt gain=K tau=DURATION delay=DURATION``: K e^(−θs) / (τs + 1), written out;
- ``ipdt gain=K delay=DURATION``: K e^(−θs) / s, K per second;
- any of them may end ``dt=DURATION``: the period of the sampled model whose poles and zeros are drawn. A process with
  dead time is always drawn sampled, since a continuous delay has no finite set of poles: at the goal's controller
  period, or a quarter of the dead time, when no ``dt`` is given; the answer states the ``dt``.

An identified process is answered only when the record tells it apart (``ident.judge``), with how well it fits (the
share of the record held out it follows, and its numbers' standard errors); otherwise the query is refused with the
record's reasons, never drawn as if it were known."""

from __future__ import annotations

import math
import re

from ..durations import DurationError, parse_duration
from . import SourceError

TYPE = "model"
KEYS: set[str] = set()
LANGUAGE = "model"
_WORD = re.compile(r"\S+")
_FORMS = {"fopdt": ("gain", "tau", "delay"), "ipdt": ("gain", "delay")}
_HOW = ("declared", "identified")


def _refused(words: str, col: int = 1) -> SourceError:
    return SourceError("refused", words, (1, col))


def _parsed(text: str) -> tuple[str, str | None, dict, dict]:
    """``(first word, goal or None, numbers, where each word is)`` from the query's one line."""
    if "\n" in text.strip():
        raise _refused("a model query is one line")
    words = [(m.group(), m.start() + 1) for m in _WORD.finditer(text)]
    head, at = words[0]
    rest, nums, cols, goal = words[1:], {}, {}, None
    if head == "goal":
        if not rest or "=" in rest[0][0]:
            raise _refused("goal needs a goal's name: goal NAME", at + len(head))
        (goal, cols["goal"]), rest = rest[0], rest[1:]
        if rest and rest[0][0] in _HOW:
            nums["how"], rest = rest[0][0], rest[1:]
        allowed = ("dt",)
    elif head in _FORMS:
        allowed = (*_FORMS[head], "dt")
    else:
        raise _refused(f"a model query starts goal, fopdt or ipdt, not {head!r}", at)
    for w, c in rest:
        k, eq, v = w.partition("=")
        if not eq or k not in allowed:
            raise _refused(f"{w!r}: {head} takes {', '.join(f'{a}=' for a in allowed)}", c)
        if k in nums:
            raise _refused(f"{k}= is given twice", c)
        try:
            nums[k] = float(v) if k == "gain" else 0.0 if k == "delay" and v in ("0", "0s") else parse_duration(v, f"{k}=")
        except (ValueError, OverflowError, DurationError) as e:
            raise _refused(f"{k}=: {v!r} is not a {'number' if k == 'gain' else 'duration (like 30s, 5m, 2h)'}", c) from e
        if not math.isfinite(nums[k]) or (k == "gain" and nums[k] == 0):
            raise _refused(f"{k}=: {v!r} is not a finite number{' other than 0' if k == 'gain' else ''}", c)
        cols[k] = c
    if head in _FORMS and (missing := [k for k in _FORMS[head] if k not in nums and k != "delay"]):
        raise _refused(f"{head} needs {', '.join(f'{k}=' for k in missing)}", at)
    return head, goal, nums, cols


def _from_goal(project, goal: str, how: str | None, until: float, col: int) -> tuple[dict, dict]:
    """The goal's process in lti's terms, and what is said of it: where it came from, its path and its fit."""
    from ..control import loop, record
    spec = getattr(getattr(project, "model", None), "spec", None)
    if spec is None or goal not in (getattr(spec, "goals", None) or {}):
        raise _refused(f"goal {goal!r} is not in the model", col)
    sig = record.signals(spec, goal)
    said: dict = {"path": {"input": sig.u, "output": sig.y} if sig else None, "period": sig.period if sig else None}
    declared = loop.model_process(spec, goal)
    if how != "identified" and declared is not None:
        return declared, {**said, "process_from": "declared"}
    if how == "declared":
        raise _refused(f"goal {goal!r} declares no process: ask goal {goal} identified, for the one its record identifies")
    if sig is None or sig.known:
        raise _refused(f"goal {goal!r} has no one process to identify: " + (sig.known if sig else
                       "nothing its controller moves is one setting or one valve"))
    r, _ = loop.identify(project, sig, until)
    proc = loop.found_process(r)
    if proc is None or not r.get("told_apart"):
        raise _refused(f"the record of goal {goal!r} does not identify its process: "
                       + "; ".join(r.get("why") or ["it says no more"]))
    fit = {"follows_held_out": r.get("fit_val"), "follows_fitted": r.get("fit_est"), "proposable": r.get("proposable"),
           "standard_errors": {k: v for k, v in (r.get("se") or {}).items() if v is not None}, "why_not": r.get("why") or [],
           "from": "step tests" if r.get("test") else "an outside step" if r.get("outside_step") else "the loop working",
           "closed_loop": r.get("closed_loop")}
    return proc, {**said, "process_from": "identified", "fit": fit}


def query(source, text: str, window) -> dict:
    """The transfer function the text names, as a ``response`` frame (datasources/_frames.py)."""
    from ..control import lti
    head, goal, nums, cols = _parsed(text)
    if goal is not None:
        proc, said = _from_goal(window.project, goal, nums.get("how"), window.until, cols["goal"])
    elif head == "fopdt":
        proc, said = {"form": "fopdt", "K": nums["gain"], "tau": nums["tau"], "theta": nums.get("delay", 0.0)}, {}
    else:
        proc, said = {"form": "integrating", "K": nums["gain"], "theta": nums.get("delay", 0.0)}, {}
    theta = proc.get("theta") or 0.0
    dt = nums.get("dt") or ((said.get("period") or theta / 4) if theta else None)
    try:
        pz = lti.poles_zeros(proc, dt)
        fr = lti.response(proc)
    except ValueError as e:
        raise _refused(str(e), cols.get("dt", 1)) from e
    system = {"form": "ipdt" if proc["form"] == "integrating" else "fopdt", "gain": proc["K"], "tau": proc.get("tau"),
              "delay": theta, "poles": pz["poles"], "zeros": pz["zeros"], **({"dt": pz["dt"]} if pz.get("dt") else {})}
    out = {"shape": "response", "frequency": fr, "system": system, "process_from": said.get("process_from", "written"),
           "provenance": "derived" if said.get("process_from") == "identified" else "declared"}
    if said.get("path"):
        out["path"] = said["path"]
    if said.get("fit"):
        out["fit"] = said["fit"]
    return out
