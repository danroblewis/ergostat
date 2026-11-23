"""Each merge batch is an item, batch/<run tag> (dev/records/merge-batch-is-an-item.md; dev/bin/batches.py): the queue
says its start, each run, the gaps it isolates, what lands and how it ends, and the item index, the Items page and its
Timeline show it. The queue's own runs here use the fixture's fake suites (tests/test_factory.py); the item index and
the Timeline are fed the events batches.py says, in this process."""

from __future__ import annotations

import json
import sys
import textwrap
import types

import pytest

from tests.test_factory import ANY_BAD, BIN, CLOCKED, ROOT, Factory, approved_gaps, git, merges, module, suite_runs


def said(lines: list[dict]) -> list[str]:
    return [x["event"] for x in lines if x.get("event", "").startswith("batch.")]


def batch(f: Factory) -> dict:
    got = [i for i in f.db()["items"].values() if i["kind"] == "batch"]
    assert len(got) == 1, [i["id"] for i in got]
    return got[0]


def settle_push(f: Factory, to: str = "ran") -> list[dict]:
    """The batch's push, held, now ran (or ``to``): push-settler settles it."""
    db = f.db()
    (aid,) = db["actions"]
    db["actions"][aid] = to
    f.record.write_text(json.dumps(db))
    return f.run("queue.py", argv=("settle",))[1]


@pytest.mark.slow
def test_a_clean_batch_is_tested_once_lands_and_ends_landed(tmp_path):
    f = Factory(tmp_path, unit=f"echo run >> {tmp_path / 'runs'}; echo '3 passed in 0.10s'")
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    pre = git(f.checkout, "rev-parse", "main")
    _, lines = f.run("queue.py", "gap/a")
    assert said(lines) == ["batch.started", "batch.run-started", "batch.run-finished", "batch.landed"]
    b = batch(f)
    assert b["id"].startswith("batch/a-") and b["state"] == "pushing"            # merged, its push held
    fl = b["fields"]
    assert fl["gaps"] == ["gap/a", "gap/b"] and fl["size"] == 2 and fl["base"] == pre
    assert fl["landed"] == ["gap/a", "gap/b"] and fl["main_sha"] == git(f.checkout, "rev-parse", "main")
    (run,) = fl["runs"]
    assert run | {"minutes": 0} == {"run": 1, "kind": "full", "gaps": ["gap/a", "gap/b"], "outcome": "passed",
                                    "failed": 0, "passed": 3, "counted": ["unit"], "first_failing": [], "minutes": 0}
    assert fl["runs_n"] == 1                                                     # (browser said no counts: not counted)
    assert said(settle_push(f)) == ["batch.ended.landed"]
    b = batch(f)
    assert b["state"] == "landed" and b["fields"]["given_back"] == [] and b["fields"]["why"] == "its push ran"
    assert merges(f) == ["a", "b"] and suite_runs(f) == 1


@pytest.mark.slow
def test_a_batch_with_one_bad_merge_isolates_it_and_ends_partial(tmp_path):
    f = Factory(tmp_path, unit=ANY_BAD.format(runs=tmp_path / "runs", greens=tmp_path / "greens"))
    approved_gaps(f, {"a": 1, "b": 2}, batch=2, edits={"a": "bad-a.txt"})
    _, lines = f.run("queue.py", "gap/b")
    assert merges(f) == ["b"] and f.item("gap/a")["state"] == "queue-failed"     # as the queue does without the item
    assert said(lines) == ["batch.started", "batch.run-started", "batch.run-finished", "batch.run-started",
                           "batch.run-finished", "batch.isolated", "batch.landed"]
    fl = batch(f)["fields"]
    assert [(r["kind"], r["outcome"], r["gaps"]) for r in fl["runs"]] == [
        ("full", "failed", ["gap/a", "gap/b"]), ("halves", "failed", ["gap/a", "gap/b"])]   # one half red, one green
    assert fl["runs"][0]["first_failing"] == ["tests/test_b.py::test_b"]
    assert fl["runs"][0]["counted"] == []                                         # no pytest summary: none counted
    assert fl["isolated"] == [{"gap": "gap/a", "how": "halves", "tests": ["tests/test_b.py::test_b"]}]
    assert fl["landed"] == ["gap/b"]
    assert said(settle_push(f)) == ["batch.ended.partial"]
    b = batch(f)
    assert b["state"] == "partial" and b["fields"]["failed"] == ["gap/a"] and b["fields"]["given_back"] == []


@pytest.mark.slow
def test_a_crashed_run_says_its_cause_and_the_batch_is_given_back(tmp_path):
    unit = (f"echo run >> {tmp_path}/runs; echo 'FAILED tests/test_x.py::t - x'; "
            "echo 'OSError: [Errno 28] No space left on device'; exit 1")
    f = Factory(tmp_path, unit=unit)
    approved_gaps(f, {x: i for i, x in enumerate("abcd", 1)}, batch=4)
    _, lines = f.run("queue.py", "gap/a")
    assert merges(f) == [] and suite_runs(f) == 3                                # the whole, then both halves
    assert said(lines) == ["batch.started", "batch.run-started", "batch.run-finished", "batch.run-started",
                           "batch.run-finished", "batch.ended.given-back"]
    b = batch(f)
    assert b["state"] == "given-back"
    runs = b["fields"]["runs"]
    assert [(r["kind"], r["outcome"], r.get("crash")) for r in runs] == [
        ("full", "crashed", "[Errno 28]"), ("halves", "crashed", "[Errno 28]")]
    assert runs[0]["first_failing"] == []                                         # a crash names no test
    assert b["fields"]["why"].startswith("its run stalled: the unit suite was stopped (both halves crashed: [Errno 28])")
    assert [x["gap"] for x in b["fields"]["given_back"]] == ["gap/a", "gap/b", "gap/c", "gap/d"]
    assert b["fields"]["failed"] == []


@pytest.mark.slow
def test_a_batch_out_of_time_lands_what_was_proven_and_gives_back_the_rest(tmp_path):
    f = Factory(tmp_path, unit=ANY_BAD.format(runs=tmp_path / "runs", greens=tmp_path / "greens"))
    f.config.write_text(f.config.read_text().replace("batch_max = 4", "batch_max = 10\nbatch_minutes = 70"))
    approved_gaps(f, {x: i for i, x in enumerate("abcdefghij", 1)}, batch=10, edits={"a": "bad-a.txt"})
    (tmp_path / "clocked.py").write_text(CLOCKED)
    _, lines = f.run(str(tmp_path / "clocked.py"), "gap/f", argv=(str(BIN), "20"))
    assert merges(f) == list("fghij")                                             # as test_queue_halves.py holds
    fl = batch(f)["fields"]
    assert [(r["kind"], r["outcome"]) for r in fl["runs"]] == [("full", "failed"), ("halves", "failed")]
    assert fl["runs"][0]["minutes"] == 40.0                     # the suites and its tests alone (main's check: after it)
    assert fl["runs"][1]["minutes"] == 20.0 and fl["minutes"] == 80.0             # the round; landed at 80
    assert "batch.isolated" not in said(lines) and fl["landed"] == [f"gap/{x}" for x in "fghij"]
    settle_push(f)
    b = batch(f)
    assert b["state"] == "partial" and b["fields"]["failed"] == []
    assert [x["gap"] for x in b["fields"]["given_back"]] == [f"gap/{x}" for x in "abcde"]
    assert {x["why"] for x in b["fields"]["given_back"]} == {"its run's time allowance was used before it was proven"}


@pytest.mark.slow
def test_a_denied_push_ends_the_batch_failed(tmp_path):
    f = Factory(tmp_path, unit="true")
    approved_gaps(f, {"a": 1}, batch=1)
    f.run("queue.py", "gap/a")
    assert said(settle_push(f, "denied")) == ["batch.ended.failed"]
    assert batch(f)["state"] == "failed" and batch(f)["fields"]["why"] == "its push denied"


FAILING = """\
import sys
sys.path[:0] = [sys.argv[1]]
import batches, queue
def broken(*a, **k):
    raise OSError(28, "No space left on device")
batches._say = batches._mark = broken
sys.exit(queue.main())
"""


@pytest.mark.slow
def test_a_failing_event_write_changes_nothing_that_lands(tmp_path):
    runs = {}
    for name, program in (("plain", "queue.py"), ("failing", str(tmp_path / "failing.py"))):
        d = tmp_path / name
        d.mkdir()
        f = Factory(d, unit=ANY_BAD.format(runs=d / "runs", greens=d / "greens"))
        approved_gaps(f, {"a": 1, "b": 2, "c": 3}, batch=3, edits={"b": "bad-b.txt"})
        (tmp_path / "failing.py").write_text(FAILING)
        got, lines = f.run(program, "gap/a", argv=(str(BIN),) if name == "failing" else ())
        runs[name] = (got, merges(f), suite_runs(f), {g: f.item(f"gap/{g}")["state"] for g in "abc"},
                      [x for x in lines if "nack" in x])
        if name == "failing":
            assert said(lines) == [] and not any(i["kind"] == "batch" for i in f.db()["items"].values())
    assert runs["plain"] == runs["failing"] and runs["plain"][1] == ["c", "a"]     # (the green half first, then a)


# ---- the item index and the Timeline, from the events batches.py says

def batches_module(monkeypatch, tmp_path):
    sys.modules.setdefault("fac", module("fac"))
    b = module("batches")
    clock, out = [1_800_000_000.0], []
    monkeypatch.setattr(b, "time", types.SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(b, "_say", lambda event, item, **data: out.append((event, item, data, clock[0])))
    return b, clock, out, {"paths": {"run": str(tmp_path / "run")}}


def three_runs(b, clock, cfg) -> list[tuple[float, float]]:
    """A batch of three: red in full, then two rounds of halves (b found alone); a and c land, the push runs."""
    spans = []
    b.begin(cfg, "a-20261123T100000Z", ["gap/a", "gap/b", "gap/c"], "0" * 40)
    red = {"failed": "unit", "tests": ["tests/t.py::t"], "unit": {"counts": {"failed": 1, "passed": 9}}}
    green = {"unit": {"counts": {"failed": 0, "passed": 5}}}
    for kind, gaps, got in (("full", ["gap/a", "gap/b", "gap/c"], [red]), ("halves", ["gap/a", "gap/b", "gap/c"], [green, red]),
                            ("halves", ["gap/b", "gap/c"], [red, green])):
        clock[0] += 30
        t0 = clock[0]
        with b.run(kind, gaps) as seen:
            clock[0] += 600
            seen += got
        spans.append((t0, clock[0]))
    b.isolated("gap/b", "halves", ["tests/t.py::t"])
    b.settled(["gap/a", "gap/c"], "1" * 40, [])
    p = b.pending()
    clock[0] += 120
    b.pushed(p, "ran")
    return spans


def project(tmp_path, out):
    from ergostat import model as mdl
    from ergostat.store import Project
    text = (ROOT / "dev" / "model" / "landing.yaml").read_text()
    kind = text[text.index("\nitems:\n") + 1:text.index("\nstocks:")]
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "ergostat.yaml").write_text(kind + textwrap.dedent("""
          gap:
            id: gap/*
            states: [approved, merged]
        messages:
          done: {batch: [landed, partial, failed, given-back], gap: [merged]}
        """))
    p = Project(mdl.load(tmp_path / "m"))
    assert not [x for x in p.model.problems if x.level == "error"], p.model.problems
    for g in "abc":
        p.events.add("gap.approved", item=f"gap/{g}", at=out[0][3] - 60)
    for event, item, data, at in out:
        p.events.add(event, item=item, data=json.loads(json.dumps(data)), at=at)
    return p


def test_the_root_model_has_the_batch_kind_and_its_finished_states():
    from ergostat.spec import read
    spec, problems = read(ROOT / "ergostat.yaml")
    assert [p for p in problems if p.level == "error"] == []
    k = spec.items["batch"]
    assert k.states == ["testing", "isolating", "pushing", "landed", "partial", "failed", "given-back"]
    assert spec.messages.done["batch"] == ["landed", "partial", "failed", "given-back"] == list(k.final)
    assert {"batch-run-percent", "batch-run-failures"} <= set(spec.auxiliaries)


def test_the_item_index_answers_a_batch_s_state_and_runs_without_the_event_log(tmp_path, monkeypatch):
    from ergostat.spec import itemindex
    from ergostat.spec import items as its
    b, clock, out, cfg = batches_module(monkeypatch, tmp_path)
    three_runs(b, clock, cfg)
    p = project(tmp_path, out)
    first = {i.id: i for i in its.project(p.events, p.model.spec, kind="batch")}
    for ix in list(itemindex._OPEN.values()):                                   # as a process that starts
        ix.close()
    itemindex._OPEN.clear()

    def after(real):
        def read(*a, **k):                              # only what came after the index's last seq (nothing), never
            got = list(real(*a, **k))                   # the record from its start
            assert k.get("after_seq") is not None and not got, (a, k)
            return got
        return read
    for name in ("query", "of_items"):
        monkeypatch.setattr(p.events, name, after(getattr(p.events, name)))
    (it,) = its.project(p.events, p.model.spec, kind="batch")
    assert it.id == "batch/a-20261123T100000Z" and it.state == "partial"
    assert [(r["run"], r["kind"], r["outcome"]) for r in it.fields["runs"]] == [
        (1, "full", "failed"), (2, "halves", "failed"), (3, "halves", "failed")]
    assert it.fields["runs"][1]["passed"] == 14 and it.fields["runs"][1]["failed"] == 1
    assert it.fields == first[it.id].fields


def test_the_timeline_draws_one_bar_per_run_and_the_gaps_link_to_their_batch(tmp_path, monkeypatch):
    from ergostat import precedence
    from ergostat.web.snapshot import build
    b, clock, out, cfg = batches_module(monkeypatch, tmp_path)
    spans = three_runs(b, clock, cfg)
    p = project(tmp_path, out)
    got = precedence.build(p.events, p.model.spec, ["batch"], now=clock[0] + 60, since=out[0][3] - 3600)
    by = {x["id"]: x for x in got["items"]}
    x = by["batch/a-20261123T100000Z"]
    bars = [(t0, t1) for st, t0, t1 in x["segments"] if st == "testing"]
    assert len(bars) == 3 and bars[1:] == spans[1:] and bars[0][1] == spans[0][1]   # (the first from the start)
    assert [s[0] for s in x["segments"]] == ["testing", "isolating", "testing", "isolating", "testing", "pushing"]
    assert x["segments"][-1][1:] == [spans[-1][1], spans[-1][1] + 120]            # (then landed: no bar)
    assert sorted(x["links"]["gaps"]) == ["gap/a", "gap/b", "gap/c"] and "gap/b" in by
    assert by["gap/b"]["inverse"] == {"batches": ["batch/a-20261123T100000Z"]}     # each gap: the batches it was in
    html = build(p)                                                             # the Items page's own answers
    import re
    data = json.loads(re.search(r"window\.SNAPSHOT = (.*?);</script>", html, re.S).group(1))["data"]
    assert "batch" in {k["name"] for k in data["items"]["kinds"]}
    assert "batch/a-20261123T100000Z" in {i["id"] for i in data["items-graph?kinds=batch"]["items"]}


@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")                              # (as tests/test_export.py)
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            b = p.chromium.launch(channel="chrome")
        yield b
        b.close()


def test_the_items_page_draws_the_batch_and_one_timeline_bar_per_run(browser, tmp_path, monkeypatch):
    """The page itself, from a snapshot of it (nothing asked of a server): the kind's list, and its Timeline with the
    batch's row holding one testing bar for each of its three runs."""
    import time

    from ergostat.web.snapshot import build
    b, clock, out, cfg = batches_module(monkeypatch, tmp_path)
    clock[0] = time.time() - 2400                                                # (in the page's window: real times)
    three_runs(b, clock, cfg)
    page = tmp_path / "snapshot.html"
    page.write_text(build(project(tmp_path, out)))
    pg = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith(("file:", "data:", "blob:")) else rt.abort())
    bid = "batch/a-20261123T100000Z"
    pg.goto(f"file://{page}#/items?kind=batch")
    pg.wait_for_function("() => document.querySelectorAll('table.items tr.click').length >= 1", timeout=60000)
    listed = [t.strip() for t in pg.locator("table.items tr.click td:first-child").all_inner_texts()]
    assert listed == [bid], listed                                               # the kind's list
    pg.goto(f"file://{page}#/items?kind=batch&view=timeline")
    pg.wait_for_selector(".rg-timeline[data-drawn]", timeout=60000)
    pg.locator(".rg-check", has_text="Collapse done").locator("input").uncheck()  # (it ended: a finished row, and
    pg.locator(".rg-check", has_text="Frontier").locator("input").uncheck()       # no unfinished one waits on it)
    pg.wait_for_selector(f".rg-timeline[data-drawn] .rg-row[data-id='{bid}'] .rg-seg", timeout=20000)
    bars = pg.locator(f".rg-row[data-id='{bid}'] .rg-seg title").all_text_contents()
    assert [t.split(",")[0] for t in bars] == [f"{bid}: {s}" for s in
                                               ("testing", "isolating", "testing", "isolating", "testing", "pushing")]
    assert not errors, errors
    pg.close()


def test_a_failure_to_say_inside_a_run_still_raises_the_run_s_own_error(tmp_path, monkeypatch):
    b, clock, out, cfg = batches_module(monkeypatch, tmp_path)
    b.begin(cfg, "a-20261123T100000Z", ["gap/a"], "0" * 40)
    monkeypatch.setattr(b, "_say", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))

    class Stalled(Exception):
        pass
    with pytest.raises(Stalled), b.run("full", ["gap/a"]):
        raise Stalled("unit")
    b.end("given-back", "x")                                                     # nothing raised


def test_a_batch_whose_run_was_killed_ends_given_back_when_the_next_run_recovers(tmp_path, monkeypatch):
    b, clock, out, cfg = batches_module(monkeypatch, tmp_path)
    b.begin(cfg, "a-20261123T100000Z", ["gap/a", "gap/b"], "0" * 40)
    killed = b.run("full", ["gap/a", "gap/b"])                                    # under way, then SIGKILLed (kept, so
    killed.__enter__()                                                            # nothing closes it here)
    assert json.loads((tmp_path / "run" / "batch.json").read_text())["under_way"] is True
    later, _, said_later, _ = batches_module(monkeypatch, tmp_path)               # the next queue run's process
    later.abandoned(cfg)
    (event, item, data, _), = said_later
    assert (event, item) == ("batch.ended.given-back", "batch/a-20261123T100000Z") and data["runs_n"] == 1
    assert [x["gap"] for x in data["given_back"]] == ["gap/a", "gap/b"] and "stopped part way" in data["why"]
    later.abandoned(cfg)
    assert len(said_later) == 1                                                   # ended once
    b.begin(cfg, "c-20261123T110000Z", ["gap/c"], "0" * 40)
    b.settled(["gap/c"], "1" * 40, [])
    b.pending()                                                                   # waiting on its push: not abandoned
    later.abandoned(cfg)
    assert len(said_later) == 1


# ---- the run under way: its progress from its own logs

def test_a_run_s_progress_is_read_from_its_logs(tmp_path, monkeypatch):
    b, clock, out, cfg = batches_module(monkeypatch, tmp_path)
    run, logs = tmp_path / "run", tmp_path / "run" / "queue"
    assert b.progress(cfg) == (0, 0)                                              # no queue run
    run.mkdir(exist_ok=True)
    (run / "queue.json").write_text(json.dumps({"running": {"pre": "x"}}))
    import time
    clock[0] = time.time() - 5                                                    # (the logs' own times: real ones)
    b.begin(cfg, "a-20261123T100000Z", ["gap/a"], "0" * 40)
    with b.run("full", ["gap/a"]):
        logs.mkdir(exist_ok=True)
        (logs / "a-20261123T100000Z-ruff.txt").write_text("All checks passed!\n")
        (logs / "a-20261123T100000Z-unit.txt").write_text("..F.....  [ 10%]\n..E.F...  [ 40%]\n")
        (logs / "a-20261123T100000Z-browser.txt").write_text("......  [ 80%]\n")
        (logs / "b-20261123T090000Z-unit.txt").write_text("FFFF  [  5%]\n")      # another batch's
        assert b.progress(cfg) == (40, 3)
        (logs / "a-20261123T100000Z-unit.txt").write_text("..F.....  [ 10%]\n..E.F...  [100%]\n3 failed, 9 passed in 2.00s\n")
        assert b.progress(cfg) == (80, 3)
        (run / "queue.json").write_text("{not json")
        with pytest.raises(ValueError):                                          # unreadable: no value, never 0
            b.progress(cfg)
        (run / "queue.json").write_text(json.dumps({"running": {"pre": "x"}}))
    assert b.progress(cfg) == (0, 0)                                              # the run finished
