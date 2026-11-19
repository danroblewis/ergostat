"""A change set judged as a whole (SPEC §12e, *Redesign*), by what a modeller cares about, the model as it is and the
scratch copy each measured on the same record:

- **findings**: what ``check`` finds (not the craft notes, not what no change to the model answers), resolved and
  introduced (a finding about a part renamed is the same finding);
- **chain pieces**: each kind's state stocks in groups no flow joins, beyond one a kind;
- **coherence**: each kind's score on the record (its agreements over its comparisons, ``coherence.py``), and the
  mismatches, the three views held against each other over the record as it is (what Blocks ↔ Process says of the runs
  of a block the change adds is left out: the record holds none of its runs, and cannot);
- **craft**: the craft notes closed and opened;
- **fit**: the replay's scaled error over the stocks both judge, not worse beyond ``TOLERANCE`` where it can be
  worked out (a fit made measurable counts for the change, one made unmeasurable against it);
- **behaviour kept**: what the old model explained (a stock its replay follows, an equation that explains its flow)
  the new still explains: still there (or renamed), no worse beyond the tolerance.

The verdict is **better** when the structural measures (findings, chains, coherence) improve (net) and none is worse,
the fit is no worse and no behaviour is lost (craft notes it opens are said beside it, and count against it only when
nothing else moves); **mixed** when something improves and something is worse; **no better** when nothing improves.
Whatever it says, the scorecard is kept and shown."""

from __future__ import annotations

import time

from ..spec.ir import Spec

TOLERANCE = 0.10            # the fit may rise by this share (and a trifle) and still be no worse
SLACK = 0.02                # ... a stock's scaled error by this much besides, on a short record
EXPLAINED = 0.5             # a stock whose replay's scaled error is at most this is explained by the model
EQ_EXPLAINED = 0.5          # an equation whose partial fit's R² is at least this explains its flow
EQ_DROP = 0.1               # ... and keeps doing so unless it falls by more than this
WEIGHTS = {"findings": 3.0, "pieces": 3.0, "mismatches": 2.0, "coherence": 4.0, "craft": 0.5, "lost": 5.0, "fit": 2.0}


def _skip(x) -> bool:
    from .requests import NOT_MODELLING
    return x.code in NOT_MODELLING or bool(getattr(getattr(x, "where", None), "template", None)) or not x.code


def findings(problems) -> set[str]:
    return {f"{x.code}@{x.about}" if x.about else x.code for x in problems
            if x.level not in ("error", "note") and not _skip(x)}


def notes(problems) -> set[str]:
    return {f"{x.code}@{x.about}" if x.about else x.code for x in problems if x.level == "note" and not _skip(x)}


def pieces(spec: Spec) -> dict[str, int]:
    """Each chained kind's state stocks: how many groups no flow joins."""
    from ..spec import chains
    out = {}
    for k, c in chains._kinds(spec).items():
        if k.startswith("ergostat."):
            continue
        stocks = set(c.stock_of.values()) | set(c.stages)
        parent = {s: s for s in stocks}

        def root(x, parent=parent):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for f in spec.flows.values():
            if f.source in parent and f.target in parent:
                parent[root(f.source)] = root(f.target)
        out[k] = len({root(s) for s in set(c.stock_of.values())})
    return out


UNSEEN = ("declared-not-seen-acting", "not-seen-acting")   # a block's runs on the record: none for a block not there then
# (and moved-without-its-block, of a flow only such blocks move: the record's moves along it had no run of theirs)


def coherence(p, spec: Spec, problems, since: float, until: float, new_blocks: set[str] | None = None) -> dict:
    """Each kind's score and the mismatches over the record. A block the change adds (or renames) has no runs on the
    record, so what Blocks ↔ Process says of its runs is left out (said as ``unseen``), not counted against it."""
    from .. import coherence as co
    try:
        got = co.compare(spec, p.events, since, until, [x for x in problems if x.level != "error"])
    except Exception as e:                          # a record that cannot be read now says nothing either way
        return {"kinds": {}, "mismatches": [], "error": f"{type(e).__name__}: {e}"}
    new_blocks = new_blocks or set()
    moved_new = {f"{t.kind}.{t.name}" for b in new_blocks if b[6:] in spec.blocks for t in spec.blocks[b[6:]].targets()}
    moved_old = {f"{t.kind}.{t.name}" for n, b in spec.blocks.items() if f"block.{n}" not in new_blocks for t in b.targets()}
    unseen = [f for f in got["findings"] if f["level"] == "mismatch" and (
        (f["code"] in UNSEEN and f["about"] in new_blocks) or
        (f["code"] == "moved-without-its-block" and f["about"] in moved_new and f["about"] not in moved_old))]
    less = {}
    for f in unseen:
        less[f["kind"]] = less.get(f["kind"], 0) + 1
    kinds = {k: {"agree": x["agree"], "compared": max(x["agree"], x["compared"] - less.get(k, 0))} for k, x in got["kinds"].items()
             if not k.startswith("ergostat.") and x["compared"]}
    gone = {f["id"] for f in unseen}
    mm = sorted({f["id"] for f in got["findings"] if f["level"] == "mismatch" and f["id"] not in gone
                 and not str(f.get("kind") or "").startswith("ergostat.")})
    return {"kinds": kinds, "mismatches": mm, "unseen": sorted(gone)}


def fit(p, spec: Spec) -> dict:
    from . import observe as ob
    from . import trial as tr
    try:
        data = ob.measured(p, ob.reference(p), spec)
        _, f = tr.fit_of(spec, data)
    except Exception as e:
        return {"total": None, "stocks": {}, "equations": {}, "why": f"{type(e).__name__}: {e}"}
    return f


class _Aliased:
    """The record's measurements, a renamed part's new series reading its old one: what Accept will copy across
    (``proposals.keep_history``), seen before it is written, so the change set is replayed on the record it will have."""

    def __init__(self, inner, alias: dict[str, str]):
        self._inner, self._alias = inner, alias

    def _s(self, series: str) -> str:
        return self._alias.get(series, series)

    def range(self, series, *a, **k):
        return self._inner.range(self._s(series), *a, **k)

    def bucketed(self, series, *a, **k):
        return self._inner.bucketed(self._s(series), *a, **k)

    def first(self, series, *a, **k):
        return self._inner.first(self._s(series), *a, **k)

    def latest(self, series, *a, **k):
        return self._inner.latest(self._s(series), *a, **k)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def with_history(p, after: Spec, renames: dict[str, str]):
    """The project as the change set's replay sees it: its renamed parts' readings under their new names."""
    import copy
    alias = {}
    for old, new in renames.items():
        kind, _, oname = old.partition(".")
        nkind, _, nname = new.partition(".")
        x = after.measured(nkind).get(nname) if nkind in ("stock", "flow", "auxiliary") else None
        for sn, sen in (getattr(x, "sensors", None) or {}).items():
            alias[sen.series] = f"sensor/{oname}.{sn}"
    if not alias:
        return p
    q = copy.copy(p)
    q.measurements = _Aliased(p.measurements, alias)
    return q


def _level(f: dict | None) -> float | None:
    """The replay's scaled error: the model's total, else (a record too short for a total) the mean over the stocks the
    replay follows; None when it follows none."""
    from . import gate as gt
    t = gt.total(f)
    if t is not None:
        return t
    xs = [_nmse(x) for x in ((f or {}).get("stocks") or {}).values()]
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _renamed(ref: str, renames: dict[str, str]) -> str:
    return renames.get(ref, ref)


def _fid(fid: str, renames: dict[str, str]) -> str:
    code, _, about = fid.partition("@")
    return f"{code}@{renames.get(about, about)}" if about else fid


def _nmse(s: dict | None) -> float | None:
    if not s or s.get("too_little") or s.get("nmse") is None:
        return None
    return float(s["nmse"])


def score(p, before: Spec, problems_before, after: Spec, problems_after, window: float | None = None,
          at: float | None = None, fit_before: dict | None = None) -> dict:
    """The scorecard: each measure before and after, what moved, and the verdict with why."""
    from .. import coherence as co
    from . import gate as gt
    from .changeset import parts_changed
    until = at or time.time()
    since = until - (window or co.WINDOW)
    parts = parts_changed(before, after)
    renames = dict(x.split(" → ") for x in parts["renamed"])
    fb, fa = findings(problems_before), findings(problems_after)
    fb_r = {_fid(x, renames) for x in fb}
    nb, na = notes(problems_before), notes(problems_after)
    nb_r = {_fid(x, renames) for x in nb}
    pb, pa = pieces(before), pieces(after)
    new_blocks = {f"block.{n}" for n in after.blocks if n not in before.blocks}
    cb = coherence(p, before, problems_before, since, until)
    ca = coherence(p, after, problems_after, since, until, new_blocks)
    ftb = fit_before or fit(p, before)
    fta = fit(with_history(p, after, renames), after)
    # the fit, like for like over the stocks both judge (a renamed stock is the same stock)
    b_st = {_renamed(r, renames): s for r, s in (ftb.get("stocks") or {}).items()}
    fit_b = {**ftb, "stocks": b_st}
    lfl = gt.like_for_like(fit_b, fta)
    tb, ta = _level(ftb), _level(fta)
    fit_card = {"before": lfl["before"], "after": lfl["after"], "stocks": lfl["stocks"], "total_before": tb, "total_after": ta,
                "measurable_before": tb is not None, "measurable_after": ta is not None}
    if tb is None and ta is None:
        short = any((x or {}).get("too_little") for f_ in (ftb, fta) for x in (f_.get("stocks") or {}).values())
        fit_card["says"] = "cannot be worked out, before or after: " + str(
            ftb.get("why") or (ftb.get("total") or {}).get("says") or
            ("too little record to judge the replay of the stocks it follows" if short else "no stock is replayed"))
        fit_card["worse"] = False
    elif tb is not None and ta is None:
        fit_card["says"] = "measurable before, not after: the change leaves nothing the replay can follow"
        fit_card["worse"] = True
    elif tb is None:
        n = len([1 for x in (fta.get("stocks") or {}).values() if _nmse(x) is not None])
        fit_card["says"] = (f"made measurable: scaled error {ta:.3g}" + ("" if gt.total(fta) is not None else
                            f", the mean over the {n} stock{'s' if n != 1 else ''} the replay follows") +
                            "; its parameters are first guesses until the record fits them (estimate: true)")
        fit_card["worse"] = False
        fit_card["made_measurable"] = True
    else:
        b, a = lfl["before"], lfl["after"]
        fit_card["worse"] = bool(b is not None and a is not None and a > b * (1 + TOLERANCE) + 1e-4)
        fit_card["says"] = gt.said(b, a) + (f" (over the {lfl['stocks']} stocks both replay)" if lfl["stocks"] else "")
    # behaviour kept: what the old model explained, the new still explains
    lost = []
    for r, s in b_st.items():
        b = _nmse(s)
        if b is None or b > EXPLAINED:
            continue
        a = _nmse((fta.get("stocks") or {}).get(r))
        if r.split(".", 1)[1] not in after.stocks:
            lost.append(f"{r}: its replay followed the record (scaled error {b:.3g}), and the change takes it away")
        elif a is None:
            lost.append(f"{r}: its replay followed the record (scaled error {b:.3g}); with the change it is not replayed")
        elif a > b * (1 + TOLERANCE) + SLACK:
            lost.append(f"{r}: its replay followed the record; {gt.said(b, a)}")
    for r, s in (ftb.get("equations") or {}).items():
        r2 = (s or {}).get("r2")
        if r2 is None or r2 < EQ_EXPLAINED:
            continue
        r_a = _renamed(r, renames)
        a = ((fta.get("equations") or {}).get(r_a) or {}).get("r2")
        if a is None or a < r2 - EQ_DROP:
            lost.append(f"{r}: its equation explained its flow (R² {r2:.2f}); with the change "
                        + ("it has none that is fitted" if a is None else f"R² {a:.2f}"))
    # coherence per kind, over the kinds both compare
    kinds = {}
    for k in sorted(set(cb["kinds"]) | set(ca["kinds"])):
        x, y = cb["kinds"].get(k), ca["kinds"].get(k)
        kinds[k] = {"before": _share(x), "after": _share(y), "said_before": _ratio(x), "said_after": _ratio(y)}
    coh_up = sum(1 for v in kinds.values() if v["before"] is not None and v["after"] is not None and v["after"] > v["before"] + 1e-9)
    coh_down = [k for k, v in kinds.items() if v["before"] is not None and (v["after"] is None or v["after"] < v["before"] - 1e-9)]
    card = {
        "findings": {"before": len(fb), "after": len(fa), "resolved": sorted(fb_r - fa), "introduced": sorted(fa - fb_r)},
        "pieces": {"before": sum(max(0, n - 1) for n in pb.values()), "after": sum(max(0, n - 1) for n in pa.values()),
                   "by_kind": {k: {"before": pb.get(k), "after": pa.get(k)} for k in sorted(set(pb) | set(pa))}},
        "coherence": {"kinds": kinds, "mismatches_before": len(cb["mismatches"]), "mismatches_after": len(ca["mismatches"]),
                      "resolved": sorted(set(cb["mismatches"]) - set(ca["mismatches"])),
                      "introduced": sorted(set(ca["mismatches"]) - set(cb["mismatches"])), "since": since, "until": until,
                      "unseen": ca.get("unseen") or []},
        "craft": {"before": len(nb), "after": len(na), "closed": sorted(nb_r - na), "opened": sorted(na - nb_r)},
        "fit": fit_card,
        "lost": lost,
        "parts": parts,
    }
    card["verdict"], card["why"], card["score"] = verdict(card, coh_up, coh_down)
    return card


def _share(x: dict | None) -> float | None:
    return x["agree"] / x["compared"] if x and x["compared"] else None


def _ratio(x: dict | None) -> str | None:
    return f"{x['agree']}/{x['compared']}" if x and x["compared"] else None


def verdict(card: dict, coh_up: int = 0, coh_down: list | None = None) -> tuple[str, str, float]:
    """Better, mixed or no better, with why, and a number to rank change sets by (higher is better)."""
    coh_down = coh_down or []
    f, pc, co, cr, ft = card["findings"], card["pieces"], card["coherence"], card["craft"], card["fit"]
    net_f = len(f["resolved"]) - len(f["introduced"])
    net_p = pc["before"] - pc["after"]
    net_m = co["mismatches_before"] - co["mismatches_after"]
    net_c = len(cr["closed"]) - len(cr["opened"])
    good, bad = [], []
    if net_f > 0:
        good.append(f"{len(f['resolved'])} finding{'s' if len(f['resolved']) != 1 else ''} resolved"
                    + (f", {len(f['introduced'])} introduced" if f["introduced"] else ""))
    elif net_f < 0 or (f["introduced"] and net_f == 0 and f["resolved"]):
        bad.append(f"{len(f['introduced'])} finding{'s' if len(f['introduced']) != 1 else ''} introduced "
                   f"({', '.join(f['introduced'][:3])}), {len(f['resolved'])} resolved")
    if net_p > 0:
        good.append(f"the chains joined ({pc['before']} → {pc['after']} pieces beyond one a kind)")
    elif net_p < 0:
        bad.append(f"the chains in more pieces ({pc['before']} → {pc['after']} beyond one a kind)")
    if net_m > 0:
        good.append(f"{net_m} coherence mismatch{'es' if net_m != 1 else ''} fewer on the record")
    elif net_m < 0:
        bad.append(f"{-net_m} coherence mismatch{'es' if net_m != -1 else ''} more on the record ({', '.join(co['introduced'][:3])})")
    if coh_up and not coh_down:
        good.append(f"coherence up for {coh_up} kind{'s' if coh_up != 1 else ''}")
    if coh_down:
        bad.append(f"coherence down for {', '.join(coh_down)}")
    caveat = []
    if net_c > 0:
        good.append(f"{net_c} craft note{'s' if net_c != 1 else ''} closed")
    elif net_c < 0:                                  # the craft is secondary: said, and against it only when nothing
        caveat.append(f"{-net_c} craft note{'s' if net_c != -1 else ''} more ({', '.join(cr['opened'][:3])})")   # else moves
    if ft.get("made_measurable"):
        good.append("the fit made measurable")
    if ft.get("worse"):
        bad.append(f"the fit worse: {ft['says']}")
    if card["lost"]:
        bad.append(f"behaviour lost: {'; '.join(card['lost'][:2])}")
    w = WEIGHTS
    num = (w["findings"] * net_f + w["pieces"] * net_p + w["mismatches"] * net_m + w["coherence"] * (coh_up - len(coh_down))
           + w["craft"] * net_c + w["fit"] * (1 if ft.get("made_measurable") else -1 if ft.get("worse") else 0)
           - w["lost"] * len(card["lost"]))
    tail = f" (though {'; '.join(caveat)})" if caveat else ""
    if good and not bad:
        return "better", "better: " + "; ".join(good) + ", with the fit no worse and nothing it explained lost" + tail, num
    if good:
        return "mixed", "mixed: " + "; ".join(good) + "; but " + "; ".join(bad) + tail, num
    if bad or caveat:
        return "no better", "no better: " + "; ".join(bad + caveat), num
    return "no better", "no better: no structural measure moves", num


def lines(card: dict) -> list[str]:
    """The scorecard as the command line prints it."""
    f, pc, co, cr, ft = card["findings"], card["pieces"], card["coherence"], card["craft"], card["fit"]
    out = [f"verdict     {card['why']}",
           f"findings    {f['before']} → {f['after']}  (resolved {len(f['resolved'])}, introduced {len(f['introduced'])})",
           f"chains      {pc['before']} → {pc['after']} pieces beyond one a kind"
           + ("  (" + ", ".join(f"{k} {v['before']}→{v['after']}" for k, v in pc["by_kind"].items()) + ")" if pc["by_kind"] else ""),
           f"coherence   mismatches {co['mismatches_before']} → {co['mismatches_after']}"
           + ("  (" + ", ".join(f"{k} {v['said_before'] or '–'}→{v['said_after'] or '–'}" for k, v in co["kinds"].items()) + ")"
              if co["kinds"] else ""),
           f"craft       notes {cr['before']} → {cr['after']}  (closed {len(cr['closed'])}, opened {len(cr['opened'])})",
           f"fit         {ft.get('says')}"]
    for x in card["lost"]:
        out.append(f"lost        {x}")
    pt = card["parts"]
    out.append("parts       " + "; ".join(f"{k} {len(v)}" for k, v in pt.items() if v))
    return out
