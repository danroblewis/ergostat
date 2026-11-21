"""A change that cannot move the replay, judged by structure (SPEC §12e, *A change the replay cannot tell*): one whose
replay is exactly the model's (``judge.compare``'s ``same``) on a record held out that exercised what it touches is
judged by the redesign scorecard (``scorecard.py``: findings, chains, coherence, craft notes; the fit only against
it), not left to wait for record that can never tell it from the model as it is.

Called from ``judge.run`` under ``proposals.locked``, which Accept takes too: nothing ergostat writes comes between the
scorecard's read of the model and its verdict. A hand edit takes no lock, so the verdict carries the version of the
model the scorecard read from disk; one that is not the change's own records nothing (the next pass supersedes it)."""

from __future__ import annotations

from ..durations import human as dur
from ..spec.ir import Spec
from . import observe as ob
from . import version as ver

READINGS = 12               # a stock read fewer times than this in the record held out is not taken as exercised


def exercised_now(p, spec: Spec, nd: dict, since: float, until: float) -> list[str]:
    """The stocks the change touches (``nd["stocks"]``) that the record held out reads and exercises (read at least
    ``READINGS`` times, and not quiet: ``exercised.quiet``). None when it touches no stock: a busy stock elsewhere says
    nothing of it. A stock with too few readings, or none, is not exercised."""
    from . import exercised as ex
    from . import judge as jd
    stocks = list(nd.get("stocks") or [])
    if not stocks or until - since < jd.MIN_WINDOW:
        return []
    data = ob.measured(p, jd._grid(since, until), spec)
    q = ex.quiet(spec, data, least=jd.MIN_WINDOW, readings=READINGS)
    return [r for r in stocks if r not in q and data.how.get(r) not in ("declared", "not measured")
            and sum(v is not None for v in data.values.get(r) or []) >= READINGS]


def _read(p) -> tuple[Spec, list]:
    """The model as it is on disk, with what ``check`` finds of it: what the scorecard scores against."""
    from ..spec import read
    return read(p.model.path)


def judged(p, x: dict, spec: Spec, nd: dict, since: float, now: float) -> tuple[str | None, str, dict | None, str]:
    """The structural verdict (passed, failed or inconclusive), why, the scorecard and the version of the model it
    read; or None, why and the scorecard: still under test, something it needs unmeasurable. A version that is not the
    change's (``x["version"]``) means a hand edit came first: no verdict is to be recorded."""
    from . import judge as jd
    from . import scorecard as sc
    from . import trial as tr
    before, problems_before = _read(p)
    v = ver.version(before)
    if v != x.get("version"):
        return None, "the model was edited since the change was made", None, v
    after, problems = tr.compiled(p.model.path, tr.texts_after(tr.edits_of(x)), findings=True)
    errors = [str(e) for e in problems if e.level == "error"]
    if errors:
        return "failed", "the model it leaves no longer compiles: " + "; ".join(errors)[:300], None, v
    card = sc.score(p, before, problems_before, after, problems, at=now, fit_counts=False)
    if card["verdict"] == "better":
        return "passed", f"on structure (its replay is the model's on all the record held out): {card['why']}", card, v
    if card["why"] != sc.STILL:                       # mixed, or no better with something worse
        return "failed", f"on structure (its replay is the model's): {card['why']}", card, v
    ft, co = card["fit"], card["coherence"]
    unmeasured = ([f"coherence ({co.get('says')})"] if not co.get("measurable", True) else []) + \
        ([f"the fit ({ft.get('says')})"] if not (ft.get("measurable_before") and ft.get("measurable_after")) else [])
    if not unmeasured:
        return "inconclusive", ("no structural measure moves, and the record cannot tell it from the model as it is: "
                                f"its replay is the model's on all of {dur(now - since)} held out"), card, v
    why = f"no structural measure moves, and {' and '.join(unmeasured)} cannot be measured"
    if now - since >= jd.horizon(nd["needs"]):
        return "inconclusive", f"{why}, after {dur(now - since)} held out", card, v
    return None, f"{why}: it stays under test until they can, or {dur(jd.horizon(nd['needs']))} held out", card, v
