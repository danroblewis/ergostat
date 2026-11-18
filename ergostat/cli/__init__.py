"""The command line: ``ergostat [TOPIC] [NAME] [FLAGS]``. Every topic lists everything of its kind,
and shows one in detail when given a name. Nothing here changes the system except ``run`` (which
starts the agents) and ``chat`` (the Supervisor). Each topic lives in its own module."""

from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..durations import DurationError
from .agents import cmd_agent
from .claims import cmd_claims
from .common import PART_TOPICS
from .messages import cmd_message, cmd_messages, cmd_session
from .numbers import cmd_accept, cmd_fit, cmd_improve, cmd_judge, cmd_measure, cmd_proposals
from .parts import cmd_part
from .record import cmd_compact, cmd_event, cmd_item, cmd_reset, cmd_residual
from .running import cmd_chat, cmd_projects, cmd_run, cmd_snapshot, cmd_web
from .spec_cmds import cmd_block, cmd_convert, cmd_discover, cmd_explain, cmd_findings
from .status import cmd_check, cmd_status
from .system import cmd_loop, cmd_system

HELP = """ergostat closes control loops around scheduled work, and finds the ones that are missing.

usage: ergostat [TOPIC] [NAME] [FLAGS]

  With no topic, ergostat shows what needs attention.

the model (ergostat.yaml: stocks, flows, auxiliaries, goals, blocks)
  check          Errors (file:line), then findings: missing feedback, open loops, ...
  explain        The model, or one part (goal.x, block.x, stock.x, flow.x, auxiliary.x), in sentences,
                 and its feedback loops (R reinforcing, B balancing)
  block          The blocks: what each computes or runs, what it reads and commands
                 (block NAME --now runs one at once; --done N is a person's report)
  convert        Write an old ergostat.toml as ergostat.yaml

what is wrong, or missing
  findings       Missing feedback, a limit ahead, saturation, people not answering, decay
  discover       Loops in the record (discover loops), a draft from Prometheus (discover prometheus)
  residual       What the model can't explain
  fit            How well the model's replay fits the record: R², MAPE, Theil's U_M, U_S, U_C
  proposals      Changes to review (values, equations, structure, loops): --show ID, accept ID, --dismiss ID
  claims         What blocks said they did, checked against the record: verified, contradicted, unchecked;
                 trust by block, rung and model (--check: check those left unchecked)
  judge          Judge the candidate changes blocks proposed for the model; measure: the model's own measures
  intent         Finished work held to what the owner meant (decisions, corrections, messages, done-when):
                 verdicts, the false-done rates; judge, overrule ID, reopen ITEM

the owner's messages
  message        Send the work in flight a message: ergostat message "that review can wait" [--about ITEM|PART];
                 routed to the items and runs it concerns, delivered to a running session as its next turn
  messages       What became of each message: routed, delivered, unrouted, answered (ID --about X: route one)

see it
  system         Draw a system (--blocks: each loop as a block diagram; --wiring: who talks to whom)
  loop           The feedback loops: what each holds, how far off, each part along it
  item           The items (ticket/12): each one's kind, state and fields, folded from its events
  decisions      The owner's decisions: extract them from transcripts, confirm, dismiss, supersede
  corrections    The owner's corrections: confirm, dismiss, retire; scan the record for them
  context        A session's starting context: context decisions --scope X, context corrections --kind Y
  event          The raw record (--follow to watch; --add TYPE records one from outside)
  snapshot       The page, as of now, in one HTML file to send

run it
  run            Run it here, in the background, with the web page (--stop)
  web            Serve the web page only
  mcp            ergostat for an AI agent, over MCP
  projects       Every project on this machine, which run, and their pages
  reset          Forget this project's record and start from nothing (--yes)
  verify         Score the changes written to the model again on the record since (--propose)
  bench          How we know it works: bench improve, judge, meta; bench parity (fresh sessions vs a long one)
  help blocks    How to write a sensor's and a block's program (also: help ai-agents, help spec, help model-tools,
                 help claims, help messages)

flags
  -C DIR             Run as if in DIR
  -s, --system NAME  Only the parts in this system
  --since TIME       The window to look at (10m, 2h, 1d; default 1h)
  --at TIME          As it was then: 30m (ago), 07:30, or epoch seconds
  --json             Output for scripts and agents
  --exit-code        The status exits 1 when something needs attention (for cron)
  --watch            Redraw the status every two seconds, like top
  -h, --help         Help (also: ergostat TOPIC --help)
  --version          Print the version

examples
  ergostat                        What needs attention
  ergostat check                  Is the model whole?
  ergostat explain goal.disk      One goal: what measures it, what serves it, what it is doing
  ergostat findings               What is worth a look
  ergostat system --all           Draw the whole system
  ergostat event --follow         Watch events arrive
"""


def build() -> argparse.ArgumentParser:
    def flags(suppress: bool) -> argparse.ArgumentParser:
        """The flags every topic takes; a topic's copy never overwrites what came before the topic."""
        f = argparse.ArgumentParser(add_help=False)
        d = {"default": argparse.SUPPRESS} if suppress else {}
        f.add_argument("-C", metavar="DIR", help="run as if in DIR", **d)
        f.add_argument("-s", "--system", metavar="NAME", help="only the parts in this system", **d)
        f.add_argument("--since", metavar="TIME", help="the window to look at (10m, 2h, 1d; default 1h)", **d)
        f.add_argument("--at", metavar="TIME", **d, help="as it was then: 30m (ago), 07:30, or epoch seconds")
        f.add_argument("--json", action="store_true", help="output for scripts and agents", **d)
        return f
    common = flags(True)
    ap = argparse.ArgumentParser(prog="ergostat", add_help=False, parents=[flags(False)], allow_abbrev=False)
    ap.add_argument("-h", "--help", action="store_true")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--exit-code", action="store_true", help="the status exits 1 when anything needs attention (for cron)")
    ap.add_argument("--watch", action="store_true", help="redraw the status every two seconds")
    sub = ap.add_subparsers(dest="topic")

    def topic(name, fn, help, named=True, desc=None):
        sp = sub.add_parser(name, parents=[common], help=help, description=desc or help)
        if named:
            sp.add_argument("name", nargs="?", metavar="NAME", help=f"show one {name} in detail (leave out: list them all)")
        sp.set_defaults(fn=fn)
        return sp
    s = topic("system", cmd_system, "Draw a system, or list them",
              desc="Draw a system, or list them. A system is a named selection of the model; systems may overlap.")
    s.add_argument("--all", action="store_true", help="draw everything")
    s.add_argument("--around", metavar="PART", help="one part and what is connected to it (loop/NAME, valve/NAME, ...)")
    s.add_argument("--depth", type=int, default=1, help="how far --around reaches (default 1)")
    s.add_argument("--list", action="store_true", help="the parts as a table")
    s.add_argument("--wiring", action="store_true", help="the agents and how they reach each other")
    s.add_argument("--blocks", action="store_true", help="each loop as a feedback block diagram")
    s.add_argument("--open", action="store_true", help="open it in the web page")
    topic("loop", cmd_loop, "The feedback loops, or one, part by part")
    ch = topic("check", cmd_check, "Is the model whole?", named=False)
    ch.add_argument("--example", nargs="?", const="disk", choices=["disk", "cron"],
                    help="print an example ergostat.toml: disk (one program, the default) or cron (one-liners, nothing to write)")
    cv = topic("convert", cmd_convert, "Write ergostat.toml as ergostat.yaml (the new format)", named=False)
    cv.add_argument("--stdout", action="store_true", help="print it instead of writing the file")
    cv.add_argument("--force", action="store_true", help="replace an ergostat.yaml that is already there")
    dv = topic("discover", cmd_discover, "Find the model in what exists: prometheus (a draft from its series) or loops "
                                         "(from the record)")
    dv.add_argument("--url", help="discover prometheus: the Prometheus to read")
    dv.add_argument("--match", metavar="REGEX", help="discover prometheus: only metric names matching this")
    topic("explain", cmd_explain, "The model, or one part (goal.x, stock.x, auxiliary.x, ...), in sentences, and its feedback loops")
    cl = topic("claims", cmd_claims, "What blocks said they did (claim lines), checked against the record; trust by "
                                    "block, rung and model")
    cl.add_argument("--check", action="store_true", help="check the claims made and left unchecked (ergostat stopped "
                                                         "between a run and its checks)")
    ms = topic("message", cmd_message, "Send the work in flight a message, routed to what it concerns", named=False)
    ms.add_argument("text", nargs="*", metavar="TEXT", help="what you say, verbatim")
    ms.add_argument("--about", action="append", metavar="ITEM|PART", help="what it is about (ticket/12, block.developer, "
                                                                            "stock.inbox); again for more")
    ms.add_argument("--as", dest="by", metavar="WHO", help="who sends it (default: owner)")
    ms.add_argument("--reopen", action="store_true", help="reopen the finished items it is about, whatever the policy")
    mss = topic("messages", cmd_messages, "The owner's messages and what became of each, or one; --about X routes one")
    mss.add_argument("--about", action="append", metavar="ITEM|PART", help="with NAME: route it to this, by hand")
    mss.add_argument("--reopen", action="store_true", help="with NAME: reopen the finished items it is about")
    mss.add_argument("--as", dest="by", metavar="WHO", help="who routes it (default: owner)")
    mss.add_argument("-n", type=int, default=30, help="how many to list (default 30)")
    se = sub.add_parser("session", parents=[common], help="Run a Claude Code session as a block's run, taking the "
                        "owner's messages while it works (ergostat session ROLE --model M -- CLAUDE-ARGS)", add_help=False)
    se.add_argument("rest", nargs=argparse.REMAINDER)
    se.set_defaults(fn=cmd_session)
    topic("findings", cmd_findings, "What is worth a look: missing feedback, limits ahead, saturation, decay", named=False)
    bk = topic("block", cmd_block, "The blocks (YAML model), or one; a person reports on theirs")
    bk.add_argument("--done", type=float, metavar="N", help="a person's report: what they moved")
    bk.add_argument("--approve", action="store_true", help="approve an advised command (mode: advise)")
    bk.add_argument("--stop", action="store_true", help="stop its run under way (one a model change left to finish, "
                    "say); it starts again only as the model says")
    bk.add_argument("--note", help="with --done, --approve or --stop: what was done, or why")
    bk.add_argument("--now", action="store_true", help="run this block once, at once (recorded like any run)")
    bk.add_argument("--command", type=float, metavar="N", help="with --now: the command it is given, as if commanded")
    ag = topic("agent", cmd_agent, "Who fills which roles, at what rung")
    ag.add_argument("--now", action="store_true", help="run this agent once, at once (recorded like any run)")
    e = topic("event", cmd_event, "The raw record, or one event with its causes (by id)")
    e.add_argument("-n", type=int, default=30, help="how many (default 30)")
    e.add_argument("--type", help="only this type (a glob ending in * matches a prefix: valve.*)")
    e.add_argument("--item", help="only events about this item")
    e.add_argument("--source", help="only events from this agent (or ergostat)")
    e.add_argument("--follow", "-f", action="store_true", help="keep printing as events arrive")
    e.add_argument("--runs", action="store_true", help="also each run's start and end (agent.started, agent.ran), left out by default")
    e.add_argument("--add", metavar="TYPE", help="record an event of this type (ticket.opened): what happened outside")
    e.add_argument("--data", metavar="JSON", help="with --add: its data, a JSON object (folded by the kind's fold: rules)")
    e.add_argument("--patch", metavar="JSON", help="with --add, in place of --data: a JSON Patch (RFC 6902) for its item, "
                                                  "applied whole or refused with why")
    e.add_argument("--set", dest="set_", metavar="JSON", help="with --add, in place of --data: its item's whole document")
    e.add_argument("--as", dest="by", metavar="SOURCE", help="with --add: who says so (default: the user)")
    i = topic("item", cmd_item, "The items: the record folded by id, with each kind's states")
    i.add_argument("-n", type=int, default=30, help="how many (default 30)")
    i.add_argument("--kind", help="only items of this kind")
    i.add_argument("--state", help="only items in this state")
    i.add_argument("--history", nargs="?", const="", metavar="FIELD",
                   help="with an item: each field's changes (or one field's), with the events that made them")
    topic("residual", cmd_residual, "What the model can't explain")
    topic("fit", cmd_fit, "How well the model's replay fits the record (each stock, the total, Theil's statistics)", named=False)
    pp = topic("proposals", cmd_proposals, "Estimate the parameters marked estimate: true, and list the changes the record "
                                           "supports", named=False)
    pp.add_argument("--dismiss", metavar="ID", help="let a proposal go (it is not made again for this model)")
    pp.add_argument("--reason", metavar="TEXT", help="with --dismiss: why, remembered with it")
    pp.add_argument("--show", metavar="ID", help="one proposal in full: what, where, why, how found, benefit, and the diff "
                                                 "accept writes")
    pp.add_argument("--stored", action="store_true", help="list the proposals already made, without estimating again")
    pp.add_argument("--calibrate", choices=["parts", "systems", "whole"], default="parts",
                    help="what is fitted at once: each part alone (default; equations proposed too), each system alone "
                         "driven by its measured inputs, or every stock integrated at once (what decisions set still taken as "
                         "measured, so loops through a decision stay open)")
    pp.add_argument("--propose", metavar="NAME=VALUE", action="append",
                    help="propose values you tried (a what-if; several, given together or as NAME=V,NAME=V, make one "
                         "proposal): the fit before and after, and the edit; nothing changes until it is accepted. A time "
                         "is written with its unit (20s, 5m, 2h)")
    topic("accept", cmd_accept, "Apply a proposal (ergostat proposals lists them) as the smallest edit to the YAML")
    topic("measure", cmd_measure, "The model's own measures (fit, unexplained, loops-unidentified, findings), as a model: "
                                  "sensor reads them")
    topic("judge", cmd_judge, "Judge the candidate changes blocks proposed, on the record after each (improve: says who "
                              "writes a kept one)", named=False)
    im = topic("improve", cmd_improve, "What blocks proposed and ergostat turned away; --try FILE checks a proposal", named=False)
    im.add_argument("--try", dest="try_", metavar="FILE", help="a propose line's JSON (or - for standard input): checked "
                                                               "and measured as a block's would be, and kept nowhere")
    im.add_argument("--edit-value", metavar="NAME=VALUE", help="the edit that sets a parameter's value, in the form a "
                                                              "propose line takes (a time with its unit: 20s); writes nothing")
    for t in PART_TOPICS:
        sp = topic(t, cmd_part, f"The {t}s, or one")
        sp.set_defaults(fn=cmd_part, topic=t)
        if t == "valve":
            sp.add_argument("--opened", type=float, metavar="N", help="a person records opening it: what it moved")
            sp.add_argument("--note", help="with --opened: what was done")
        if t == "sensor":
            sp.add_argument("--read", type=float, metavar="V", help="a person records a reading")
            sp.add_argument("--forget-above", type=float, metavar="V", help="set aside readings above V (wrong ones: they "
                                                                          "would skew every rate and residual)")
            sp.add_argument("--forget-below", type=float, metavar="V", help="set aside readings below V")
        if t == "controller":
            sp.add_argument("--decided", metavar="TEXT", help="a person records a decision")
    r = topic("run", cmd_run, "Start the agents (in the background) and the web page", named=False)
    r.add_argument("--foreground", action="store_true", help="stay attached instead of running in the background")
    r.add_argument("--stop", action="store_true", help="stop the ergostat running here, and its agents' runs")
    r.add_argument("--no-web", action="store_true", help="no web page")
    r.add_argument("--port", type=int, help="the web page's port (default 8781, or the next free one)")
    r.add_argument("--service", nargs="?", const="auto", choices=["auto", "launchd", "systemd"],
                   help="print a launchd agent (macOS) or systemd user unit (or the one named) that keeps it running across "
                        "reboots, on the page's current port; prints only, installs nothing")
    topic("projects", cmd_projects, "Every project on this machine, and which are running", named=False)
    cp = topic("compact", cmd_compact, "Roll items' old events up into snapshots (archived), forget what is past keep, "
                                       "roll measurements into their tiers: what the engine does every hour", named=False)
    cp.add_argument("--dry-run", action="store_true", help="say what would be rolled up, and change nothing")
    rs = topic("reset", cmd_reset, "Forget this project's record (events, items, measurements, logs) and start from nothing",
               named=False)
    rs.add_argument("--yes", action="store_true", help="do it (without it, says what it would forget)")
    mc = sub.add_parser("mcp", parents=[common], help="Serve ergostat to an AI agent over MCP (stdio)",
                        description="An MCP server on stdin/stdout: check, explain, status, findings, residuals, fit, events, "
                                    "spec, improve_model, try_change, measures, report_done, read_sensor, items, "
                                    "record_event. "
                                    "Add it to Claude Code: claude mcp add ergostat -- ergostat -C DIR mcp")
    mc.set_defaults(fn=cmd_mcp)
    hp = sub.add_parser("help", help="Guides: blocks (writing their programs), ai-agents, spec (the format), modelling "
                                     "(improving a model), improve-model (the skill for an AI agent reviewing one)")
    hp.add_argument("name", nargs="?")
    hp.set_defaults(fn=cmd_help)
    sn = topic("snapshot", cmd_snapshot, "Write the page, with what it shows now, to one HTML file", named=False,
               desc="Write the web page, with everything it shows now, to one HTML file that opens anywhere, offline, "
                    "with no ergostat running: the diagrams to attach to a document or a ticket.")
    sn.add_argument("-o", "--output", metavar="FILE", help="where (default: <name>-<date>-<time>.html here)")
    sn.add_argument("--with-logs", action="store_true", help="also the end of each agent's log (left out by default: a log may "
                                                            "hold what should not be sent on)")
    w = topic("web", cmd_web, "Serve the web page only", named=False)
    w.add_argument("--port", type=int, help="the web page's port (default 8781, or the next free one)")
    chat = sub.add_parser("chat", parents=[common], help="Talk to the Supervisor")
    chat.add_argument("message", nargs="*", help="what to say first (optional)")
    chat.add_argument("--print-prompt", action="store_true", help="print the Supervisor's brief instead of starting it")
    chat.set_defaults(fn=cmd_chat)
    from .bench import register as bench_topics
    bench_topics(sub, common)
    from .decisions import register as intent_topics
    intent_topics(sub, common)
    from .intent import register as judge_topics
    judge_topics(sub, common)
    return ap


def cmd_mcp(args) -> int:
    from pathlib import Path

    from ..mcp import serve
    return serve(Path(args.C).resolve() if args.C else Path.cwd())


def cmd_help(args) -> int:
    """``ergostat help [NAME]``: the guides, shipped with ergostat (``helpdocs``)."""
    from .. import helpdocs
    guides = list(helpdocs.guides())
    if not args.name:
        print(HELP)
        print("guides: " + ", ".join(f"ergostat help {g}" for g in guides))
        return 0
    text = helpdocs.read(args.name)
    if text is None:
        print(f"no guide {args.name!r}; guides: {', '.join(guides)}", file=sys.stderr)
        return 2
    print(text)
    return 0


def _more_files() -> None:
    """The soft limit on open files raised toward the hard one (macOS starts at 256): a runner with
    many agents runs a process per agent at once, each with its pipes and log."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = 4096 if hard == resource.RLIM_INFINITY else min(4096, hard)
        if soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except (ImportError, ValueError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    _more_files()
    ap = build()
    argv = list(sys.argv[1:] if argv is None else argv)
    flags_with_value = {"-C", "-s", "--system", "--since", "--at"}
    i = 0
    while i < len(argv) and argv[i].startswith("-"):    # past the global flags to the topic
        i += 2 if argv[i] in flags_with_value else 1
    if i < len(argv) and argv[i] == "status":           # `ergostat status` is the status, as bare `ergostat`
        del argv[i]
    args = ap.parse_args(argv)
    if args.version:
        print(f"ergostat {__version__}")
        return 0
    if getattr(args, "help", False) and not args.topic:
        print(HELP)
        return 0
    try:
        if not args.topic:
            return cmd_status(args)
        return args.fn(args)
    except DurationError as e:
        print(e, file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
