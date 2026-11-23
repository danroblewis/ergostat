"""A journal sensor (SPEC §6): a folder of JSONL journals written by something ergostat did not start. Each engine
follows the journal sensors it owns, on one thread of its own, every ``EVERY`` seconds. Each complete line goes through
a ``run:`` sensor's rules, recorded under an id made from the sensor, the file's name, the line's offset and its bytes,
so a line read again (a restart, a lost read state, a reload) records nothing new. The offsets read are kept in a state
file; when it is missing or unreadable every journal is read from its start, never taken as read."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import threading
import time
from pathlib import Path

from . import mirror

EVERY = 2.0             # seconds between looks at the folders
LINES = 500             # lines recorded per sensor per pass: the rest wait for the next pass
LINE_BYTES = 65536      # a longer line (its \n counted) is refused and skipped
FILES = 64              # journals read per folder: past it, said once and not read
TAIL = 4096             # the bytes before a file's offset, kept as a hash: changed, the file went back
SOURCE = "ergostat"


def _id(*parts) -> str:
    h = hashlib.sha256()
    for x in parts:
        h.update(x if isinstance(x, bytes) else str(x).encode())
        h.update(b"\0")
    return h.hexdigest()[:32]


def _value(v) -> float | None:
    try:
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None
    except OverflowError:
        return None


class Journals:
    """One engine's journal sensors (``sync``: by their names) and what was read of them (``state``)."""

    def __init__(self, p, root, state: Path, say=print, read=None):
        self.p, self.root, self.path, self.say, self.read = p, Path(root).resolve(), Path(state), say, read
        self.sensors: dict = {}
        self.stop, self.thread, self.said = threading.Event(), None, set()
        self.pending: dict = {}              # sensor: its latest value line's value, not yet a reading
        self.last: dict = {}                 # sensor: when its last reading was taken
        self.state = self._load()

    def sync(self, sensors: dict) -> None:
        self.sensors = dict(sensors)         # (replaced whole: a pass under way sees a removed one gone)
        if sensors and self.thread is None and not self.stop.is_set():
            self.thread = threading.Thread(target=self._run, name="ergostat-journals", daemon=True)
            self.thread.start()

    def close(self, wait: float = 5.0) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(wait)

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                self.look()
            except Exception as e:           # the next pass reads again from what was saved
                self.say(f"journals: {type(e).__name__}: {e}")
            self.stop.wait(EVERY)

    def _load(self) -> dict:
        try:
            got = json.loads(self.path.read_text())
        except (OSError, ValueError, RecursionError):
            return {}                        # read from the start: duplicates dropped by id, nothing skipped
        if not isinstance(got, dict):
            return {}
        return {k: v for k, v in got.items() if isinstance(v, dict) and type(v.get("offset")) is int and v["offset"] >= 0}

    def look(self) -> None:
        """One pass over every folder: new complete lines recorded, at most ``LINES`` per sensor."""
        for name, s in list(self.sensors.items()):
            if self.stop.is_set():
                break
            folder = Path(os.path.realpath(self.root / s.journal))
            if not folder.is_relative_to(self.root):
                self.once(name, "", "outside", f"{s.journal}: leaves the model's folder, not read")
                continue
            try:
                names = sorted(n for n in os.listdir(folder) if n.endswith(".jsonl"))
            except OSError as e:
                self.say(f"sensor {name}: {s.journal}: {e}")
                continue
            if len(names) > FILES:
                self.once(name, "", "files", f"{len(names) - FILES} journals past the first {FILES} are not read "
                                             f"(from {names[FILES]})")
            left = LINES
            for n in names[:FILES]:
                if left <= 0 or name not in self.sensors or self.stop.is_set():
                    break
                left -= self.file(name, folder, n, left)
            self.reading(name)
        self._save()

    def file(self, name: str, folder: Path, n: str, left: int) -> int:
        real = os.path.realpath(folder / n)
        if os.path.dirname(real) != str(folder):
            self.once(name, n, "link", f"{n}: a link that leaves the folder, not read")
            return 0
        try:                                 # never blocks: a FIFO named *.jsonl is opened, seen and not read
            f = os.fdopen(os.open(real, os.O_RDONLY | os.O_NONBLOCK), "rb")
        except OSError:
            return 0                         # (not marked read: read when it can be)
        with f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode):
                self.once(name, n, "not-file", f"{n}: not a regular file, not read")
                return 0
            key, ino = f"{name}/{n}", [st.st_dev, st.st_ino]
            was = self.state.get(key) or {}
            at = was.get("offset", 0)
            if at and (was.get("ino") != ino or st.st_size < at or self._tail(f, at) != was.get("tail")):
                self.once(name, n, "went-back", f"{n} went back: read again from its start", was.get("ino"), at,
                          was.get("tail"))
                at = 0
            f.seek(at)
            done = 0
            while done < left:
                raw = f.readline(LINE_BYTES + 1)
                size, h = len(raw), None
                if size > LINE_BYTES:        # over the limit: the rest of it read through, never kept
                    h = hashlib.sha256(raw)
                    while raw and not raw.endswith(b"\n"):
                        raw = f.readline(LINE_BYTES)
                        h.update(raw)
                        size += len(raw)
                if not raw.endswith(b"\n"):
                    break                    # a partial last line: it waits until it is complete
                if h is None:
                    self.line(name, n, at, raw)
                else:
                    self.refuse(name, f"{n}: a line of {size} bytes, over the {LINE_BYTES} a journal line may have",
                                n, at, _id(name, n, at, h.hexdigest(), "refused"))
                at += size
                done += 1
            self.state[key] = {"offset": at, "ino": ino, "tail": self._tail(f, at)}
            return done

    @staticmethod
    def _tail(f, at: int) -> str:
        f.seek(max(0, at - TAIL))
        return hashlib.sha256(f.read(min(at, TAIL))).hexdigest()

    def line(self, name: str, n: str, at: int, raw: bytes) -> None:
        from .spec.engine import observations
        from .store import ChangesetError
        lid = _id(name, n, at, raw)
        try:
            obj = json.loads(raw)
        except (ValueError, RecursionError):
            return                           # (not an observation: words a command prints are passed over too)
        seen, refused = [], []
        if isinstance(obj, dict) and "value" in obj and "event" not in obj and "message" not in obj:
            v = _value(obj["value"])
            if v is None:
                refused.append(f"{n}: a value line's value is a finite number ({{\"value\": 3}})")
            elif self.p.events.add("sensor.value", item=name, source=SOURCE, id=lid,
                                   data={"value": v, "file": n, "offset": at}).get("seq") is not None:
                self.pending[name] = v       # a reading only the first time its line is read (by the line's id)
        else:
            seen, refused = observations(raw.decode("utf-8", "replace"))
        for o in seen:
            if "message" in o:
                refused.append("message: a journal cannot relay a message")
                continue
            why = "id" in o and mirror.valid(o["id"], name)     # a line's own cite: as a run: sensor's (mirror.py)
            if why:
                refused.append(why)
                continue
            try:
                self.p.events.add(o["type"], item=o["item"], source=name, data=o["data"], patch=o.get("patch"),
                                  set=o.get("set"), id=o.get("id") or lid)
            except ChangesetError as err:
                refused.append(f"{o['type']}: {err}")
        for i, why in enumerate(refused):
            self.refuse(name, why, n, at, _id(lid, "refused", i))

    def reading(self, name: str) -> None:
        """The latest value line read: the sensor's reading, at most one a second."""
        s, now = self.sensors.get(name), time.time()
        if name not in self.pending or s is None or now - self.last.get(name, 0.0) < 1.0:
            return
        v = self.pending.pop(name)
        self.p.measurements.add(s.series, v, at=now)
        self.last[name] = now
        if self.read is not None:
            self.read(s)

    def once(self, name: str, n: str, kind: str, why: str, *extra) -> None:
        rid = _id(name, n, kind, *extra)
        if rid not in self.said:
            self.said.add(rid)
            self.refuse(name, why, n, None, rid)

    def refuse(self, name: str, why: str, n: str, at: int | None, rid: str) -> None:
        got = self.p.events.add("sensor.refused", item=name, source=SOURCE, id=rid,
                                data={"why": why, "file": n, **({"offset": at} if at is not None else {})})
        if got.get("seq") is not None:
            self.say(f"sensor {name}: {why}")

    def _save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(self.state))
            os.replace(tmp, self.path)
        except OSError as e:                 # unsaved: the next engine reads again, duplicates dropped by id
            self.say(f"journals: {self.path.name}: {e}")
