"""A kept daemon's relay (SPEC §9.7, *A daemon that outlives its engine*): the process its keeper forks, standard
library only, run as ``python3 -I relay.py INBOX POS COMMAND``. It starts the daemon's ``COMMAND`` (``sh -c``) in its own
process group, its standard output and error its own (the journal and the log), and writes the daemon's standard
input from ``INBOX``, the file the engine appends its lines to, from where it delivered last (``POS``, saved after each
write). With no engine up the inbox does not grow, so the daemon is sent nothing and is never sent the end of its
input: it goes on with what it holds. A ``stop`` line is the last delivered: its input is closed after it. Its exit is
the daemon's (128 + N for a signal N)."""

import json
import os
import subprocess
import sys
import time

TICK = 0.05


def put(path: str, text: str) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def start(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            got = int(f.read())
        return got if got >= 0 else 0
    except (OSError, ValueError):
        return 0                                     # (none saved: from the start; each line carries its own id)


def stops(line: bytes) -> bool:
    try:
        return json.loads(line) == {"op": "stop"}
    except ValueError:
        return False


def main(argv: list[str]) -> int:
    inbox, pos_path, command = argv
    child = subprocess.Popen(["/bin/sh", "-c", command], stdin=subprocess.PIPE)
    pos, closed = start(pos_path), False
    while child.poll() is None:
        got = b""
        if not closed:
            try:
                with open(inbox, "rb") as f:
                    f.seek(pos)
                    got = f.read().rpartition(b"\n")[0]
            except OSError:
                got = b""
        if not got:
            time.sleep(TICK)
            continue
        for line in got.split(b"\n"):
            try:
                child.stdin.write(line + b"\n")
                child.stdin.flush()
            except (OSError, ValueError):
                closed = True                        # (it closed its input: its exit is waited for)
                break
            pos += len(line) + 1
            put(pos_path, str(pos))
            if stops(line):
                closed = True
                child.stdin.close()
                break
    code = child.wait()
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
