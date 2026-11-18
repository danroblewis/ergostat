"""How an item's folded document is kept in its index (``itemindex.py``): packed small, read fast.

``marshal`` (the standard library's own format for code objects: dicts, lists, strings and numbers,
with repeated strings written once and interned when read) compressed with zlib when that saves
much. Chosen by measurement against JSON and msgpack, each with and without zlib, on the demos'
items (``docs/proposals/harness-parity-plan.md``, the item index). The index is rebuilt from the
record whenever its layout changes or its Python does, so marshal's version-specific format is safe
here; nothing outside the index reads it, and JSON stays the format of the API and the pages."""

from __future__ import annotations

import json
import marshal
import zlib

RAW, PACKED = b"m", b"z"
SMALL = 160                     # bytes: anything shorter is kept as it is (zlib's header costs more than it saves)


def _plain(v):
    """What marshal takes: JSON's values (a value that is not one, as JSON would write it)."""
    try:
        marshal.dumps(v)
        return v
    except ValueError:
        return json.loads(json.dumps(v, default=str))


def pack(v) -> bytes:
    body = marshal.dumps(_plain(v), 4)
    if len(body) < SMALL:
        return RAW + body
    z = zlib.compress(body, 1)
    return PACKED + z if len(z) < len(body) * 0.9 else RAW + body


def unpack(b: bytes):
    tag, body = b[:1], b[1:]
    return marshal.loads(zlib.decompress(body) if tag == PACKED else body)
