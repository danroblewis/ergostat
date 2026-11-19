"""Calls from a step to the running engine, over a Unix socket in its state directory (docs/proposals/latency.md;
SPEC §9.5): ``ergostat act``, ``event --add``, ``lease --renew`` / ``--nack`` and ``item ID --json`` answered by the
engine itself, in milliseconds, instead of each loading the whole model. ``ERGOSTAT_SOCKET`` names it in every run's
environment; a command run from a shell finds it in the project's state directory. When no engine listens, each
command does what it always did.

- ``server``: the engine's listener: a fixed pool of threads, and calls that wait (an action's answer) parked, not
  holding a thread;
- ``client``: the other end, the standard library only, for the CLI and for a step's own code;
- ``ops``: what each call does, with the engine's record and model."""

SOCKET = "engine.sock"           # in the state directory (or, when that path is too long for a socket, named there)
POINTER = "engine.sock.path"     # the socket's path, when it is not in the state directory
