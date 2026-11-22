"""``ergostat worker`` (SPEC §12s): ``--stdio [--root DIR]`` runs this machine as a compute node's worker, the same
main as ``python3 -I PATH/worker --stdio`` (ergostat/compute/worker/, loaded by path: its modules are the standard
library's and its own); ``--pack FILE`` writes that folder as a zipapp to copy to a node with no ergostat."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import zipapp
from pathlib import Path

WORKER = Path(__file__).resolve().parent.parent / "compute" / "worker"


def register(sub, common) -> None:
    wp = sub.add_parser("worker", help="Run as a compute node's worker (--stdio), or write it to copy to one (--pack FILE)",
                        description="A compute node's worker (SPEC §12s): --stdio speaks the protocol on standard input "
                                    "and output, keeping its node id and files in --root (default "
                                    "~/.local/state/ergostat-worker/); --pack FILE writes it as a zipapp, run on a node "
                                    "with python3 -I FILE --stdio")
    wp.add_argument("--stdio", action="store_true", help="speak the worker protocol on standard input and output")
    wp.add_argument("--root", metavar="DIR", help="with --stdio: the worker's own folder")
    wp.add_argument("--pack", metavar="FILE", help="write the worker as a zipapp to FILE")
    wp.add_argument("--beat", type=float, help=argparse.SUPPRESS)
    wp.set_defaults(fn=cmd_worker)


def cmd_worker(args) -> int:
    if bool(args.stdio) == bool(args.pack):
        print("ergostat worker: one of --stdio or --pack FILE", file=sys.stderr)
        return 2
    if args.pack:
        if args.root or args.beat is not None:
            print("ergostat worker: --root is for --stdio", file=sys.stderr)
            return 2
        zipapp.create_archive(WORKER, args.pack, interpreter="/usr/bin/env python3",
                              filter=lambda p: p.suffix == ".py" and "__pycache__" not in p.parts)
        print(f"wrote {args.pack}: on a node, python3 -I {args.pack} --stdio")
        return 0
    sys.dont_write_bytecode = True                      # (no cache of the worker's modules beside them)
    spec = importlib.util.spec_from_file_location("ergostat_worker_main", WORKER / "__main__.py")
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    argv = ["--stdio"] + (["--root", args.root] if args.root else []) + \
        (["--beat", str(args.beat)] if args.beat is not None else [])
    return main.main(argv)
