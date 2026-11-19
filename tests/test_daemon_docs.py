"""The daemon docs run (docs/DAEMONS.md, docs/skills/ergostat-author/daemons.md): every code block parses, and every
example marked in them (``<!-- example: NAME, file: PATH -->``, ``run``, ``output``) is written to a folder, checked,
driven by hand over its standard input as the docs tell people to, and run under the engine until it has recorded
readings and finished items. examples/daemon-demo is the docs' own files, byte for byte."""

import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from ergostat import model as mdl
from ergostat.spec.engine import Engine
from ergostat.store import Project

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "docs" / "DAEMONS.md", ROOT / "docs" / "skills" / "ergostat-author" / "daemons.md"]
DEMO = ROOT / "examples" / "daemon-demo"
MARK = re.compile(r"<!-- example: ([\w-]+), (?:file: (\S+)|(run|output)) -->")
FENCE = re.compile(r"^(\s*)```(\w*)\s*$")


def blocks(doc: Path) -> list[dict]:
    """Each fenced block: its language, text (dedented), line, and the example mark just before it."""
    out, mark, lines = [], None, doc.read_text().splitlines()
    i = 0
    while i < len(lines):
        if m := MARK.search(lines[i]):
            mark = {"example": m[1], "file": m[2], "role": m[3] or "file"}
        elif f := FENCE.match(lines[i]):
            ind, start, body = len(f[1]), i + 1, []
            i += 1
            while not FENCE.match(lines[i]) or len(FENCE.match(lines[i])[1]) != ind:
                body.append(lines[i][ind:])
                i += 1
            out.append({"lang": f[2], "text": "\n".join(body) + "\n", "at": f"{doc.name}:{start}", **(mark or {})})
            mark = None
        elif lines[i].strip():
            mark = None if not lines[i].lstrip().startswith("<!--") else mark
        i += 1
    return out


ALL = [b for d in DOCS for b in blocks(d)]
EXAMPLES = sorted({b["example"] for b in ALL if b.get("example")})


def build(name: str, at: Path) -> list[dict]:
    """The example's files written under ``at``; its run and output blocks, in order."""
    mine = [b for b in ALL if b.get("example") == name]
    for b in mine:
        if b["role"] == "file":
            p = at / b["file"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(b["text"])
            p.chmod(0o755)
    if name == "daemon-demo":                    # (its count-files.sh is shape 1's)
        src = next(b for b in ALL if b.get("file") == "bin/count-files.sh")
        (at / "bin" / "count-files.sh").write_text(src["text"])
    return [b for b in mine if b["role"] != "file"]


def test_every_code_block_in_the_daemon_docs_parses(tmp_path):
    assert len(EXAMPLES) >= 9 and len(ALL) >= 30, (EXAMPLES, len(ALL))
    for b in ALL:
        if b["lang"] == "yaml":
            assert isinstance(yaml.safe_load(b["text"]), dict), b["at"]
        elif b["lang"] == "python":
            compile(b["text"], b["at"], "exec")
        elif b["lang"] == "sh":
            r = subprocess.run(["sh", "-n"], input=b["text"], capture_output=True, text=True)
            assert r.returncode == 0, (b["at"], r.stderr)
        elif b["lang"] == "text" and b.get("role") == "output":
            assert all(json.loads(x) for x in b["text"].splitlines() if x.startswith("{")), b["at"]
        else:
            assert b["lang"] == "text", f"{b['at']}: a block in {b['lang']!r}, which nothing checks"


@pytest.mark.parametrize("name", EXAMPLES)
def test_each_example_model_passes_check(tmp_path, name):
    build(name, tmp_path)
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(tmp_path), "check"], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert mdl.load(tmp_path).spec.daemons, "an example with no daemon"


class Daemon:
    """A daemon started as ergostat starts it (in the model's folder, by its run:), driven by hand."""

    def __init__(self, d, cwd: Path):
        self.p = subprocess.Popen(d.run, shell=True, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        self.lines: list[dict] = []
        self.buf = b""

    def send(self, **line):
        self.p.stdin.write((json.dumps(line) + "\n").encode())
        self.p.stdin.flush()

    def until(self, cond, seconds: float) -> dict | None:
        end = time.time() + seconds
        while time.time() < end:
            got = next((x for x in self.lines if cond(x)), None)
            if got is not None:
                return got
            if select.select([self.p.stdout], [], [], 0.1)[0]:
                chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    break
                self.buf += chunk
                *whole, self.buf = self.buf.split(b"\n")
                for x in whole:
                    obj = json.loads(x)          # every line JSON
                    assert isinstance(obj, dict) and (obj == {"heartbeat": True} or {"run", "request", "sensor"} & set(obj)), obj
                    if "done" in obj:
                        assert set(obj) == {"done", "run"} and type(obj["done"]) is int, obj
                    self.lines.append(obj)
        return next((x for x in self.lines if cond(x)), None)

    def stop(self) -> int:
        self.send(op="stop")
        self.p.stdin.close()
        try:
            return self.p.wait(15)
        finally:
            try:
                os.killpg(self.p.pid, 9)         # (and whatever it left: a push loop's sleep)
            except OSError:
                pass


def item_line(run: str, seconds: float) -> dict:
    return {"op": "item", "run": run, "item": f"job/{run}", "lease": {"fence": 1},
            "input": {"item": {"id": f"job/{run}", "fields": {"seconds": seconds}}},
            "env": {"ERGOSTAT_ITEM": f"job/{run}", "ERGOSTAT_RUN": run, "ERGOSTAT_LEASE": "1"}}


@pytest.mark.slow
@pytest.mark.parametrize("name", EXAMPLES)
def test_each_daemon_answers_lines_piped_by_hand(tmp_path, name):
    for b in build(name, tmp_path):              # the docs' own commands, and what they say comes out
        if b["role"] == "run":
            r = subprocess.run(["sh", "-c", b["text"]], cwd=tmp_path, capture_output=True, text=True, timeout=60)
            assert r.returncode == 0, (b["at"], r.stdout, r.stderr)
            said = r.stdout
        else:
            missing = [x.strip() for x in b["text"].splitlines() if x.strip() and x.strip() not in
                       [y.strip() for y in said.splitlines()]]
            assert not missing, (b["at"], missing, said)
    spec = mdl.load(tmp_path).spec
    for dn, d in spec.daemons.items():
        sensors = [s for s in spec.sensors() if s.daemon == dn]
        takers = [b for b in spec.blocks.values() if b.params.get("daemon") == dn]
        h = Daemon(d, tmp_path)
        for i, s in enumerate(sensors):
            sid = f"{s.of.name}.{s.name}"
            if s.push:
                assert h.until(lambda x, sid=sid: x.get("sensor") == sid and isinstance(x["reading"], int | float), 10), sid
            else:
                h.send(op="read", sensor=sid, request=f"q{i}")
                got = h.until(lambda x, i=i: x.get("request") == f"q{i}", 10)
                assert got and isinstance(got.get("reading"), int | float), (sid, got)
        if takers and d.concurrency > 1:
            h.send(**item_line("slow", 30))      # a slow item, then a quick one and a cancel: neither waits on it
            h.send(**item_line("quick", 0.2))
            assert h.until(lambda x: x == {"done": 0, "run": "quick"}, 10), h.lines
        elif takers:                             # one at a time: the quick one, then the slow one cancelled
            h.send(**item_line("quick", 0.2))
            assert h.until(lambda x: x == {"done": 0, "run": "quick"}, 10), h.lines
            h.send(**item_line("slow", 30))
        if takers:
            h.send(op="cancel", run="slow")
            assert h.until(lambda x: x.get("run") == "slow" and "done" in x, 10), "a cancel answered at once"
        assert h.stop() == 0, f"{dn}: stop ends it, exit 0"
        if d.run.startswith("python3"):          # a broken line ends it, not 0
            r = subprocess.run(d.run, shell=True, cwd=tmp_path, input="not json\n", capture_output=True, text=True,
                               timeout=20)
            assert r.returncode != 0, f"{dn} fails hard on a broken line"


@pytest.mark.slow
@pytest.mark.parametrize("name", EXAMPLES)
def test_each_example_records_readings_and_finishes_items_under_the_engine(tmp_path, name):
    for b in build(name, tmp_path):
        if b["role"] == "run" and "printf" not in b["text"] and "compare.py" not in b["text"]:   # setup only
            subprocess.run(["sh", "-c", b["text"]], cwd=tmp_path, check=True, capture_output=True, timeout=60)
    p = Project(mdl.load(tmp_path))
    spec = p.model.spec
    series = [s.series for s in spec.sensors() if s.daemon]
    opened = []
    if not any(b.type == "program" and b.params.get("run") for b in spec.blocks.values()):   # nothing opens items
        for b in spec.blocks.values():
            if b.takes:
                ev = next(t for t, st in spec.items[b.takes.kind].on.items() if st == b.takes.at[0])
                for n in range(2):
                    opened.append((f"{b.takes.kind}/{n}", b.takes.to))
                    p.events.add(ev, item=opened[-1][0], source="t", data={"seconds": 1})
    takers = [b for b in spec.blocks.values() if b.takes]
    e = Engine(p, say=lambda s: None)
    e.start_all()

    def state(i):
        from ergostat.spec import items as its
        return its.one(p.events, spec, i).state

    try:
        end = time.time() + 30
        while time.time() < end:
            read = all(p.measurements.latest(s, time.time()) for s in series)
            worked = all(state(i) in to for i, to in opened) and (not takers or any(
                r["data"].get("daemon") for r in p.events.query(n=None, type="agent.ran")))
            if read and worked:
                break
            time.sleep(0.2)
    finally:
        e.close()
    assert all(p.measurements.latest(s, time.time()) for s in series), [s for s in series if not p.measurements.latest(s, time.time())]
    assert all(state(i) in to for i, to in opened), [(i, state(i)) for i, _ in opened]
    if takers:
        ran = [r for r in p.events.query(n=None, type="agent.ran") if r["data"].get("daemon")]
        assert ran and all(r["data"]["exit"] == 0 for r in ran), ran[:3]
    assert not p.events.query(n=None, type="ergostat.daemon.restarted"), "no daemon restarted"
    assert not p.events.query(n=None, type="sensor.failed"), [x["data"] for x in p.events.query(n=None, type="sensor.failed")][:3]


def test_the_demo_is_built_from_the_docs_own_files(tmp_path):
    build("daemon-demo", tmp_path)
    tracked = subprocess.run(["git", "-C", str(DEMO), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    built = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
    assert sorted(f for f in tracked if f not in ("README.md", ".gitignore")) == built
    for f in built:
        assert (DEMO / f).read_text() == (tmp_path / f).read_text(), f"examples/daemon-demo/{f} differs from the docs"
