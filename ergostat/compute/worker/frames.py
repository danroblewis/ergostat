"""The worker protocol's frame (SPEC §12s): one JSON object a line each way, with ``v`` (the protocol, 1), ``seq``
(per direction, from 1, rising by one a line) and ``type``, at most 1 MiB a line (the newline not counted)."""

import json
import threading

V = 1
MAX = 1 << 20


class Bad(Exception):
    """A line that is not a frame of this protocol: the stream past it can't be trusted, so the worker ends."""

    def __init__(self, why: str, id=None):
        super().__init__(why)
        self.why, self.id = why, id


def _int(x) -> bool:
    return type(x) is int                       # (True is not a seq, nor a version)


def decode(line: bytes, want: int) -> dict:
    """The frame on ``line``, whose ``seq`` must be ``want``; else ``Bad``."""
    line = line.rstrip(b"\n")
    if len(line) > MAX:
        raise Bad("line over 1 MiB")
    try:
        obj = json.loads(line)
    except (ValueError, UnicodeDecodeError):
        raise Bad("not JSON") from None
    if not isinstance(obj, dict):
        raise Bad("not a JSON object")
    rid = obj.get("id")
    if not _int(obj.get("v")) or obj["v"] != V:
        raise Bad(f"protocol v{obj.get('v')!r} is not v{V}", rid)
    if not _int(obj.get("seq")) or obj["seq"] != want:
        raise Bad(f"seq {obj.get('seq')!r} where {want} was next", rid)
    if not isinstance(obj.get("type"), str) or not obj["type"]:
        raise Bad("no type", rid)
    return obj


class Writer:
    """Frames out, one a line, numbered under one lock (the loop and the beat both send)."""

    def __init__(self, out):
        self.out, self.seq, self.lock = out, 0, threading.Lock()

    def send(self, type: str, **fields) -> None:
        with self.lock:
            frame = {"v": V, "seq": self.seq + 1, "type": type, **fields}
            line = json.dumps(frame, separators=(",", ":"), allow_nan=False).encode()
            if len(line) > MAX:
                raise ValueError(f"{type}: a frame over 1 MiB")
            self.out.write(line + b"\n")
            self.out.flush()
            self.seq += 1
