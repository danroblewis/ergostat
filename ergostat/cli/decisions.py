"""``ergostat decisions``, ``ergostat corrections`` and ``ergostat context``: the owner's intent kept as items
(``ergostat.decision``, ``ergostat.correction``), proposed by the extractor or a person and decided by the
owner; and the projections that put the confirmed ones at the start of a session."""

from __future__ import annotations

import json
import sys

from ..decisions import acts
from ..decisions.kinds import CORRECTION, DECISION


def register(sub, common) -> None:
    d = sub.add_parser("decisions", parents=[common], help="The owner's decisions: extract them from transcripts, propose, "
                                                           "confirm, dismiss, supersede")
    ds = d.add_subparsers(dest="act")
    ex = ds.add_parser("extract", parents=[common], help="propose the decisions and corrections in Claude Code transcripts "
                                                         "(--since: from a line, 4000; a time, 2026-11-16T09:00; or ago, 2d)")
    ex.add_argument("paths", nargs="+", metavar="TRANSCRIPT", help="a session's .jsonl, a folder of them, or a session "
                                                                  "item whose transcript the record holds (claude.* events)")
    ex.add_argument("--model", help="the AI extractor, on this model (sonnet); without it, the stand-in (no tokens)")
    ex.add_argument("--max-cost", type=float, metavar="USD", help="with --model: stop before spending more than this")
    ex.add_argument("--prompt", metavar="FILE", help="with --model: the extractor's instructions (- for standard input, as an "
                                                    "ai block gives its prompt); default: ergostat's own")
    ex.add_argument("--new", action="store_true", help="only the lines added since the last --new run (for a block)")
    ex.add_argument("--print", dest="print_lines", action="store_true",
                    help="print the proposals as event lines instead of recording them (for a block: the engine records them)")
    ex.add_argument("--as", dest="by", default="extractor", help="who proposes them (default: extractor)")
    pr = ds.add_parser("propose", parents=[common], help="propose a decision (the owner's own, or with their words)")
    pr.add_argument("text", help="the decision, one sentence")
    _proposal_flags(pr)
    pr.add_argument("--reason", action="append", default=[], help="why (repeat for several)")
    pr.add_argument("--rejected", action="append", default=[], metavar="OPTION[: WHY]", help="an alternative rejected")
    pr.add_argument("--supersedes", action="append", default=[], metavar="ID", help="a decision it would replace")
    for name, help in (("confirm", "confirm a proposed decision (the owner's act)"),
                       ("dismiss", "dismiss a proposed decision, with --reason"),
                       ("supersede", "replace a confirmed decision: --by ID and --reason")):
        a = ds.add_parser(name, parents=[common], help=help)
        a.add_argument("id", help="its id, or the slug after ergostat.decision/")
        a.add_argument("--reason", help="why" + (" (required)" if name != "confirm" else ""))
        if name == "supersede":
            a.add_argument("--by", dest="by_decision", required=True, help="the decision that replaces it")
    ls = ds.add_parser("list", parents=[common], help="the decisions, by state")
    ls.add_argument("--state", help="only these (proposed, confirmed, superseded, dismissed)")
    d.set_defaults(fn=cmd_decisions)

    c = sub.add_parser("corrections", parents=[common], help="The owner's corrections: propose, confirm, dismiss, retire, "
                                                             "scan the record for them")
    cs = c.add_subparsers(dest="act")
    pr = cs.add_parser("propose", parents=[common], help="propose a correction (the owner's own, or with their words)")
    pr.add_argument("text", help="the correction, one sentence: what to do differently")
    _proposal_flags(pr)
    pr.add_argument("--corrects", help="the behaviour or result it corrects")
    pr.add_argument("--kind", dest="kind_of_work", action="append", default=[], help="the kind of work it applies to")
    pr.add_argument("--repeats", metavar="ID", help="the earlier correction it gives again")
    for name, help in (("confirm", "confirm a proposed correction (the owner's act)"),
                       ("dismiss", "dismiss a proposed correction, with --reason"),
                       ("retire", "retire a confirmed correction that no longer applies, with --reason")):
        a = cs.add_parser(name, parents=[common], help=help)
        a.add_argument("id", help="its id, or the slug after ergostat.correction/")
        a.add_argument("--reason", help="why" + (" (required)" if name != "confirm" else ""))
    cs.add_parser("scan", parents=[common], help="propose the corrections the record holds: dismissals with a reason, items "
                                                 "reopened, messages classed as corrections")
    ls = cs.add_parser("list", parents=[common], help="the corrections, by state, with their repeats")
    ls.add_argument("--state", help="only these (proposed, confirmed, retired, dismissed)")
    c.set_defaults(fn=cmd_corrections)

    x = sub.add_parser("context", parents=[common], help="A starting context for a session, as Markdown: a recipe "
                                                         "under contexts:, or decisions, corrections")
    x.add_argument("recipe", nargs="?", help="a recipe (ergostat context --list), or decisions or corrections")
    x.add_argument("--item", help="a recipe: the item the work is on (its history, its parts, the owner's words on it)")
    x.add_argument("--block", help="a recipe: the block the context is for (its findings, {block})")
    x.add_argument("--list", action="store_true", help="the recipes: each one's version and parts")
    x.add_argument("--outcomes", action="store_true", help="each recipe's uses and how the work they started turned "
                                                           "out, over the last week")
    x.add_argument("--scope", help="decisions: the parts or topic the session works on (most relevant first)")
    x.add_argument("--kind", help="corrections: the kind of work (ui, docs, git, testing, modelling, ...)")
    x.add_argument("--budget", help="its size: characters (6000, the default 8000) or tokens (1500t)")
    x.add_argument("--proposed", action="store_true", help="also the ones still waiting for the owner, marked so")
    x.set_defaults(fn=cmd_context)


def _proposal_flags(pr) -> None:
    pr.add_argument("--words", action="append", default=[], help="the owner's words, verbatim (repeat for several); "
                                                                  "left out, the sentence is the owner's own")
    pr.add_argument("--session", help="with --words: the session they were said in")
    pr.add_argument("--line", type=int, help="with --words: the transcript's line")
    pr.add_argument("--scope", action="append", default=[], help="a part or topic it applies to (repeat for several)")
    pr.add_argument("--as", dest="by", default="owner", help="who proposes it (default: owner)")


def _say(got: dict, args) -> int:
    if getattr(args, "json", False):
        print(json.dumps(got, default=str))
    else:
        print(" ".join(f"{k}: {v}" for k, v in got.items() if k != "event"))
    return 0


def _list(p, kind: str, args) -> int:
    from .common import c
    its = [i for i in acts.items(p, kind) if not args.state or i.state == args.state]
    if args.json:
        print(json.dumps([i.as_dict() for i in its], default=str))
        return 0
    key = "decision" if kind == DECISION else "correction"
    counts: dict[str, int] = {}
    for i in acts.items(p, kind):
        counts[i.state] = counts.get(i.state, 0) + 1
    print(", ".join(f"{n} {s}" for s, n in counts.items()) or f"no {key}s yet")
    for i in its:
        rep = f"  repeats {i.fields['repeats']}" if i.fields.get("repeats") else ""
        print(f"{c(i.state, 'accent'):<12} {i.id}{rep}\n    {i.fields.get(key, '')}")
    return 0


def _words(args) -> list[dict]:
    return [{"text": w, **({"session": args.session} if args.session else {}), **({"line": args.line} if args.line else {})}
            for w in args.words]


def _act(fn) -> int:
    try:
        got = fn()
    except acts.ActError as e:
        print(e, file=sys.stderr)
        return 2
    return got


def cmd_decisions(args) -> int:
    from .common import open_project
    act = getattr(args, "act", None)
    if act is None:
        print("ergostat decisions extract | propose | confirm | dismiss | supersede | list (--help)", file=sys.stderr)
        return 2
    p = open_project(args)
    if act == "extract":
        return _extract(p, args)
    if act == "list":
        return _list(p, DECISION, args)
    if act == "propose":
        alts = [dict(zip(("option", "why"), [x.strip() for x in r.split(":", 1)], strict=False)) for r in args.rejected]
        data = {"decision": args.text, "words": _words(args), "scope": args.scope, "reasons": args.reason,
                "alternatives": alts, "supersedes": args.supersedes}
        return _act(lambda: _say(acts.propose(p, DECISION, data, args.by), args))
    if act == "confirm":
        return _act(lambda: _say(acts.confirm(p, DECISION, args.id, args.reason), args))
    if act == "dismiss":
        return _act(lambda: _say(acts.dismiss(p, DECISION, args.id, args.reason), args))
    return _act(lambda: _say(acts.supersede(p, args.id, args.by_decision, args.reason), args))


def _extract(p, args) -> int:
    from ..decisions import ai, extract
    instructions = None
    if args.prompt == "-":
        raw = sys.stdin.read()
        instructions = ai.strip_block_footer(raw) if raw.strip() and not raw.lstrip().startswith("{") else None
    elif args.prompt:
        from pathlib import Path
        instructions = Path(args.prompt).read_text(encoding="utf-8")
    try:
        got = extract.run(p, args.paths, since=getattr(args, "since", None), model=args.model, cap=args.max_cost,
                          instructions=instructions, print_lines=args.print_lines, new=args.new, source=args.by)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    if args.print_lines:
        return 0
    if args.json:
        print(json.dumps(got, default=str))
        return 0
    n = got["proposed"]
    print(f"{got['owner_turns']} owner turns read ({got['extractor']}{', ' + got['model'] if got.get('model') else ''}): "
          f"{n['decision']} decisions and {n['correction']} corrections proposed, {got['known']} already known, "
          f"{got['repeats']} repeats, {len(got['refused'])} refused")
    if got.get("spent"):
        s = got["spent"]
        print(f"spent ${s['cost_usd']:.2f} over {s['calls']} calls ({s['tokens_in']} tokens in, {s['tokens_out']} out); "
              f"{s['dropped_unquoted']} findings dropped for a quote not found" + (f"; {s['stopped']}" if s.get("stopped") else ""))
    for r in got["refused"][:5]:
        print(f"  refused: {r}")
    print("They wait for the owner: ergostat decisions list --state proposed, or Items → ergostat.decision.")
    return 0


def cmd_corrections(args) -> int:
    from .common import open_project
    act = getattr(args, "act", None)
    if act is None:
        print("ergostat corrections propose | confirm | dismiss | retire | scan | list (--help)", file=sys.stderr)
        return 2
    p = open_project(args)
    if act == "list":
        return _list(p, CORRECTION, args)
    if act == "scan":
        from ..decisions import fromrecord
        got = fromrecord.scan(p, getattr(p.model, "spec", None))
        return _say({k: v for k, v in got.items() if k != "items"}, args)
    if act == "propose":
        data = {"correction": args.text, "words": _words(args), "scope": args.scope, "corrects": args.corrects,
                "kind_of_work": args.kind_of_work, **({"repeats": args.repeats} if args.repeats else {})}
        return _act(lambda: _say(acts.propose(p, CORRECTION, data, args.by), args))
    if act == "confirm":
        return _act(lambda: _say(acts.confirm(p, CORRECTION, args.id, args.reason), args))
    if act == "dismiss":
        return _act(lambda: _say(acts.dismiss(p, CORRECTION, args.id, args.reason), args))
    return _act(lambda: _say(acts.retire(p, args.id, args.reason), args))


def cmd_context(args) -> int:
    from ..decisions import context as cx
    from .common import open_project
    p = open_project(args)
    try:
        budget = cx.budget_of(args.budget) if args.budget or args.recipe in ("decisions", "corrections") else None
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if args.list or args.outcomes or args.recipe not in ("decisions", "corrections"):
        from .context_cmd import recipes
        return recipes(p, args, budget)
    kind = DECISION if args.recipe == "decisions" else CORRECTION
    scope = args.scope if kind == DECISION else (args.kind or args.scope)
    text = cx.render(p, kind, scope, budget, args.proposed)
    if args.json:
        print(json.dumps({"recipe": args.recipe, "scope": scope, "budget": budget, "markdown": text}))
    else:
        sys.stdout.write(text)
    return 0
