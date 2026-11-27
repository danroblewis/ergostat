"""Triage reads Ruby traces, and a Python traceback that begins before the 8,000-character tail is read from the run's
own file, at most its last 64,000 characters (SPEC §12r, *Triage*; dev/records/repair-traces-more.md)."""

import os
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat.repair import FAILURE, capture
from ergostat.spec import items as its
from ergostat.store import Project

MODEL = """\
name: traces-more
projections:
  issue: {id: issue/*, states: [open, closed], on: {issue.seen: open}}
stocks:
  open-issues: {unit: issues, cumulative: true, sensor: {projection: issue, state: open, every: 1h}}
blocks:
  collector:
    type: program
    run: python3 collect.py
    every: 1h
uses:
  repair:
    use: repair
    with: {count-every: 1h, approver: person}
"""
RUN = "logs/runs/collector/7-0123456789ab.log"


@pytest.fixture
def proj(tmp_path):
    d = tmp_path / "proj"
    (d / "lib").mkdir(parents=True)
    (d / "ergostat.yaml").write_text(MODEL)
    for f in ("collect.py", "app.rb", "lib/store.rb"):
        (d / f).write_text("#\n")
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    return Project(m)


def spec(p):
    return p.model.spec


def one(p, fid):
    return its.one(p.events, spec(p), fid)


def fail(p, stderr, log=None):
    """A failed run of the collector, triaged as the engine does (``stderr``: the tail of its own file)."""
    b = spec(p).blocks["collector"]
    data = {"exit": 1, "note": "exited 1", **({"log": log} if log else {})}
    begun = p.events.add("agent.started", item="collector", source="ergostat")
    return capture.failed(p, spec(p), b, begun, data, "in", stderr)["item"]


HOW = f"{FAILURE}/collector-{capture.signature('collector', 'collect.py', None, 'exited 1')}"


def _old(p, stderr, log=None, state="open"):
    """A failure signed the way it was before: by how it ended."""
    p.events.add("ergostat.run.failed", item=HOW, source="ergostat",
                 data={"block": "collector", "program": "collect.py", "stderr": stderr, "count": 1,
                       "error": "exited 1", **({"log": log} if log else {})})
    if state == "open":
        p.events.add(f"{FAILURE}.opened", item=HOW, source="ergostat", data={})
    assert one(p, HOW).state == state
    return HOW


def ruby(r, q="'", fn="Store#load"):
    return (f"{r}/vendor/bundle/ruby/3.3.0/gems/json-2.7.1/lib/json/common.rb:219:in {q}JSON.parse': "
            f"unexpected token at 'x' (JSON::ParserError)\n"
            f"\tfrom <internal:kernel>:187:in {q}loop'\n"
            f"\tfrom {r}/gems/local/lib/z.rb:3:in {q}each'\n"
            f"\tfrom {r}/lib/store.rb:12:in {q}{fn}'\n"
            f"\tfrom {r}/app.rb:4:in {q}<main>'\n")


@pytest.mark.parametrize("q", ["'", "`"])
def test_ruby_trace_innermost_project_frame(proj, q):
    r = spec(proj).root
    tb = capture.traceback_of("starting\n" + ruby(r, q), r)
    assert (tb["language"], tb["type"], tb["message"]) == ("ruby", "JSON::ParserError", "unexpected token at 'x'")
    assert (tb["file"], tb["line"], tb["function"]) == ("lib/store.rb", 12, "Store#load")
    assert [f["project"] for f in tb["frames"]] == [False, False, False, True, True]
    assert tb["frames"][0]["function"] == "JSON.parse"                   # innermost first: the header's own frame
    fid = fail(proj, ruby(r, q))
    assert fid == f"{FAILURE}/collector-{capture.signature('collector', 'collect.py', tb)}" != HOW
    assert one(proj, fid).state == "open"


def test_ruby_supersedes_old_item_only_on_same_signature(proj):
    r = spec(proj).root
    old = _old(proj, ruby(r, fn="Store#other"))
    fail(proj, ruby(r))
    assert one(proj, old).state == "open", "another bug that ended the same way is left alone"
    assert not proj.events.query(n=None, type=f"{FAILURE}.superseded")
    proj.events.add("ergostat.run.failed", item=old, source="ergostat", data={"stderr": ruby(r, "`")})
    new = fail(proj, ruby(r))
    assert one(proj, old).state == "superseded"
    assert proj.events.query(n=1, item=old)[-1]["data"] == {"by": new}


def long_py(r, back: int) -> str:
    """A Python traceback whose header is about ``back`` characters before the end, its last line the exception's."""
    end = f'  File "{r}/collect.py", line 6, in fetch\n    return d["issues"]\nKeyError: \'issues\'\n'
    out, i = "", 0
    while len(out) + len(end) < back:
        out += f'  File "{r}/collect.py", line {100 + i}, in step{i}\n    step{i + 1}()\n'
        i += 1
    return "earlier lines\nTraceback (most recent call last):\n" + out + end


def put(p, text, rel=RUN):
    f = Path(p.dir) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return capture.clip(text[-capture.TAIL - 1:])          # what the engine hands triage: the file's tail


def test_long_python_traceback_read_from_run_file(proj):
    r = spec(proj).root
    text = long_py(r, 20_000)
    tail = put(proj, text)
    assert capture.traceback_of(tail, r) is None                       # the tail alone holds no header
    old = _old(proj, tail, RUN)                                        # signed by how it ended, before
    tb = capture.traceback_of(text, r)
    assert (tb["type"], tb["file"], tb["function"]) == ("KeyError", "collect.py", "fetch")
    new = fail(proj, tail, RUN)
    assert new == f"{FAILURE}/collector-{capture.signature('collector', 'collect.py', tb)}" != old
    assert one(proj, new).fields["traceback"]["type"] == "KeyError"
    assert one(proj, old).state == "superseded"
    tail = put(proj, long_py(r, 70_000))
    assert fail(proj, tail, RUN) == HOW                                # its header is past the 64,000-character read
    put(proj, text + "and then it went on\n")
    assert fail(proj, tail, RUN) == HOW, "a traceback that does not run to the end of the file signs nothing"


@pytest.mark.parametrize("how", ["no log", "absent", "a folder", "a link"])
def test_missing_run_file_signs_by_how(proj, how):
    r = spec(proj).root
    text = long_py(r, 20_000)
    tail = capture.clip(text[-capture.TAIL - 1:])
    f = Path(proj.dir) / RUN
    f.parent.mkdir(parents=True, exist_ok=True)
    if how == "a folder":
        f.mkdir()
    elif how == "a link":
        (Path(proj.dir) / "elsewhere.log").write_text(text)
        os.symlink(Path(proj.dir) / "elsewhere.log", f)
    assert fail(proj, tail, None if how == "no log" else RUN) == HOW
    assert one(proj, HOW).fields["stderr"] == tail


def test_never_reads_block_log(proj):
    r = spec(proj).root
    other = long_py(r, 20_000)                                         # another run's, whole, in the block's log
    (Path(proj.dir) / "logs").mkdir(exist_ok=True)
    (Path(proj.dir) / "logs/collector.log").write_text("--- run abcd (exited 1)\n" + other)
    tail = put(proj, "ours: no header\n    return d['issues']\nKeyError: 'issues'\n")
    assert fail(proj, tail, RUN) == HOW
    assert fail(proj, tail, "logs/collector.log") == HOW
    assert fail(proj, tail) == HOW
