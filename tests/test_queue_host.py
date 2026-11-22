"""The merge queue's host step (dev/bin/queue.py, `[suites] host`): the tests its container skips (the AI repair
sandbox's) run on the Mac, outside any container, as a required suite (dev/records/queue-runs-what-its-container-
skips.md). Each suite here is a fake command: no Docker, no live instance."""

from __future__ import annotations

import json
import subprocess
import sys

from tests.test_factory import BIN, Factory, approved_gaps, git, merges, suite_runs

UNIT = "echo run >> {runs}"
NS = "bwrap cannot make its namespaces here"


def with_host(f: Factory, host: str, **more: str) -> Factory:
    text = f.config.read_text().replace('demo = "true"', f'demo = "true"\nhost = "{host}"')
    for k, v in more.items():
        text = text.replace(k, v)
    f.config.write_text(text)
    return f


def host_logs(f: Factory) -> list[str]:
    q = f.model / "run" / "queue"
    return sorted(p.name for p in q.glob("*-host.txt")) if q.exists() else []


def host_script(f: Factory, body: str) -> str:
    (f.tmp / "host.sh").write_text(f"echo run >> {f.tmp}/host-runs\n{body}\n")
    return f"sh {f.tmp / 'host.sh'}"


def host_runs(f: Factory) -> int:
    p = f.tmp / "host-runs"
    return len(p.read_text().splitlines()) if p.exists() else 0


def test_a_failing_host_step_fails_the_batch_and_bisects(tmp_path):
    f = Factory(tmp_path, unit=UNIT.format(runs=tmp_path / "runs"))
    with_host(f, host_script(f, "if [ -e bad.txt ]; then echo 'FAILED tests/test_repair2.py::test_x - boom'; exit 1; fi"))
    approved_gaps(f, {"p": 1, "q": 2, "r": 3, "s": 4}, bad="r", batch=4)
    said, _ = f.run("queue.py", "gap/p")
    # all four red on host; p, q green; p, q, r red: r. Then s onto p, q: green. Unit green each time
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 3
    assert merges(f) == ["p", "q", "s"] and suite_runs(f) == 4 and host_runs(f) == 4
    r = f.item("gap/r")["fields"]
    assert r["failed_suite"] == "host" and r["failed_tests"] == ["tests/test_repair2.py::test_x"]
    assert r["suites_queue"]["host"]["rc"] == 1 and r["suites_queue"]["unit"]["rc"] == 0
    assert f.item("gap/s")["fields"]["suites_queue"]["host"]["rc"] == 0           # in the landed run's outcome too
    assert len(host_logs(f)) == 4                                                 # beside the others, in run/queue
    # flake triage reruns the host's tests on the Mac too: with the container on, the rerun still runs unboxed
    # (boxed, it would need Docker, which this test does not have, and the rerun would never run)
    (tmp_path / "rerun.sh").write_text(f'echo "$*" >> {tmp_path}/reruns\necho "FAILED $1 - boom"\nexit 1\n')
    f.config.write_text(f.config.read_text().replace('rerun = "echo again {tests}"',
                                                     f'rerun = "sh {tmp_path / "rerun.sh"} {{tests}}"')
                        .replace("queue_container = false", "queue_container = true"))
    said, _ = f.run("triage.py", "gap/r")
    assert said == ["gap.sent-back"] and (tmp_path / "reruns").read_text().startswith("tests/test_repair2.py::test_x")


def test_an_empty_host_skips_the_step(tmp_path):
    for n, host in enumerate(("", "  ", None)):                                 # empty, blank, or not set at all
        f = Factory(tmp_path / str(n), unit=UNIT.format(runs=tmp_path / str(n) / "runs"))
        if host is not None:
            with_host(f, host)
        approved_gaps(f, {"a": 1})
        said, _ = f.run("queue.py", "gap/a")
        assert said == ["gap.queued", "gap.merged", "gap.push-asked"]
        assert "host" not in f.item("gap/a")["fields"]["suites_queue"] and host_logs(f) == []


def test_a_host_step_that_cannot_start_is_not_read_as_passing(tmp_path):
    (tmp_path / "not-runnable.sh").write_text("exit 0\n")                      # (no x bit: the shell's 126)
    for n, host in enumerate((str(tmp_path / "no-such-suite"), str(tmp_path / "not-runnable.sh"))):
        f = Factory(tmp_path / str(n), unit=UNIT.format(runs=tmp_path / str(n) / "runs"))
        with_host(f, host)
        approved_gaps(f, {"a": 1})
        start = git(f.checkout, "rev-parse", "main")
        said, _ = f.run("queue.py", "gap/a", fails=True)
        assert "gap.merged" not in said and "gap.queue-failed" not in said        # never green, and no gap blamed
        assert "the host suite did not start" in f.stderr
        assert git(f.checkout, "rev-parse", "main") == start                      # the merge undone
        assert f.item("gap/a")["state"] != "merged"


def test_a_test_skipped_in_both_places_fails_the_run(tmp_path):
    skip = f"echo 'SKIPPED [2] tests/test_repair2.py:44: {NS}'; echo '2 skipped'"
    f = Factory(tmp_path / "both", unit=f"echo run >> {tmp_path}/runs; {skip}")
    with_host(f, host_script(f, skip))                                           # the Mac cannot make it either
    approved_gaps(f, {"a": 1})
    said, _ = f.run("queue.py", "gap/a")
    assert said == ["gap.queued", "gap.queue-failed", "gap.measured"]
    got = f.item("gap/a")["fields"]
    assert got["failed_suite"] == "host" and got["suites_queue"]["host"]["nowhere"] == [f"tests/test_repair2.py:44: {NS}"]
    # skipped in the container only: the Mac ran it, green
    g = Factory(tmp_path / "one", unit=f"echo run >> {tmp_path}/runs; {skip}")
    with_host(g, host_script(g, "echo '3 passed'"))
    approved_gaps(g, {"a": 1})
    assert g.run("queue.py", "gap/a")[0] == ["gap.queued", "gap.merged", "gap.push-asked"]
    # a stated external need, skipped in both: unaffected
    url = "echo 'SKIPPED [1] tests/test_store_conformance.py:303: set ERGOSTAT_TEST_VM_URL to run it'; echo '1 skipped'"
    h = Factory(tmp_path / "url", unit=f"echo run >> {tmp_path}/runs; {url}")
    with_host(h, host_script(h, url))
    approved_gaps(h, {"a": 1})
    assert h.run("queue.py", "gap/a")[0] == ["gap.queued", "gap.merged", "gap.push-asked"]


def test_skips_that_cannot_be_compared_count_as_nowhere(tmp_path):
    named = f"echo 'SKIPPED [2] tests/test_repair2.py:44: {NS}'; echo '2 skipped'"
    for n, (unit, host) in enumerate((("echo '2 skipped'", named),                # the unit run names no skip (no -rs)
                                      ("echo '9 passed'", "echo '2 skipped'"))):  # the host's own skips unnamed
        f = Factory(tmp_path / str(n), unit=f"echo run >> {tmp_path}/runs; {unit}")
        with_host(f, host_script(f, host))
        approved_gaps(f, {"a": 1})
        said, _ = f.run("queue.py", "gap/a")
        assert said == ["gap.queued", "gap.queue-failed", "gap.measured"], n
        assert f.item("gap/a")["fields"]["suites_queue"]["host"]["nowhere"], n


def test_the_host_step_is_never_boxed(tmp_path):
    f = with_host(Factory(tmp_path), "true", **{"queue_container = false": "queue_container = true"})
    code = ("import sys, json, pathlib; sys.path[:0] = [sys.argv[1]]; import fac, queue\n"
            "seen = []\n"
            "def suite(cfg, name, cwd, log, slot=True, command=None, quarantined=(), box='', **fmt):\n"
            "    seen.append([name, box]); log.write_text(''); return 0, 0.0\n"
            "fac.suite = suite; cfg = fac.config(); logs = pathlib.Path(sys.argv[2])\n"
            "got = queue.suites(cfg, fac.path(cfg, 'checkout'), 't', logs, 'HEAD')\n"
            "print(json.dumps({'seen': seen, 'got': sorted(got)}))")
    r = subprocess.run([sys.executable, "-c", code, str(BIN), str(tmp_path)], cwd=f.model, env=f.env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.splitlines()[-1])
    boxes = dict(out["seen"])
    assert boxes["host"] == "" and {boxes[n] for n in ("ruff", "unit", "browser", "demo")} == {"queue"}
    assert [n for n, _ in out["seen"]].index("host") > [n for n, _ in out["seen"]].index("unit")
    assert "host" in out["got"]
