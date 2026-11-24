"""The merge queue's host step (dev/bin/queue.py, `[suites] host`): the tests its container skips (the AI repair
sandbox's) run on the Mac, outside any container, as a required suite (dev/records/queue-runs-what-its-container-
skips.md). Each suite here is a fake command: no Docker, no live instance."""

from __future__ import annotations

import importlib.util
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
    # all four red on host; p, q green and r, s red at once; then r red and s green at once. Unit green each time
    assert said.count("gap.queue-failed") == 1 and said.count("gap.merged") == 3
    assert merges(f) == ["p", "q", "s"] and suite_runs(f) == 5 and host_runs(f) == 5
    r = f.item("gap/r")["fields"]
    assert r["failed_suite"] == "host" and r["failed_tests"] == ["tests/test_repair2.py::test_x"]
    assert r["suites_queue"]["host"]["rc"] == 1 and r["suites_queue"]["unit"]["rc"] == 0
    assert f.item("gap/s")["fields"]["suites_queue"]["host"]["rc"] == 0           # in the landed run's outcome too
    assert len(host_logs(f)) == 5                                                 # beside the others, in run/queue
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


def queue_module():
    spec = importlib.util.spec_from_file_location("factory_queue", BIN / "queue.py")   # (not the stdlib's queue)
    q = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(BIN))
    try:
        spec.loader.exec_module(q)
    finally:
        sys.path.remove(str(BIN))
    return q


def test_only_the_stated_external_needs_in_use_are_exempt(tmp_path):
    q = queue_module()
    exempt = ("set ERGOSTAT_TEST_VM_URL to run VictoriaMetrics", "spends money: ERGOSTAT_LIVE_AI=1",
              "no Chromium to drive: gone", "could not import 'playwright.sync_api': No module named 'playwright'",
              "needs Docker and the agent image (dev/agent/Dockerfile)", "no 3 free ports in 9000-9100")
    counted = ("needs curl", "not under Docker", f"{NS} (no playwright either)", "url")
    lines = [f"SKIPPED [1] tests/test_x.py:{i}: {r}" for i, r in enumerate(exempt + counted)]
    unit = tmp_path / "unit.txt"
    unit.write_text("\n".join(lines))
    assert q.nowhere("\n".join(lines), unit) == sorted(f"tests/test_x.py:{i}: {r}"
                                                       for i, r in enumerate(exempt + counted) if r in counted)


def test_a_missing_unit_log_counts_every_host_skip_as_nowhere(tmp_path):
    q = queue_module()
    host = f"SKIPPED [2] tests/test_repair2.py:44: {NS}\nSKIPPED [1] tests/test_x.py:9: spends money: set it\n2 skipped"
    assert q.nowhere(host, tmp_path / "no-such-unit.txt") == [f"tests/test_repair2.py:44: {NS}"]   # (an excused run)


def test_a_triage_rerun_of_the_host_step_that_cannot_start_blames_no_gap(tmp_path):
    import re

    from tests.test_factory import queue_failed
    f, gid = queue_failed(tmp_path)
    db = f.db()
    db["items"][gid]["fields"]["failed_suite"] = "host"
    f.record.write_text(json.dumps(db))
    f.config.write_text(re.sub(r"^rerun = .*$", f'rerun = "{tmp_path / "no-such-suite"} {{tests}}"',   # (the shell's 127)
                               f.config.read_text(), flags=re.M))
    said, _ = f.run("triage.py", gid, fails=True)
    assert "gap.sent-back" not in said and "gap.retried" not in said and "the host rerun did not start" in f.stderr


def test_a_host_step_that_stops_writing_is_stopped_as_a_stall(tmp_path):
    from tests.test_queue import gone, hangs, limited, reaped
    f = Factory(tmp_path, unit=UNIT.format(runs=tmp_path / "runs"))
    with_host(f, host_script(f, hangs(tmp_path)))
    limited(f, stall_minutes=0.05)                                               # 3 s
    approved_gaps(f, {"a": 1, "b": 2}, batch=2)
    start = git(f.checkout, "rev-parse", "main")
    try:
        said, lines = f.run("queue.py", "gap/a", timeout=90)
        assert gone(int((tmp_path / "sleeper").read_text()))                    # its process group stopped
    finally:
        reaped(tmp_path / "group")
    assert said == ["gap.queued", "gap.measured"] and merges(f) == []           # undone; no gap blamed
    assert git(f.checkout, "rev-parse", "main") == start
    nacks = [x["nack"] for x in lines if "nack" in x]
    assert len(nacks) == 1 and nacks[0]["count"] is False and "did not grow" in nacks[0]["why"]
    a = f.item("gap/a")["fields"]
    assert a["stalled"] == "host" and a["stalled_test"] == "tests/test_x.py::test_hangs" and "failed_gates" not in a


def test_a_triage_rerun_of_the_host_step_is_limited_too(tmp_path):
    import re

    from tests.test_factory import queue_failed
    from tests.test_queue import hangs, limited, reaped
    f, gid = queue_failed(tmp_path)
    db = f.db()
    db["items"][gid]["fields"]["failed_suite"] = "host"                          # a host failure, rerun on the Mac
    f.record.write_text(json.dumps(db))
    f.config.write_text(re.sub(r"^rerun = .*$", f'rerun = "{hangs(tmp_path)}"', f.config.read_text(), flags=re.M)
                        .replace("queue_container = false", "queue_container = true"))   # (boxed: no Docker here)
    limited(f, stall_minutes=0.05)
    try:
        said, lines = f.run("triage.py", gid, timeout=90)
    finally:
        reaped(tmp_path / "group")
    assert said == ["gap.measured"] and f.item(gid)["fields"]["stalled"] == "rerun"
    assert [x["nack"]["count"] for x in lines if "nack" in x] == [False]


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
    assert boxes["host"] == "host" and {boxes[n] for n in ("ruff", "unit", "browser", "demo")} == {"queue"}
    assert [n for n, _ in out["seen"]].index("host") > [n for n, _ in out["seen"]].index("unit")
    assert "host" in out["got"]


def test_the_shipped_suites_name_their_failures_and_their_skips():
    # -r replaces pytest's default report chars (fE): without f and E a failing run prints no FAILED line, which is
    # all fac.failed_tests reads; without s the host step's check cannot name a skip
    import re
    import tomllib

    from tests.test_factory import ROOT
    s = tomllib.loads((ROOT / "dev" / "factory.toml").read_text())["suites"]
    for name in ("unit", "build", "host"):
        chars = re.findall(r"\s-r(\w+)", s[name])
        assert chars and all(set("fEs") <= set(c) for c in chars), (name, chars)
