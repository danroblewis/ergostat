"""Ports for the tests' page servers. ``ERGOSTAT_TEST_PORTS`` ("8791-8799") names a range to take them
from; otherwise the system hands out free ones, so tests run side by side (several worktrees at once)
never run out of ports or take a fixed one another program keeps. Never 8790, the owner's page."""
import os
import socket

import pytest

OWNER = 8790


def _range() -> range | None:
    v = os.environ.get("ERGOSTAT_TEST_PORTS", "").strip()
    if not v:
        return None
    a, _, b = v.partition("-")
    return range(int(a), int(b or a) + 1)


def free_ports(n: int = 1) -> list[int]:
    """``n`` distinct ports free now, on 127.0.0.1."""
    out: list[int] = []
    rng = _range()
    if rng is not None:
        for p in rng:
            if p == OWNER:
                continue
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # (as the server binds: a port just left is free)
                try:
                    s.bind(("127.0.0.1", p))
                except OSError:
                    continue
            out.append(p)
            if len(out) == n:
                return out
        pytest.skip(f"no {n} free ports in {rng.start}-{rng.stop - 1}")
    held = []
    try:
        while len(out) < n:                     # held open until all are found, so no two are the same
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            held.append(s)
            p = s.getsockname()[1]
            if p != OWNER:
                out.append(p)
    finally:
        for s in held:
            s.close()
    return out


def free_port() -> int:
    return free_ports(1)[0]
