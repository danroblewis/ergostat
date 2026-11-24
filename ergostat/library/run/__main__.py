"""``python -m ergostat.library.run PROGRAM ...``: the programs the built-in templates run (see ``__init__``)."""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    from . import collect, each, modelling, ping, report, standin, todo, upkeep
    progs = {"collect": collect.main, "each": each.main, "ping": ping.main, "due": report.due, "report": report.report,
             "summary": report.summary, "modelling": modelling.main, "upkeep": upkeep.main, "todo": todo.main,
             "standin": None}
    if not argv or argv[0] not in progs:
        print(f"usage: python -m ergostat.library.run {{{','.join(progs)}}} ...", file=sys.stderr)
        return 2
    if argv[0] == "standin":
        subs = {"act": standin.act, "level": standin.level, "lower": standin.lower, "improver": standin.improver}
        named = {"load": standin.scaled, "replicas": standin.scaled, "signal": standin.alert, "firing": standin.alert}
        if len(argv) < 2 or argv[1] not in {**subs, **named}:
            print(f"usage: ... standin {{{','.join([*subs, *named])}}} ...", file=sys.stderr)
            return 2
        return named[argv[1]](argv[1:]) if argv[1] in named else subs[argv[1]](argv[2:])
    return progs[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
