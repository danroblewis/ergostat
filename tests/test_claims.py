"""Claims (SPEC §12g): a block says what it did, and ergostat checks it against the record and the world, never
taking the block's word. The case from this project's history first: tests piped through ``tail`` hide their
failing exit code, the run exits 0, and the block claims they pass. Running the declared test command catches it."""

import json
import os
import subprocess
import sys
import textwrap
import time

import pytest

from ergostat import model as mdl
from ergostat.claims import checks, record, trust
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = sys.executable
FAILING = "def test_it():\n    assert 1 + 1 == 3\n"
PASSING = "def test_it():\n    assert 1 + 1 == 2\n"


def project(tmp_path, blocks: str, extra: str = "") -> Project:
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        stocks:
          todo:
            sensor: {manual: true}
        flows:
          done:
            from: todo
        """) + textwrap.dedent(extra) + "blocks:\n" + textwrap.indent(textwrap.dedent(blocks), "  "))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    assert not errors, errors
    return Project(m)


def run(p: Project, name: str) -> list[dict]:
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks[name], "schedule")
    ran = p.events.query(n=1, type="agent.ran,agent.failed", item=name)[-1]
    return record.of_run(p, ran["causedby"])


def write_block(tmp_path, name: str, script: str) -> str:
    (tmp_path / name).write_text(script)
    return f"sh {name}"


TESTS = f"""
claims:
  tests:
    run: {PY} -m pytest -q -p no:cacheprovider test_x.py
    timeout: 2m
"""


def test_a_pipe_that_hid_a_failing_exit_code_is_caught_by_running_the_declared_tests(tmp_path):
    """The pattern exactly: the block runs pytest through tail (the pipe's exit code is tail's, 0), then claims the
    tests pass. Its run exits 0, so the exit code alone is fooled; the declared test command, run by ergostat, is not."""
    (tmp_path / "test_x.py").write_text(FAILING)
    cmd = write_block(tmp_path, "ci.sh", textwrap.dedent(f"""\
        {PY} -m pytest -q -p no:cacheprovider test_x.py | tail -n 3
        echo '{{"claim": {{"says": "tests pass"}}}}'
        echo '{{"claim": {{"says": "the command succeeded", "check": "exit"}}}}'
        echo '{{"out": "flow.done", "moved": 1}}'
        """))
    p = project(tmp_path, f"ci:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", TESTS)
    got = {c["says"]: c for c in run(p, "ci")}
    ran = p.events.query(n=1, type="agent.ran", item="ci")[-1]
    assert ran["data"]["exit"] == 0, "the pipe hid the failure: the run itself exited 0"
    assert got["the command succeeded"]["state"] == "verified", "the exit code says success: the pipe fooled it"
    tests = got["tests pass"]
    assert tests["state"] == "contradicted"
    assert tests["kind"] == "tests"
    assert tests["evidence"]["exit"] != 0 and "failed" in tests["evidence"]["output"]
    assert "pytest" in tests["evidence"]["command"]
    assert p.events.query(type="ergostat.claim.contradicted", item=tests["id"])[-1]["source"] == "ergostat"


def test_tests_that_pass_verify_the_claim(tmp_path):
    (tmp_path / "test_x.py").write_text(PASSING)
    cmd = write_block(tmp_path, "ci.sh", f"{PY} -m pytest -q -p no:cacheprovider test_x.py | tail -n 3\n"
                                         "echo '{\"claim\": {\"says\": \"all tests pass\"}}'\necho 1\n")
    p = project(tmp_path, f"ci:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", TESTS)
    [c] = run(p, "ci")
    assert c["state"] == "verified" and c["evidence"]["exit"] == 0


def test_a_claim_no_check_knows_is_unchecked_not_trusted(tmp_path):
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"says\": \"made it better\"}}'\n"
                                        "echo '{\"claim\": {\"says\": \"it is fine\", \"check\": \"vibes\"}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n")
    a, b = run(p, "w")
    assert a["state"] == b["state"] == "unchecked"
    assert "no check knows" in a["why"] and "no check named vibes" in b["why"]
    assert trust.measure(p, "ergostat.trust.unchecked@w") == 2
    assert trust.measure(p, "ergostat.trust.contradicted@w") == 0.0     # nothing checked: nothing contradicted


def test_a_claim_line_that_says_nothing_is_refused(tmp_path):
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"about\": \"stock.todo\"}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n")
    assert run(p, "w") == []
    assert "says what was done" in p.events.query(type="agent.refused", item="w")[-1]["data"]["why"]


ITEMS = """
projections:
  job:
    query: key.startswith('job/')
    fields:
      state:
        type: one of [waiting, running, done]
    events:
      job-started:
        when: type == 'job.started'
        '...': data
        state: set('running')
      job-finished:
        when: type == 'job.finished'
        '...': data
        state: set('done')
      other:
        when: true
        '...': data
"""


def test_an_item_moved_to_a_state_is_checked_by_folding_it(tmp_path):
    cmd = write_block(tmp_path, "w.sh", textwrap.dedent("""\
        echo '{"event": "job.started", "item": "job/1"}'
        echo '{"event": "job.finished", "item": "job/1"}'
        echo '{"event": "job.started", "item": "job/2"}'
        echo '{"claim": {"says": "job/1 is done", "about": "job/1"}}'
        echo '{"claim": {"says": "finished job/2", "about": "job/2", "check": {"state": "done"}}}'
        echo '{"claim": {"says": "finished job/3", "about": {"item": "job/3"}, "check": {"state": "done"}}}'
        echo 1
        """))
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", ITEMS)
    one, two, three = run(p, "w")
    assert one["kind"] == "state" and one["state"] == "verified"     # the state named in what it says
    assert two["state"] == "contradicted" and two["evidence"]["state"] == "running"
    assert three["state"] == "contradicted" and "nothing is recorded" in three["why"]
    assert trust.measure(p, "ergostat.trust.contradicted@w") == pytest.approx(2 / 3)
    assert trust.measure(p, "ergostat.trust.contradictions@rung:program") == 2


def test_a_file_changed_is_checked_in_git(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for f in ("a.txt", "b.txt"):
        (tmp_path / f).write_text("x\n")
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run([*g, "add", "-A"], cwd=tmp_path, check=True)
    an_hour_ago = {**os.environ, "GIT_COMMITTER_DATE": f"{int(time.time()) - 3600} +0000"}
    subprocess.run([*g, "commit", "-qm", "first"], cwd=tmp_path, check=True, env=an_hour_ago)
    cmd = write_block(tmp_path, "w.sh", textwrap.dedent("""\
        echo y >> a.txt
        echo '{"claim": {"says": "changed a.txt", "about": "a.txt"}}'
        echo '{"claim": {"says": "edited b.txt", "about": {"file": "b.txt"}}}'
        echo 1
        """))
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n")
    a, b = run(p, "w")
    assert a["kind"] == "changed" and a["state"] == "verified" and a["evidence"]["uncommitted"]
    assert b["state"] == "contradicted"


def test_a_level_reached_is_checked_against_the_reading(tmp_path):
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"says\": \"todo is down to 3\", \"about\": \"stock.todo\", "
                                        "\"check\": {\"level\": \"<= 3\"}}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n")
    p.measurements.add("sensor/todo.main", 7)
    [c] = run(p, "w")
    assert c["state"] == "contradicted" and c["evidence"]["value"] == 7
    p.measurements.add("sensor/todo.main", 2)
    [c] = run(p, "w")
    assert c["state"] == "verified"


def test_without_a_test_command_the_latest_test_run_in_the_record_decides(tmp_path):
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"says\": \"tests pass\"}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n")
    [c] = run(p, "w")
    assert c["state"] == "unchecked" and "no test command" in c["why"]
    p.events.add("tests.ran", item="ci/1", source="ci", data={"exit": 2})
    [c] = run(p, "w")
    assert c["state"] == "contradicted"
    p.events.add("tests.passed", item="ci/2", source="ci")
    [c] = run(p, "w")
    assert c["state"] == "verified"


def test_tests_run_at_the_commit_an_item_names_and_a_claims_own_command_is_never_run(tmp_path):
    """A claim about an item whose ``branch`` (or ``commit``) field names a revision is checked on a copy of that
    revision, from the repository the test command's ``in:`` names; the working tree is left alone."""
    repo = tmp_path / "product"
    repo.mkdir()
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=main"]
    subprocess.run([*g, "init", "-q"], cwd=repo, check=True)
    (repo / "test_x.py").write_text(PASSING)
    subprocess.run([*g, "add", "-A"], cwd=repo, check=True)
    subprocess.run([*g, "commit", "-qm", "good"], cwd=repo, check=True)
    subprocess.run([*g, "checkout", "-qb", "change-1"], cwd=repo, check=True)
    (repo / "test_x.py").write_text(FAILING)
    subprocess.run([*g, "commit", "-qam", "broken"], cwd=repo, check=True)
    subprocess.run([*g, "checkout", "-q", "main"], cwd=repo, check=True)
    extra = ITEMS + f"""
claims:
  tests:
    run: {PY} -m pytest -q -p no:cacheprovider test_x.py
    in: product
"""
    cmd = write_block(tmp_path, "w.sh", textwrap.dedent("""\
        echo '{"event": "job.started", "item": "job/1", "data": {"branch": "change-1"}}'
        echo '{"claim": {"says": "tests pass", "about": "job/1", "check": {"kind": "tests", "run": "true"}}}'
        echo '{"claim": {"says": "tests pass", "about": {"dir": "product"}}}'
        echo 1
        """))
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", extra)
    at_branch, here = run(p, "w")
    assert at_branch["state"] == "contradicted" and at_branch["evidence"]["from"] == "job/1's branch"
    assert "not_run" in at_branch["evidence"]
    assert here["state"] == "verified"                       # main, in the folder: the good one
    assert (repo / "test_x.py").read_text() == PASSING       # nothing was checked out


def test_a_contradicted_claim_is_a_finding_and_needs_attention(tmp_path):
    from ergostat import state
    from ergostat.spec import watch
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"says\": \"finished job/9\", \"about\": \"job/9\", "
                                        "\"check\": {\"state\": \"done\"}}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", ITEMS)
    run(p, "w")
    found = [f for f in watch.find(p, p.model.spec) if f.code == "contradicted-claim"]
    assert found and found[0].about == "block.w" and "finished job/9" in found[0].message
    att = state.attention(state.snapshot(p), running=False, model=p.model)
    assert any(a["what"] == "agent w" and "contradicted" in a["says"] for a in att)
    t = trust.table(p)
    row = next(r for r in t["rows"] if r["by"] == "block" and r["name"] == "w")
    assert row["contradicted"] == 1 and row["contradicted_share"] == 1.0
    assert t["contradicted"][0]["says"] == "finished job/9"


def test_the_kind_is_built_in_and_trust_is_a_measure_a_sensor_reads(tmp_path):
    from ergostat.numbers import measures
    from ergostat.spec import items
    extra = """
auxiliaries:
  w-honesty:
    sensor: {builtin: "ergostat.trust.contradicted@w"}
goals:
  w-honest:
    auxiliary: w-honesty
    hold: "<= 0.1"
"""
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"says\": \"the command succeeded\", \"check\": \"exit\"}}'\n"
                                        "exit 3\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", extra)
    spec = p.model.spec
    assert "ergostat.claim" in spec.items
    s = spec.auxiliaries["w-honesty"].sensors["main"]
    assert s.builtin == "ergostat.trust.contradicted@w" and "measure" in s.run
    [c] = run(p, "w")
    assert c["state"] == "contradicted" and c["evidence"]["exit"] == 3
    assert measures.measure(p, "trust.contradicted@w") == 1.0
    listed = items.listing(p.events, spec, kind="ergostat.claim")
    assert listed["items"][0]["state"] == "contradicted"
    assert listed["items"][0]["fields"]["evidence"]["exit"] == 3


def test_claims_section_is_checked(tmp_path):
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        claims:
          state: {run: "true"}
          lint: {says: "(", run: ruff check .}
          docs: {in: /etc}
          site: {in: /etc, run: "true"}
        """))
    from ergostat import spec
    _, problems = spec.read(tmp_path / "ergostat.yaml")
    msgs = [x.message for x in problems if x.level == "error"]
    assert any("built-in check" in m for m in msgs)
    assert any("a pattern" in m for m in msgs)
    assert any("run:" in m for m in msgs)
    assert any("inside the model's" in m for m in msgs)


def test_a_check_the_project_declares_is_its_own_kind_of_claim(tmp_path):
    extra = """
claims:
  lint:
    says: "lint (is )?clean"
    run: test ! -e dirty
"""
    cmd = write_block(tmp_path, "w.sh", "touch dirty\necho '{\"claim\": {\"says\": \"lint is clean\"}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", extra)
    [c] = run(p, "w")
    assert c["kind"] == "lint" and c["state"] == "contradicted"
    (tmp_path / "dirty").unlink()
    assert checks.check(p, p.model.spec, {**c, "id": c["id"]})["state"] == "verified"


def test_the_cli_the_mcp_tool_and_the_page_show_the_verdicts_and_trust(tmp_path, capsys):
    from urllib.parse import quote

    from ergostat.cli import main
    from ergostat.mcp import Server
    from ergostat.web.server import Live, api
    cmd = write_block(tmp_path, "w.sh", "echo '{\"claim\": {\"says\": \"finished job/9\", \"about\": \"job/9\", "
                                        "\"check\": {\"state\": \"done\"}}}'\n"
                                        "echo '{\"claim\": {\"says\": \"the command succeeded\"}}'\necho 1\n")
    p = project(tmp_path, f"w:\n  type: program\n  run: {cmd}\n  every: 1h\n  out: flow.done\n", ITEMS)
    bad, good = run(p, "w")
    assert main(["-C", str(tmp_path), "claims"]) == 0
    out = capsys.readouterr().out
    assert "developer" not in out and "w" in out and "50%" in out and "finished job/9" in out
    assert main(["-C", str(tmp_path), "claims", bad["id"].split("/")[1]]) == 0
    assert "job/9" in capsys.readouterr().out
    got = json.loads(Server(tmp_path).call("trust", {})["content"][0]["text"])
    assert got["all"]["contradicted"] == 1 and got["all"]["verified"] == 1
    t = api(Live(p), "trust", {})
    assert next(r for r in t["rows"] if r["who"] == "w")["contradicted_share"] == 0.5
    d = api(Live(p), "items/" + quote(bad["id"], safe=""), {})
    assert d["state"] == "contradicted" and "job/9" in d["fields"]["why"]


def test_claims_left_unchecked_are_checked_again(tmp_path):
    p = project(tmp_path, "w:\n  type: program\n  run: echo 1\n  every: 1h\n  out: flow.done\n", ITEMS)
    c = record.made(p, p.model.spec, "w", {"says": "finished job/1", "about": "job/1", "check": {"state": "done"}})
    assert [x["id"] for x in checks.pending(p, p.model.spec)] == [c["id"]]
    p.events.add("job.finished", item="job/1", source="w")
    [done] = checks.check_all(p, p.model.spec, checks.pending(p, p.model.spec))
    assert done["state"] == "verified" and not checks.pending(p, p.model.spec)
