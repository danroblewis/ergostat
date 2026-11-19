"""``ergostat bench``: how we know the improver works (docs/MODEL-TOOLS.md). ``bench improve`` runs the recovery
benchmark (a true model damaged, the improvement loop run on it, scored against the truth); ``bench judge`` measures
the judge alone on changes known better, worse or neutral; ``bench meta`` prints the loop's own measures for this
project. ``ergostat verify`` is the live prediction check, run by a block like the judge."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path


def register(sub, common) -> None:
    b = sub.add_parser("bench", parents=[common], help="How we know the improver works: the recovery benchmark, the "
                                                       "judge's error rates, the loop's own measures")
    bs = b.add_subparsers(dest="bench")
    im = bs.add_parser("improve", help="damage true models, run the improvement loop on each, score it against the truth")
    im.add_argument("--improver", choices=["standin", "calibrator", "ai"], default="standin",
                    help="who proposes: the stand-in (default), the calibrator (the calibration's estimates, as the "
                         "examples' stand-ins do), or an AI agent")
    im.add_argument("--model", default="sonnet", help="with --improver ai: the model (default sonnet)")
    im.add_argument("--cases", metavar="LIST", help="cases by id, prefix or tag:NAME, comma-separated (default: all)")
    im.add_argument("--rounds", type=int, default=6, help="rounds of propose and judge, two hours of record each (default 6)")
    im.add_argument("--seed", type=int, default=1, help="the measurement noise's seed")
    im.add_argument("--out", metavar="DIR", help="where the scorecard goes (default ./bench-IMPROVER)")
    im.add_argument("--keep", action="store_true", help="keep each case's model and record under DIR/work")
    im.add_argument("--list", action="store_true", help="list the cases and their defects")
    im.add_argument("--suite", choices=["all", "values", "craft"], default="all",
                    help="the planted values and structure on the truth's record (values), the craft and chain defects "
                         "planted in the examples, answered by the modelling tiers (craft; the rule tier, and with "
                         "--improver ai the AI tier too), or both (default)")
    im.add_argument("--json", action="store_true", help="print the scorecard as JSON")
    jd = bs.add_parser("judge", help="the judge's false-accept and false-reject rates over many seeds")
    jd.add_argument("--seeds", type=int, default=20)
    jd.add_argument("--json", action="store_true")
    bs.add_parser("meta", parents=[common], help="the improvement loop's own measures, for this project")
    _parity(bs)
    b.set_defaults(fn=cmd_bench)
    v = sub.add_parser("verify", parents=[common], help="Score the changes written to the model again, on the record "
                                                        "since; flag the ones whose forecasts got worse")
    v.add_argument("--propose", action="store_true", help="propose undoing a change flagged (the judge and the owner decide)")
    v.set_defaults(fn=cmd_verify)


def _parity(bs) -> None:
    from .bench_parity import register
    register(bs)


def _g(x) -> str:
    return "–" if x is None else f"{x:.4g}" if isinstance(x, float) else str(x)


def cmd_bench(args) -> int:
    which = getattr(args, "bench", None)
    if which == "improve":
        return _improve(args)
    if which == "judge":
        from ..bench import judging
        trials, got = judging.run(args.seeds)
        if args.json:
            print(json.dumps(got, indent=1, default=str))
            return 0
        print(f"{got['trials']} trials: false accepts {got['false_accepts']} (rate {_g(got['false_accept_rate'])}), "
              f"false rejects {got['false_rejects']} (rate {_g(got['false_reject_rate'])})")
        for k, v in got["written_by_kind"].items():
            print(f"  {k}: written {v}")
        for t in got["false_reject_examples"]:
            print(f"  rejected though better: {t['world']} {t['family']} seed {t['seed']}: {t['why']}")
        return 0 if not got["false_accepts"] else 1
    if which == "meta":
        from ..numbers import meta
        from .common import open_project
        p = open_project(args)
        got = meta.all_of(p)
        if args.json:
            print(json.dumps(got))
            return 0
        for n, v in got.items():
            print(f"{n:36s} {_g(v):>10s}  {meta.MEASURES[n]}")
        return 0
    if which == "parity":
        from .bench_parity import cmd_parity
        return cmd_parity(args)
    print("ergostat bench improve | judge | meta | parity (ergostat bench --help)", file=sys.stderr)
    return 2


def _craft(args) -> int:
    from ..bench import craft
    names = [x.strip() for x in (args.cases or "").split(",") if x.strip()] or None
    if args.list:
        for c in craft.CASES:
            print(f"{c.id:26s} {', '.join(d.kind for d in c.defects) or '(from the example)'}")
        return 0
    out = Path(args.out or f"bench-{args.improver}")
    work = out / "work" if args.keep else Path(tempfile.mkdtemp(prefix="ergostat-bench-craft-"))
    improver = "ai" if args.improver == "ai" else "rules"
    model = args.model if args.model != "sonnet" or args.improver == "ai" else "haiku"
    got = craft.bench(work, out, improver, model, [n for n in names or [] if n in {c.id for c in craft.CASES}] or None)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps(got, indent=1, default=str) if args.json else (out / "craft.md").read_text())
    return 0


def _improve(args) -> int:
    if getattr(args, "suite", "all") in ("craft", "all"):
        code = _craft(args)
        if args.suite == "craft" or code:
            return code
    from ..bench import improvers, recovery, truth
    names = [x.strip() for x in (args.cases or "").split(",") if x.strip()] or None
    try:
        cases = truth.select(names)
    except KeyError as e:
        print(e, file=sys.stderr)
        return 2
    if args.list:
        for c in cases:
            print(f"{c.id:26s} {', '.join(d['kind'] for d in c.defects):40s} {c.title}")
        return 0
    out = Path(args.out or f"bench-{args.improver}")
    work = out / "work" if args.keep else Path(tempfile.mkdtemp(prefix="ergostat-bench-"))
    imp = improvers.make(args.improver, args.model)
    results = []
    for c in cases:
        before = dict(imp.cost)
        s = recovery.prepare(c, work / c.id, seed=args.seed, rounds=args.rounds)
        r = recovery.run(s, imp)
        r.cost = {**{k: round(v - before.get(k, 0), 4) if isinstance(v, int | float) else v for k, v in imp.cost.items()},
                  "rounds": r.cost["rounds"], "seconds": r.cost["seconds"]}
        results.append(r)
        sc = r.scores
        print(f"{c.id:26s} fixed {sum(d['fixed'] for d in sc['defects'])}/{len(sc['defects'])}, proposals "
              f"{sc['proposals']} ({sc['real_fixes']} real), accepted {sc['accepted']} ({sc['damage']} damaging), fit "
              f"{_g(sc['fit']['damaged'])} → {_g(sc['fit']['final'])} (truth {_g(sc['fit']['truth'])})", file=sys.stderr)
    j, m = recovery.save(results, out)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print(j.read_text() if args.json else m.read_text())
    print(f"written: {m}, {j}", file=sys.stderr)
    return 0


def cmd_verify(args) -> int:
    from ..numbers import verify
    from .common import open_project
    p = open_project(args)
    got = verify.run(p, propose=args.propose)
    if getattr(args, "json", False):
        print(json.dumps(got, default=str))
        return 0
    for k in ("verified", "regressed"):
        for x in got[k]:
            print(f"{x['id']}  {k}: {x['why']}")
    for x in got["unjudged"]:
        print(f"{x['id']}  not judged: {x['why']}")
    if got["waiting"]:
        print(f"{len(got['waiting'])} written too recently to check")
    if not any(got.values()):
        print("no change written to the model yet")
    return 0
