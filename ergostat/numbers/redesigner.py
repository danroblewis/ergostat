"""The redesigner (SPEC §12e, *Redesign*): an AI agent given a whole system (or the whole model) and asked for one change
set, as a modeller editing holistically would write it. It is given the YAML, what ``check`` finds (findings and craft
notes), the coherence report, the moves the process map observed on the record, the record's summary (each stock's
fit, the event types seen) and the guides (``library/templates/modelling/redesigner.md``, the modeller's craft, and
the review checklists of ``docs/MODELLING-WELL.md``).

It works on a scratch copy (``changeset.Scratch``): each round its edits are made there, the copy compiled, checked,
held against the record (coherence) and scored (``scorecard.py``), and what is left (an edit that could not be made,
an error, a finding, a mismatch, the scorecard) is given back for the next round, up to ``rounds``. The best round's
copy is proposed, once, as one change set (``redesign.submit``). Bounded by ``budget`` dollars a run: no call starts
once it is spent. Every call says what it cost (``claude -p --output-format json``); the run's total is kept on the
change and printed as a Claude Code result line, so the run's cost is recorded as any AI run's (``costs/ai.py``)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..spec.ir import Spec, template_made
from . import changeset as cs
from . import modeller as md

HERE = Path(__file__).resolve().parent.parent
GUIDE = HERE / "library" / "templates" / "modelling" / "redesigner.md"
CRAFT = HERE / "library" / "templates" / "modelling" / "modeller.md"
WELL_SECTIONS = ("How an SD practitioner reads it", "Rework, visible", "4. Across all three views", "5. Review checklists")
WHOLE = 40000                # model files shown whole up to this many characters, else the system's parts as written
BUDGET = 0.50                # dollars a run, by default
ROUNDS = 3


def _sections(text: str, names: tuple[str, ...]) -> str:
    out = []
    lines = text.split("\n")
    for name in names:
        at = next((i for i, x in enumerate(lines) if x.startswith("#") and name in x), None)
        if at is None:
            continue
        depth = len(lines[at]) - len(lines[at].lstrip("#"))
        end = next((j for j in range(at + 1, len(lines)) if lines[j].startswith("#")
                    and len(lines[j]) - len(lines[j].lstrip("#")) <= depth), len(lines))
        body = [x for x in lines[at:end] if not x.startswith("![") and not x.startswith("| ![")]
        out.append("\n".join(body).strip())
    return "\n\n".join(out)


def guides() -> str:
    craft = CRAFT.read_text(encoding="utf-8")
    a, b = craft.find("## The model's craft"), craft.find("## What you may propose")
    craft = craft[a:b].strip() if a >= 0 else ""
    from .. import helpdocs  # an installed ergostat has it in help/, a clone in docs/
    text = helpdocs.read("modelling-well")
    well = _sections(text, WELL_SECTIONS) if text else ""
    return "\n\n".join(x for x in (GUIDE.read_text(encoding="utf-8"), craft, "## From docs/MODELLING-WELL.md\n\n" + well) if x)


def _files(s: cs.Scratch, spec: Spec, system: str) -> list[str]:
    total = sum(len(s.texts[f]) for f in s.files)
    if total <= WHOLE:
        return [f"```yaml\n# {s.rel(f)}\n{s.texts[f]}\n```" for f in s.files]
    from . import redesign as rd
    refs = rd.members(spec, system)
    near = md.neighbourhood(spec, refs)[:80]
    out = []
    from ..spec.load import texts as override
    with override(s.texts):
        for r in near:
            t = md._text_of(spec, r)
            if t:
                out.append(f"```yaml\n{t}\n```")
    return out


def _mine(spec: Spec, system: str, about: str | None) -> bool:
    """A finding about a part of this system (or about no part): what this system's redesign may answer."""
    if system == "model" or not about or about == "model":
        return True
    from . import redesign_due as due
    return due._in(spec, system, about)


def _check(problems, spec: Spec | None = None, system: str = "model") -> list[str]:
    out = []
    for x in problems:
        if x.level == "error":
            out.append(f"ERROR {x}")
    for lv in ("finding", "note"):
        for x in problems:
            if x.level == lv or (lv == "finding" and x.level not in ("error", "note")):
                if template_made(x) or (spec is not None and not _mine(spec, system, x.about)):
                    continue
                out.append(f"{'note' if x.level == 'note' else 'finding'} {x.code}@{x.about}: {str(x.message)[:400]}")
    return out


def _coherence(p, spec: Spec, problems) -> list[str]:
    from .. import coherence as co
    try:
        got = co.compare(spec, p.events, None, None, [x for x in problems if x.level != "error"])
    except Exception as e:
        return [f"(coherence could not be read: {type(e).__name__}: {e})"]
    out = [f"{s}  {t}" if s in ("head",) else t for s, t in co.lines(got)]
    for k, x in got["kinds"].items():
        if k.startswith("ergostat.") or not x.get("moved"):
            continue
        out.append(f"observed moves of {k} in the window (process map): " + ", ".join(f"{m} ×{n}" for m, n in x["moved"].items()))
    return out


def _record(p, spec: Spec) -> list[str]:
    from . import scorecard as sc
    f = sc.fit(p, spec)
    out = []
    t = (f.get("total") or {})
    out.append(f"fit (scaled error of the replay, lower is better): {t.get('nmse') if t else None}"
               + (f" ({f.get('why')})" if f.get("why") else ""))
    for r, s in sorted((f.get("stocks") or {}).items()):
        if s and s.get("nmse") is not None:
            out.append(f"  {r}: scaled error {s['nmse']:.3g}")
    for r, s in sorted((f.get("equations") or {}).items()):
        if s and s.get("r2") is not None:
            out.append(f"  {r} equation: R² {s['r2']:.2f}")
    levels = []                                       # each stock's level, as the record moved it: a queue building up
    for n, st in sorted(spec.stocks.items()):
        for sn in st.sensors.values():
            pts = p.measurements.range(sn.series, 0.0)
            if len(pts) >= 2:
                vs = [v for _, v in pts]
                levels.append(f"  stock.{n}: {vs[0]:.3g} at first, {vs[-1]:.3g} now, {max(vs):.3g} at most, over "
                              f"{(pts[-1][0] - pts[0][0]) / 60:.0f} min")
            break
    if levels:
        out.append("each stock's level on the record (first, now, most):")
        out += levels
    try:
        from collections import Counter
        types = Counter(e["type"] for e in p.events.query(n=4000) if not str(e["type"]).startswith(("ergostat.", "agent.", "valve.",
                                                                                                    "sensor.", "model.")))
        if types:
            out.append("event types on the record (last 4000 events): " + ", ".join(f"{k} ×{n}" for k, n in types.most_common(30)))
    except Exception:
        pass
    return out


def prompt(p, s: cs.Scratch, system: str, why: list[str], feedback: list[str] | None = None, card: dict | None = None) -> str:
    spec, problems = s.compiled()
    shown = spec or s.base
    lines = [guides(), "", "## The task", "",
             f"Redesign {'the whole model' if system == 'model' else 'system ' + system + ' (change only its parts)'}. "
             f"Why now: {'; '.join(why) or 'asked'}.",
             f"Files: {', '.join(s.rel(f) for f in s.files)}.", "",
             "## The model, as it is now" + (" (with your edits so far)" if s.done else ""), ""]
    lines += _files(s, shown, system)
    lines += ["", f"## What check finds{'' if system == 'model' else f' in system {system}'}", ""] + \
        (_check(problems, shown, system) or ["nothing"])
    if spec is not None:
        lines += ["", "## Coherence: the three views held against the record", ""]
        lines += _coherence(p, spec, problems) or ["nothing to compare"]
    lines += ["", "## The record", ""] + _record(p, shown)
    if s.done:
        lines += ["", "## Your edits so far (made on the scratch copy above)", ""]
        lines += [f"- {x['said']}" + (f": {x['why']}" if x["why"] else "") for x in s.done]
    if card:
        from . import scorecard as sc
        lines += ["", "## The scorecard of your edits so far", ""] + sc.lines(card)
    if feedback:
        lines += ["", "## What ergostat said of your last answer (fix these in this round's edits)", ""] + [f"- {x}" for x in feedback]
    if s.done:
        lines += ["", "Answer with the edits still to make, on top of those already made (an empty list when it is done): "
                      "the same one JSON line."]
    return "\n".join(lines)


def parse(text: str) -> dict | None:
    """The change set in an answer: its one JSON line (or a fenced block), or None."""
    t = str(text or "").strip()
    cands = [x.strip().strip("`").strip() for x in t.splitlines() if x.strip().startswith("{")]
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if m:
        cands.insert(0, m.group(1))
    cands.append(t[t.find("{"):t.rfind("}") + 1] if "{" in t else "")
    for c in cands:
        try:
            obj = json.loads(c)
        except ValueError:
            continue
        if isinstance(obj, dict) and "redesign" in obj:
            return obj["redesign"] if isinstance(obj["redesign"], dict) else {"edits": [], "none": obj.get("why") or "nothing to change"}
    return None


def reports(text: str) -> list:
    """The report lines in an answer (``{"report": ...}``: what ergostat could not express), passed on as the block's own."""
    out = []
    for x in str(text or "").splitlines():
        try:
            obj = json.loads(x.strip().strip("`").strip())
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("report"):
            out.append(obj["report"])
    return out


def run(p, system: str = "model", why: list[str] | None = None, model: str = "haiku", budget: float = BUDGET,
        rounds: int = ROUNDS, by: str = "redesigner", submit: bool = True, call=None, timeout: float | None = None,
        on_call=None) -> dict:
    """One run: rounds on a scratch copy, then the best copy proposed. Returns what it did and what it cost."""
    from ..spec import read
    from . import redesign as rd
    from . import scorecard as sc
    from . import version as ver
    call = call or md.call
    spec: Spec = p.model.spec
    system = rd.system_of(spec, system)
    _, before_problems = read(p.model.path)
    fit_b = sc.fit(p, spec)
    cost = {"usd": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": 0, "seconds": 0.0, "model": model}
    s = cs.Scratch(p, spec)
    feedback: list[str] = []
    card = None
    best: tuple[float, list[dict], dict] | None = None    # (score, edits, card)
    title, summary = None, None
    log: list[dict] = []
    said: list = []                                   # report lines, for the block to print (SPEC §12m)
    t0 = time.perf_counter()
    for r in range(1, max(1, rounds) + 1):
        if cost["usd"] >= budget:
            log.append({"round": r, "stopped": f"the budget (${budget:.2f}) is spent"})
            break
        t_p = time.perf_counter()
        text = prompt(p, s, system, why or [], feedback, card)
        t_c = time.perf_counter()
        got = call(text, model, md.per_call(timeout, rounds))
        if on_call is not None:                     # each call's cost said as it is spent: a run cut short keeps it
            on_call(got)
        took = {"prompt_s": round(t_c - t_p, 1), "call_s": round(time.perf_counter() - t_c, 1), "prompt_chars": len(text)}
        cost["calls"] += 1
        for k in ("usd", "tokens_in", "tokens_out", "seconds"):
            cost[k] = round(cost[k] + float(got.get(k) or 0), 6) if k in ("usd", "seconds") else cost[k] + int(got.get(k) or 0)
        if got.get("error"):
            log.append({"round": r, "error": got["error"], **took})
            break
        said += [x for x in reports(got.get("result")) if x not in said]
        cs_ = parse(got.get("result"))
        if cs_ is None:
            feedback = ["your answer had no {\"redesign\": {...}} line that is JSON: answer with that one line only"]
            log.append({"round": r, "made": 0, "why": "no change set in the answer", **took})
            continue
        title = title or cs_.get("title")                    # the first round's: what the whole change set is
        summary = summary or cs_.get("summary")
        edits = cs_.get("edits") or []
        feedback = []
        made = 0
        for i, e in enumerate(edits if isinstance(edits, list) else []):
            try:
                s.apply(e)
                made += 1
            except cs.ChangeSetError as err:
                feedback.append(f"edit {i + 1} ({cs.said(e) if isinstance(e, dict) else str(e)[:80]}) was not made: {err}"[:600])
        t_s = time.perf_counter()
        s.keep_names()
        after, problems = s.compiled()
        if after is None:
            feedback += [f"the model does not compile: {x}"[:400] for x in s.errors()[:6]]
            card = None
            log.append({"round": r, "made": made, "not_made": len(feedback), "compiles": False, **took})
        elif s.changed():
            card = sc.score(p, spec, before_problems, after, problems, fit_before=fit_b)
            left = [f"{x.code}@{x.about}" for x in problems if x.level not in ("error", "note") and not sc._skip(x)
                    and _mine(after, system, x.about)]
            if left:
                feedback.append("check still finds: " + "; ".join(left[:12]))
            if card["coherence"]["mismatches_after"]:
                feedback.append("coherence still finds: " + "; ".join(card["coherence"]["introduced"][:6] or ["see above"]))
            beyond = rd.outside(spec, after, system, card["parts"])
            if beyond:                                # refused if proposed so: said now, while there are rounds left
                feedback.append(f"you changed parts outside system {system}: {', '.join(beyond[:8])}; change only its "
                                f"parts (other systems follow your renames on their own): undo those edits")
            log.append({"round": r, "made": made, "not_made": sum(1 for x in feedback if " was not made" in x),
                        "verdict": card["verdict"], "score": card["score"], **took,
                        "score_s": round(time.perf_counter() - t_s, 1)})
            if not beyond and (best is None or card["score"] > best[0]):
                best = (card["score"], [x["edit"] | ({"why": x["why"]} if x["why"] else {}) for x in s.done
                                        if "keep_names" not in x["edit"]], card)
            if card["verdict"] == "better" and not left and not card["coherence"]["mismatches_after"] and not \
                    [x for x in feedback if "was not made" in x]:
                break
        else:
            log.append({"round": r, "made": made, "why": cs_.get("none") or "it changed nothing", **took})
            if not edits:
                break
    cost["seconds"] = round(time.perf_counter() - t0, 1)
    out = {"system": system, "why": why or [], "rounds": log, "cost": cost, "model": model, "budget": budget,
           "version": ver.version(spec), "reports": said}
    if best is None:
        out["result"] = "nothing proposed"
        return out
    out["scorecard"] = best[2]
    raw = {"title": title or f"A redesign of {'the model' if system == 'model' else system}", "system": system,
           "summary": summary or "", "edits": best[1], "rounds": len(log), "cost": cost}
    out["change_set"] = raw
    if submit:
        import copy

        from .. import model as mdl
        now = copy.copy(p)                             # the model as it is now (changes may have been written meanwhile),
        now.model = mdl.load(p.model.path.parent)      # never put in place of the caller's
        if ver.version(now.model.spec) != out["version"]:
            out["moved_on"] = "the model changed while the redesigner worked: its edits made again on the model as it is"
        got = rd.submit(now, by, raw)
        out["result"] = got["status"]
        out["id"] = got["id"]
        out["why_not"] = got.get("why")
        if got.get("scorecard"):
            out["scorecard"] = got["scorecard"]
    return out


result_line = md.result_line
