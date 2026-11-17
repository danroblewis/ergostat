"""``ergostat bench parity``: does a fresh session, given a starting context, know what a long session knew
(docs/parity-bench.md)? ``run`` asks every case under every variant and judges the answers; ``context`` writes a
built-in starting context; ``draft`` drafts cases from a transcript with an AI pass."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def register(bs) -> None:
    pa = bs.add_parser("parity", help="the parity benchmark: fresh sessions from given contexts, judged against what "
                                      "the owner said")
    ps = pa.add_subparsers(dest="parity")
    r = ps.add_parser("run", help="ask every case under every variant, judge, write the scorecard")
    r.add_argument("--cases", required=True, metavar="FILE", help="the cases (JSON lines or a JSON list)")
    r.add_argument("--variant", action="append", default=[], metavar="NAME=FILE",
                   help="a starting context, as plain text (repeat; 'none' for no context). Any projection is a file: "
                        "ergostat bench parity context ..., ergostat context ... > FILE")
    r.add_argument("--out", required=True, metavar="DIR", help="answers.jsonl, scorecard.md, scorecard.json; a run "
                                                               "again on the same DIR runs only what is missing")
    r.add_argument("--model", default="sonnet", help="the answering model (default sonnet)")
    r.add_argument("--judge-model", default="sonnet", help="the judge's model (default sonnet)")
    r.add_argument("--max-usd", type=float, help="stop starting cases once this much is spent (answers and judging, "
                                                 "counting what DIR already holds)")
    r.add_argument("--workers", type=int, default=4, help="sessions at once within a variant (default 4)")
    r.add_argument("--only", metavar="IDS", help="only these cases, comma-separated")
    r.add_argument("--repo", metavar="DIR", help="where a case with read-only tools reads (default: none may)")
    r.add_argument("--json", action="store_true", help="print the scorecard as JSON")
    c = ps.add_parser("context", help="write a built-in starting context to stdout")
    c.add_argument("kind", choices=["none", "docs", "owner", "fork", "memory"])
    c.add_argument("--repo", metavar="DIR", default=".", help="docs: the repository (default .)")
    c.add_argument("--transcript", metavar="FILE", help="owner, fork: a Claude Code session's JSONL")
    c.add_argument("--dir", metavar="DIR", help="memory: the memory directory")
    c.add_argument("--budget", type=int, help="owner, fork: characters at most (default 100000)")
    c.add_argument("--last", type=int, help="fork: at most this many turns")
    d = ps.add_parser("draft", help="draft cases from a transcript with an AI pass, each quote checked against it")
    d.add_argument("--transcript", required=True, metavar="FILE")
    d.add_argument("--out", required=True, metavar="FILE", help="the drafted cases, JSON lines")
    d.add_argument("--parts", type=int, default=3, help="the owner's messages read in this many parts (default 3)")
    d.add_argument("--questions", type=int, default=14, help="questions a part (default 14)")
    d.add_argument("--tasks", type=int, default=3, help="tasks a part (default 3)")
    d.add_argument("--model", default="sonnet")


def cmd_parity(args) -> int:
    which = getattr(args, "parity", None)
    if which == "run":
        return _run(args)
    if which == "context":
        return _context(args)
    if which == "draft":
        return _draft(args)
    print("ergostat bench parity run | context | draft (ergostat bench parity --help)", file=sys.stderr)
    return 2


def _say(s: str) -> None:
    print(s, file=sys.stderr, flush=True)


def _run(args) -> int:
    from ..bench import parity as pb
    try:
        cases = pb.load_cases(Path(args.cases))
        variants = pb.load_variants(args.variant or ["none"])
    except (OSError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c.id in want]
    repo = Path(args.repo).resolve() if args.repo else None
    card = pb.run(cases, variants, pb.Claude(args.model, repo=repo), pb.Claude(args.judge_model), Path(args.out),
                  workers=args.workers, max_usd=args.max_usd, say=_say)
    out = Path(args.out)
    print(json.dumps(card, indent=1) if args.json else (out / "scorecard.md").read_text(encoding="utf-8"))
    _say(f"written: {out / 'scorecard.md'}, {out / 'scorecard.json'}")
    return 0


def _context(args) -> int:
    from ..bench import contexts as cx
    k = args.kind
    budget = args.budget or cx.BUDGET
    if k in ("owner", "fork") and not args.transcript:
        print(f"{k} needs --transcript FILE", file=sys.stderr)
        return 2
    if k == "memory" and not args.dir:
        print("memory needs --dir DIR", file=sys.stderr)
        return 2
    text = {"none": lambda: cx.none(), "docs": lambda: cx.docs(Path(args.repo)),
            "owner": lambda: cx.owner(Path(args.transcript), budget),
            "fork": lambda: cx.fork(Path(args.transcript), budget, args.last),
            "memory": lambda: cx.memory(Path(args.dir))}[k]()
    sys.stdout.write(text)
    return 0


def _draft(args) -> int:
    from ..bench import parity as pb
    from ..bench import parity_draft as pd
    rows, usd = pd.draft(Path(args.transcript), pb.Claude(args.model, timeout=900), args.parts, args.questions, args.tasks,
                         say=_say)
    Path(args.out).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    ok = sum(r["verified"] for r in rows)
    _say(f"{len(rows)} cases drafted ({ok} with every quote found at its lines), ${usd:.2f}: {args.out}")
    return 0
