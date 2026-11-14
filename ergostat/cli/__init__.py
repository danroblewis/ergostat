"""The command line: ``ergostat [TOPIC] [NAME] [FLAGS]``. Every topic lists everything of its kind,
and shows one in detail when given a name. Nothing here changes the system except ``run`` (which
starts the agents) and ``chat`` (the Supervisor). Each topic lives in its own module."""

from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..durations import DurationError
from .agents import cmd_agent
from .common import PART_TOPICS
from .parts import cmd_part
from .record import cmd_event, cmd_item, cmd_residual
from .running import cmd_chat, cmd_projects, cmd_run, cmd_web
from .status import cmd_check, cmd_status
from .system import cmd_loop, cmd_system

HELP = """ergostat keeps your work going. Design, watch and run the control system around it.

usage: ergostat [TOPIC] [NAME] [FLAGS]

  With no topic, ergostat shows what needs attention.

the system
  system         Draw a system (--blocks: each loop as a block diagram; --wiring: how agents talk)
  loop           The feedback loops: what each holds, how far off, each part along it
  check          Is the model whole? Unknown names, loops that cannot close

who does the work
  agent          People, AI agents, decisions, programs and rules, and the roles they fill
                 (agent NAME --now runs one at once)

what happened
  event          The raw record (--follow to watch)
  item           Events folded by id
  residual       What the model can't explain

run it
  run            Start the agents here, in the background, with the web page
  web            Serve the web page only
  chat           Talk to the Supervisor, who changes the system for you
  projects       Every project on this machine, which run, and their pages

the parts, one at a time
  stock  flow  valve  sensor  controller  disturbance

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
  ergostat system --all           Draw the whole system
  ergostat loop disk-under-80     One loop, part by part
  ergostat agent                  Who fills which roles, at what rung
  ergostat event --follow         Watch events arrive
  ergostat check --example        An example ergostat.toml to start from
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
    ap = argparse.ArgumentParser(prog="ergostat", add_help=False, parents=[flags(False)])
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
    ch.add_argument("--example", action="store_true", help="print an example ergostat.toml")
    ag = topic("agent", cmd_agent, "Who fills which roles, at what rung")
    ag.add_argument("--now", action="store_true", help="run this agent once, at once (recorded like any run)")
    e = topic("event", cmd_event, "The raw record, or one event with its causes (by id)")
    e.add_argument("-n", type=int, default=30, help="how many (default 30)")
    e.add_argument("--type", help="only this type (a glob ending in * matches a prefix: valve.*)")
    e.add_argument("--item", help="only events about this item")
    e.add_argument("--source", help="only events from this agent (or ergostat)")
    e.add_argument("--follow", "-f", action="store_true", help="keep printing as events arrive")
    i = topic("item", cmd_item, "Events folded by id")
    i.add_argument("-n", type=int, default=30, help="how many (default 30)")
    i.add_argument("--all", action="store_true", help="also the parts and agents ergostat's own events are about")
    topic("residual", cmd_residual, "What the model can't explain")
    for t in PART_TOPICS:
        topic(t, cmd_part, f"The {t}s, or one").set_defaults(fn=cmd_part, topic=t)
    r = topic("run", cmd_run, "Start the agents (in the background) and the web page", named=False)
    r.add_argument("--foreground", action="store_true", help="stay attached instead of running in the background")
    r.add_argument("--stop", action="store_true", help="stop the ergostat running here, and its agents' runs")
    r.add_argument("--no-web", action="store_true", help="no web page")
    r.add_argument("--port", type=int, help="the web page's port (default 8781, or the next free one)")
    topic("projects", cmd_projects, "Every project on this machine, and which are running", named=False)
    w = topic("web", cmd_web, "Serve the web page only", named=False)
    w.add_argument("--port", type=int, help="the web page's port (default 8781, or the next free one)")
    chat = sub.add_parser("chat", parents=[common], help="Talk to the Supervisor")
    chat.add_argument("message", nargs="*", help="what to say first (optional)")
    chat.add_argument("--print-prompt", action="store_true", help="print the Supervisor's brief instead of starting it")
    chat.set_defaults(fn=cmd_chat)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build()
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
