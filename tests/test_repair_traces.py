"""Repair's triage reads Node, Java and Go tracebacks as well as Python's, records an error a good run swallowed without
moving any failure, decides opening in the fold (``ItemKind.moves_from``) and supersedes the old items the new
signatures replace (SPEC §12r, *Triage*; dev/records/repair-traces.md)."""

import json
import threading
import time

import pytest

from ergostat import model as mdl
from ergostat.repair import FAILURE, capture, traces
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

MODEL = """\
name: traces-demo
projections:
  issue: {id: issue/*, states: [open, closed], on: {issue.seen: open}}
stocks:
  open-issues: {unit: issues, cumulative: true, sensor: {projection: issue, state: open, every: 1h}}
flows:
  issues-found: {to: open-issues, sensor: {projection: issue, entering: open, over: 10m}}
blocks:
  collector:
    type: program
    run: python3 collect.py
    every: 1h
    out: flow.issues-found
uses:
  repair:
    use: repair
    with: {count-every: 1h, approver: person}
"""
CATCHES = """\
import sys, traceback
def look(d):
    return d["issues"]
try:
    look({})
except KeyError:
    traceback.print_exc()
sys.exit(0)
"""
R = "0123456789abcdef0123"            # the run that takes a lease in these tests


@pytest.fixture
def proj(tmp_path, monkeypatch):
    from ergostat import runner
    runner.STOPPING.clear()
    d = tmp_path / "proj"
    (d / "lib").mkdir(parents=True)
    (d / "ergostat.yaml").write_text(MODEL)
    (d / "collect.py").write_text(CATCHES)
    for f in ("app.js", "lib/parse.js", "main.go", "pick.go"):
        (d / f).write_text("//\n")
    for c in ("App", "Store", "Config", "Other"):
        (d / "src/main/java/com/acme").mkdir(parents=True, exist_ok=True)
        (d / f"src/main/java/com/acme/{c}.java").write_text("//\n")
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    p = Project(m)
    yield p
    runner.STOPPING.clear()


def spec(p):
    return p.model.spec


def block(p):
    return spec(p).blocks["collector"]


def one(p, fid):
    return its.one(p.events, spec(p), fid)


def begun(p, at=None):
    e = p.events.add("agent.started", item="collector", source="ergostat")
    return {**e, "time": at if at is not None else e["time"]}


def fail(p, stderr, note="exited 1", stdin="in"):
    """A failed run of the collector, triaged as the engine does."""
    row = capture.failed(p, spec(p), block(p), begun(p), {"exit": 1, "note": note}, stdin, stderr)
    return row["item"]


def swallow(p, tail, stdin="good input"):
    row = capture.swallowed(p, spec(p), block(p), begun(p), tail, stdin)
    return row and row["item"]


def ev(p, type_, fid, causedby=None, **data):
    return p.events.add(type_, item=fid, source="ergostat", causedby=causedby, data=data)


def take(p, fid, fence=1, max_=3):
    ev(p, "ergostat.lease.taken", fid, run=R, block="repair-fix", fence=fence, ttl=600, max=max_, back="open")


def py(r):
    return f'''Traceback (most recent call last):
  File "{r}/collect.py", line 9, in <module>
    main()
  File "{r}/collect.py", line 6, in fetch
    return helper.call(url)
  File "{r}/.venv/lib/python3.12/site-packages/requests/api.py", line 73, in get
    return request("get", url)
KeyError: 'issues'
'''


def node(r, fn="parse"):
    return f'''{r}/app.js:4
  const id = rows.map(parse)[0].id;
                                ^

TypeError: Cannot read properties of undefined (reading 'id')
    at Object.get ({r}/node_modules/lodash/get.js:5:3)
    at {fn} ({r}/lib/parse.js:10:17)
    at Array.map (<anonymous>)
    at main (file://{r}/app.js:4:20)
    at node:internal/main/run_main_module:28:49

Node.js v20.11.0
'''


def java_no_cause():
    return '''Exception in thread "main" java.lang.IllegalStateException: no store
\tat java.base/java.util.Objects.requireNonNull(Objects.java:233)
\tat com.acme.Store.open(Store.java:12)
\tat com.acme.App.main(App.java:5)
\tSuppressed: java.lang.IllegalArgumentException: closing
\t\tat com.acme.Other.close(Other.java:1)
'''


ONE_CAUSE = '''Exception in thread "main" java.lang.RuntimeException: wrapped
\tat com.acme.App.main(App.java:9)
Caused by: java.io.FileNotFoundException: store.db
\tat java.base/java.io.FileInputStream.open0(Native Method)
\tat com.acme.Store.open(Store.java:12)
\tat com.acme.App.main(App.java:7)
\t... 1 more
'''
TWO_CAUSES = ONE_CAUSE + '''Caused by: java.lang.NumberFormatException: For input string: "x"
\tat java.base/java.lang.Integer.parseInt(Integer.java:652)
\tat com.acme.Config.port(Config.java:3)
\t... 2 more
'''
ROOT_LIBRARY = '''Exception in thread "main" java.lang.RuntimeException: wrapped
\tat com.acme.App.main(App.java:9)
Caused by: java.io.UncheckedIOException: java.nio.file.NoSuchFileException: store.db
\tat com.acme.Store.open(Store.java:12)
\t... 1 more
Caused by: java.nio.file.NoSuchFileException: store.db
\tat java.base/sun.nio.fs.UnixException.translateToIOException(UnixException.java:92)
\tat java.base/sun.nio.fs.UnixFileSystemProvider.newByteChannel(UnixFileSystemProvider.java:218)
\t... 2 more
'''


def go(r):
    return f'''panic: runtime error: index out of range [3] with length 3

goroutine 1 [running]:
github.com/x/y.Do(0x0)
\t{r}/vendor/github.com/x/y/y.go:20 +0x45
main.pick(...)
\t{r}/pick.go:7
main.main()
\t{r}/main.go:12 +0x1d
exit status 2
'''


# ---- parsing (1)


@pytest.mark.parametrize("lang", ["python", "node", "java", "go"])
def test_each_language_is_read(proj, lang):
    r = spec(proj).root
    text = {"python": py(r), "node": node(r), "java": java_no_cause(), "go": go(r)}[lang]
    want = {"python": ("KeyError", "'issues'", "collect.py", 6, "fetch"),
            "node": ("TypeError", "Cannot read properties of undefined (reading 'id')", "lib/parse.js", 10, "parse"),
            "java": ("java.lang.IllegalStateException", "no store", "com/acme/Store.java", 12, "com.acme.Store.open"),
            "go": ("panic", "runtime error: index out of range [3] with length 3", "pick.go", 7, "main.pick")}[lang]
    tb = traces.last("some output first\n" + text + "and after\n", r)
    assert tb is not None and tb["language"] == lang
    assert (tb["type"], tb["message"], tb["file"], tb["line"], tb["function"]) == want
    assert tb["frames"][0]["project"] is False, "innermost first: a library frame"


@pytest.mark.parametrize("case", ["no-cause", "one-cause", "two-causes", "root-frames-all-library"])
def test_java_takes_type_from_the_root_cause_and_its_innermost_project_frame(proj, case):
    text, want = {
        "no-cause": (java_no_cause(), ("java.lang.IllegalStateException", "no store", "com.acme.Store.open", 12)),
        "one-cause": (ONE_CAUSE, ("java.io.FileNotFoundException", "store.db", "com.acme.Store.open", 12)),
        "two-causes": (TWO_CAUSES, ("java.lang.NumberFormatException", 'For input string: "x"', "com.acme.Config.port",
                                    3)),
        "root-frames-all-library": (ROOT_LIBRARY, ("java.nio.file.NoSuchFileException", "store.db",
                                                   "com.acme.Store.open", 12))}[case]
    tb = traces.last(text, spec(proj).root)
    assert (tb["type"], tb["message"], tb["function"], tb["line"]) == want
    assert "walk" not in tb


def test_python_signatures_are_unchanged(proj):
    r = spec(proj).root
    text = py(r).replace(f'  File "{r}/.venv', '  File "/opt/tools/helper.py", line 21, in call\n    x()\n'
                                                f'  File "{r}/.venv')
    tb = traces.last(text, r)
    assert (tb["file"], tb["function"]) == ("/opt/tools/helper.py", "call"), "the innermost frame with no LIBRARY marker"
    assert capture.signature("collector", "collect.py", tb) == "c72bb8ff"
    assert fail(proj, text) == f"{FAILURE}/collector-c72bb8ff"


def _padded(lang, r):
    pad = 400
    return {"python": "Traceback (most recent call last):\n" + f'  File "{r}/collect.py", line 6, in fetch\n' * pad
            + "KeyError: 'x'\n",
            "node": "TypeError: boom\n" + f"    at parse ({r}/lib/parse.js:10:17)\n" * pad,
            "java": 'Exception in thread "main" java.lang.RuntimeException: x\n'
            + "\tat com.acme.App.main(App.java:9)\n" * pad
            + "Caused by: java.io.IOException: y\n\tat com.acme.Store.open(Store.java:12)\n",
            "go": "panic: boom\n\ngoroutine 1 [running]:\n" + f"main.main()\n\t{r}/main.go:12 +0x1d\n" * pad}[lang]


@pytest.mark.parametrize("lang", ["python", "node", "java", "go"])
def test_a_trace_whose_header_the_tail_cut_off_gives_none(proj, lang):
    r = spec(proj).root
    text = _padded(lang, r)
    assert len(text) > capture.TAIL + 100 and traces.last(text, r) is not None, "whole, it is read"
    tail = capture.clip(text[-(capture.TAIL + 1):])
    assert len(tail) <= capture.TAIL and traces.last(tail, r) is None
    if lang == "java":
        assert "Caused by: java.io.IOException" in tail
    fid = fail(proj, tail)
    assert fid == f"{FAILURE}/collector-{capture.signature('collector', 'collect.py', None, 'exited 1')}"


def test_the_tail_drops_its_first_partial_line():
    text = "x" * 10 + "\n" + "a" * (capture.TAIL - 5) + "\nlast\n"
    assert capture.clip(text[-(capture.TAIL + 1):]) == "last\n"
    assert capture.clip("short\n") == "short\n"
    whole = "y" * 9 + "\n" + "b" * (capture.TAIL - 1)
    assert capture.clip(("z" + whole)[-(capture.TAIL + 1):]) == "b" * (capture.TAIL - 1), "it begins mid-line"
    exact = "\n" + "c\n" * (capture.TAIL // 2)
    assert capture.clip(exact[-(capture.TAIL + 1):]) == exact[-capture.TAIL:], "it begins at a line: nothing dropped"


def test_the_last_trace_in_the_text_is_taken(proj):
    r = spec(proj).root
    tb = traces.last(ONE_CAUSE + "\nthen\n" + node(r), r)
    assert tb["language"] == "node"
    assert traces.last(node(r) + ONE_CAUSE, r)["language"] == "java"


# ---- project frames (2)


@pytest.mark.parametrize("file,ours", [
    ("{r}/lib/parse.js", True), ("lib/parse.js", True), ("{r}/main.go", True),
    ("{r}/node_modules/lodash/get.js", False), ("{r}/.venv/lib/a.py", False), ("{r}/vendor/x/y.go", False),
    ("{r}/env/lib/python3.12/site-packages/req.py", False), ("/usr/lib/node/x.js", False),
    ("node:internal/main/run_main_module", False), ("/usr/local/go/src/runtime/panic.go", False),
    ("<frozen runpy>", False), ("../outside.js", False)])
def test_a_project_frame_is_under_the_models_folder_and_outside_library_folders(proj, file, ours):
    r = spec(proj).root
    assert traces.project(file.format(r=r), r) is ours


def test_a_java_frame_is_the_projects_when_its_package_path_is_a_file_under_the_folder(proj):
    tb = traces.last(java_no_cause(), spec(proj).root)
    got = {f["function"]: f["project"] for f in tb["frames"]}
    assert got == {"java.util.Objects.requireNonNull": False, "com.acme.Store.open": True, "com.acme.App.main": True}
    assert [f["file"] for f in tb["frames"]][1] == "com/acme/Store.java"
    text = java_no_cause().replace("com.acme.Store", "com.other.Store")
    assert traces.last(text, spec(proj).root)["function"] == "com.acme.App.main", "com/other/Store.java is not there"


def test_a_capped_java_walk_finds_no_project_frame(proj, monkeypatch):
    r = spec(proj).root
    monkeypatch.setattr(traces, "WALK", 50)
    (r / "aaa").mkdir()
    for i in range(51):
        (r / "aaa" / f"f{i}").write_text("")
    tb = traces.last(java_no_cause(), r)
    assert tb["walk"] == "capped" and not any(f["project"] for f in tb["frames"])
    assert swallow(proj, java_no_cause()) is None
    assert not proj.events.query(n=None, type="ergostat.run.swallowed")
    monkeypatch.setattr(traces, "WALK", 5000)
    assert traces.last(java_no_cause(), r)["frames"][1]["project"] is True, "under the cap, it is found"


# ---- swallowed (3)


def kinds(p) -> list[str]:
    return [e["type"] for e in p.events.query(n=None) if e["type"].startswith(("ergostat.failure", "ergostat.run."))]


def test_a_good_run_that_swallowed_a_project_error_records_a_noted_failure(proj):
    e = Engine(proj, say=lambda s: None)
    try:
        e.run_block(block(proj), "test")
    finally:
        e.close()
    assert proj.events.query(n=1, item="collector", type="agent.ran")
    got = its.project(proj.events, spec(proj), FAILURE)
    assert len(got) == 1, got
    it = got[0]
    assert it.state == "noted" and it.fields["swallowed"] == 1 and it.fields["count"] == 0
    assert it.fields["traceback"]["type"] == "KeyError" and it.fields["traceback"]["function"] == "look"
    assert it.fields["program"] == "collect.py" and "KeyError" in it.fields["stderr"]
    assert kinds(proj) == ["ergostat.run.swallowed"], "no opened"
    assert (proj.dir / "repair" / f"{it.id.split('/')[1]}.input").is_file()


def test_a_good_run_with_only_library_frames_records_nothing(proj):
    r = spec(proj).root
    fake = (f'Traceback (most recent call last):\n  File "{r}/.venv/lib/python3.12/site-packages/req/api.py", line 3, '
            f'in get\n    x()\n  File "{r}/node_modules/x/y.py", line 4, in z\n    y()\nKeyError: \'x\'\n')
    (r / "collect.py").write_text(f"import sys\nsys.stderr.write({fake!r})\n")
    e = Engine(proj, say=lambda s: None)
    try:
        e.run_block(block(proj), "test")
    finally:
        e.close()
    assert proj.events.query(n=1, item="collector", type="agent.ran")
    assert kinds(proj) == []
    assert not (proj.dir / "repair").exists() or not any((proj.dir / "repair").iterdir())


def _make(p, state, text):
    """A failure in ``state`` (``leased``: by a real lease taken), its trace ``text``."""
    if state == "noted":
        return fail(p, text, note="killed: its lease expired")
    fid = fail(p, text)
    if state in ("leased", "awaiting-approval", "applied"):
        take(p, fid)
    if state in ("awaiting-approval", "applied"):
        ev(p, f"{FAILURE}.passed", fid, causedby=R, fix="0" * 40)
        ev(p, "ergostat.lease.ended", fid, run=R, fence=1, how="ack")
    if state == "applied":
        ev(p, f"{FAILURE}.applied", fid)                 # (by apply, after the fixer's lease ended)
    assert one(p, fid).state == state
    return fid


@pytest.mark.parametrize("state", ["noted", "open", "leased", "awaiting-approval", "applied"])
def test_a_swallowed_record_moves_no_existing_failure(proj, state):
    text = node(spec(proj).root)
    fid = _make(proj, state, text)
    before = one(proj, fid)
    name = fid.split("/")[1]
    kept = (proj.dir / "repair" / f"{name}.input").read_bytes()
    assert swallow(proj, "it ran on\n" + text, stdin="another input") == fid
    after = one(proj, fid)
    assert after.state == state
    lb, la = before.fields.get("lease") or {}, after.fields.get("lease") or {}
    assert (la.get("holder"), la.get("fence")) == (lb.get("holder"), lb.get("fence"))
    for f in ("error", "traceback", "stderr", "count", "input", "began"):
        assert after.fields.get(f) == before.fields.get(f), f
    assert (proj.dir / "repair" / f"{name}.input").read_bytes() == kept
    assert after.fields["swallowed"] == (before.fields.get("swallowed") or 0) + 1
    last = proj.events.query(n=1, item=fid)[-1]
    assert last["type"] == "ergostat.run.swallowed" and set(last["data"]) == {"swallowed", "last_swallowed"}
    assert not after.refused


def test_a_failed_run_still_opens_a_noted_swallowed_failure(proj):
    text = node(spec(proj).root)
    fid = swallow(proj, text)
    assert one(proj, fid).state == "noted"
    assert fail(proj, text) == fid
    it = one(proj, fid)
    assert it.state == "open" and it.fields["count"] == 1 and it.fields["swallowed"] == 1


# ---- opening, and the lock (4)


@pytest.mark.parametrize("was", ["noted", "applied"])
def test_opened_after_a_lease_taken_between_triages_read_and_write_leaves_it_leased(proj, monkeypatch, was):
    text = node(spec(proj).root)
    fid = _make(proj, was, text)
    real = capture.current

    def between(p, sp, f):
        got = real(p, sp, f)
        if f == fid:                         # another triage opened it, and the dispatcher took it, in the gap
            assert got.state == was
            ev(p, f"{FAILURE}.opened", fid)
            take(p, fid, fence=2 if was == "applied" else 1)
        return got
    monkeypatch.setattr(capture, "current", between)
    fail(proj, text)
    it = one(proj, fid)
    assert it.state == "leased" and it.fields["lease"]["holder"] == R
    assert any(x["type"] == f"{FAILURE}.opened" and x["form"] == "from" for x in it.refused), it.refused


@pytest.mark.parametrize("second", ["failed", "swallowed"])
def test_two_triages_of_one_new_signature_are_serialised_by_the_capture_lock(proj, monkeypatch, second):
    text = py(spec(proj).root)                # (Python: one read a triage, no old item looked for)
    real, read2, order, errors = capture.current, threading.Event(), [], []
    main = threading.current_thread()
    t0 = time.time()

    def call2():
        try:
            b = begun(proj, at=t0 + 5)
            if second == "failed":
                capture.failed(proj, spec(proj), block(proj), b, {"exit": 1, "note": "exited 1"}, "two", text)
            else:
                capture.swallowed(proj, spec(proj), block(proj), b, text, "two")
        except Exception as e:                # (said in the main thread)
            errors.append(e)
    t = threading.Thread(target=call2)

    def current(p, sp, f):
        if threading.current_thread() is main:
            t.start()
            read2.wait(2)                     # bounded: with the lock, call 2 never reads before call 1 writes
            order.append("read 1")
        else:
            order.append("read 2")
            read2.set()
        return real(p, sp, f)
    adds = proj.events.add_many

    def add_many(rows, new=False):
        order.append("write 1" if threading.current_thread() is main else "write 2")
        return adds(rows, new=new)
    monkeypatch.setattr(capture, "current", current)
    monkeypatch.setattr(proj.events, "add_many", add_many)
    capture.failed(proj, spec(proj), block(proj), begun(proj, at=t0), {"exit": 1, "note": "exited 1"}, "one", text)
    t.join(10)
    assert not t.is_alive() and not errors, errors
    assert order == ["read 1", "write 1", "read 2", "write 2"]
    fid = proj.events.query(n=None, type="ergostat.run.failed")[0]["item"]
    it = one(proj, fid)
    assert it.fields["first_seen"] == t0 and it.fields["began"] == t0, "the second saw it there: no began of its own"
    if second == "failed":
        assert it.fields["count"] == 2
    else:
        last = proj.events.query(n=None, type="ergostat.run.swallowed")
        assert len(last) == 1 and set(last[0]["data"]) == {"swallowed", "last_swallowed"}, "counts only"
        assert it.fields["count"] == 1 and it.state == "open"


OPENED = {"noted": "open", "open": "open", "leased": "leased", "awaiting-approval": "awaiting-approval",
          "applied": "applied", "superseded": "open", "dismissed": "dismissed", "dead": "dead",
          "verified": "open", "regressed": "regressed", "reverted": "reverted"}   # (applied: settle's, repair-verify)


def _put(p, fid, state):
    """``fid`` taken to ``state`` by the events that move it there."""
    ev(p, "ergostat.run.failed", fid, block="collector", count=1)
    if state == "noted":
        return
    ev(p, f"{FAILURE}.opened", fid)
    after = ("verified", "regressed", "reverted")
    if state in ("leased", "awaiting-approval", "applied", "dismissed", "dead", *after):
        take(p, fid, max_=1 if state == "dead" else 3)
    if state == "dead":
        ev(p, "ergostat.lease.ended", fid, run=R, fence=1, how="nack")
    if state in ("awaiting-approval", "applied", "dismissed", *after):
        ev(p, f"{FAILURE}.passed", fid, causedby=R)
        ev(p, "ergostat.lease.ended", fid, run=R, fence=1, how="ack")
    if state in ("applied", *after):
        ev(p, f"{FAILURE}.applied", fid)
    if state in ("dismissed", "verified", "regressed"):
        ev(p, f"{FAILURE}.{state}", fid)
    if state == "reverted":
        ev(p, f"{FAILURE}.regressed", fid)
        ev(p, f"{FAILURE}.reverted", fid)
    if state == "superseded":
        ev(p, f"{FAILURE}.superseded", fid, by="x")


def test_opened_moves_only_from_noted_verified_or_superseded(proj):
    """``superseded``: so an old signature superseded hides no later failure. ``applied`` no longer (repair-verify):
    a fix failing again is settle's to judge, ``regressed`` and ``reverted`` a person's."""
    states = spec(proj).items[FAILURE].states
    assert sorted(OPENED) == sorted(states), "every state of the compiled kind has a row"
    for s in states:
        fid = f"{FAILURE}/t-{s}"
        _put(proj, fid, s)
        assert one(proj, fid).state == s
        ev(proj, f"{FAILURE}.opened", fid)
        it = one(proj, fid)
        assert it.state == OPENED[s], s
        assert any(x["form"] == "from" for x in it.refused) is (OPENED[s] == s != "open"), s


# ---- superseding (6)


def _old(p, text, state="open"):
    """A failure signed the way it was before triage read Node: by how it ended."""
    fid = f"{FAILURE}/collector-{capture.signature('collector', 'collect.py', None, 'exited 1')}"
    ev(p, "ergostat.run.failed", fid, block="collector", program="collect.py", stderr=text, count=1, error="exited 1")
    if state != "noted":
        ev(p, f"{FAILURE}.opened", fid)
    if state in ("leased", "awaiting-approval", "applied"):
        take(p, fid)
    if state in ("awaiting-approval", "applied"):
        ev(p, f"{FAILURE}.passed", fid, causedby=R)
    if state == "applied":
        ev(p, f"{FAILURE}.applied", fid, causedby=R)
    assert one(p, fid).state == state
    return fid


@pytest.mark.parametrize("state", ["noted", "open"])
def test_an_old_how_signed_failure_is_superseded_by_its_trace_signature(proj, state):
    text = node(spec(proj).root)
    old = _old(proj, text, state)
    new = fail(proj, text)
    assert new != old and one(proj, new).state == "open"
    it = one(proj, old)
    assert it.state == "superseded" and proj.events.query(n=1, item=old)[-1]["data"] == {"by": new}


@pytest.mark.parametrize("case", ["leased", "awaiting-approval", "applied", "other-trace"])
def test_an_old_failure_being_worked_or_of_another_bug_is_not_superseded(proj, case):
    r = spec(proj).root
    old = _old(proj, node(r, fn="other") if case == "other-trace" else node(r),
               "open" if case == "other-trace" else case)
    before = one(proj, old)
    fail(proj, node(r))
    it = one(proj, old)
    assert it.state == before.state and it.fields.get("lease") == before.fields.get("lease")
    if case == "other-trace":
        assert not proj.events.query(n=None, type=f"{FAILURE}.superseded")
        return
    assert any(x["type"] == f"{FAILURE}.superseded" and x["form"] == "from" for x in it.refused)
    if case == "leased":
        assert it.fields["lease"]["holder"] == R
        ev(proj, "ergostat.lease.ended", old, run=R, fence=1, how="nack")
        assert one(proj, old).state == "open"
        fail(proj, node(r))
        assert one(proj, old).state == "superseded"


def test_a_lease_taken_between_the_supersede_read_and_write_keeps_the_old_item_leased(proj, monkeypatch):
    text = node(spec(proj).root)
    old = _old(proj, text)
    real = capture.current

    def between(p, sp, f):
        got = real(p, sp, f)
        if f == old:
            assert got.state == "open"
            take(p, old)
        return got
    monkeypatch.setattr(capture, "current", between)
    fail(proj, text)
    it = one(proj, old)
    assert it.state == "leased" and it.fields["lease"]["holder"] == R
    assert any(x["type"] == f"{FAILURE}.superseded" and x["form"] == "from" for x in it.refused)


def test_a_traceless_failure_after_superseding_opens_the_old_signature_again(proj):
    text = node(spec(proj).root)
    old = _old(proj, text)
    fail(proj, text)
    assert one(proj, old).state == "superseded"
    assert fail(proj, "nothing it could say\n") == old
    it = one(proj, old)
    assert it.state == "open" and it.fields["stderr"] == "nothing it could say\n"
    fail(proj, text)
    assert one(proj, old).state == "open", "its stderr is another ending now: not the same bug, not superseded"


def test_python_failures_are_never_superseded(proj):
    text = py(spec(proj).root)
    _old(proj, text)
    fail(proj, text)
    assert not proj.events.query(n=None, type=f"{FAILURE}.superseded")
    json.dumps([e["data"] for e in proj.events.query(n=None)])       # (everything recorded is plain JSON)
