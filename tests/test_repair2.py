"""The repair loop (SPEC §12r): triage into ``ergostat.failure`` items; the fix made by an AI with no tools in a
disposable clone, tested in ``ergostat.sandbox``, proposed as the gated ``apply-fix`` with its impact report; the
ladder's first two rungs (a person; an AI approver with its approval record); and the gates' findings (X1, X2, M1-M8)."""

import hashlib
import http.server
import json
import os
import re
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import sandbox
from ergostat.actions import gate
from ergostat.actions import record as actions
from ergostat.repair import FAILURE, fix
from ergostat.spec import items as its
from ergostat.spec.engine import Engine
from ergostat.store import Project

PY = sys.executable
LINUX = sys.platform.startswith("linux")
# What a read the sandbox refuses raises: macOS's seatbelt denies it; Linux's bwrap starts from an empty root, where
# the path is not there at all
DENIED = "denied FileNotFoundError" if LINUX else "denied PermissionError"


def _no_sandbox() -> str | None:
    if sandbox.backend() is None:
        return "no OS sandbox here"
    if sandbox.backend() == "bwrap" and subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "true"],
                                                       capture_output=True).returncode:
        return "bwrap cannot make its namespaces here (in the dev container: scripts/in_container.sh --sandbox)"
    return None


_WHY = _no_sandbox()
pytestmark = pytest.mark.skipif(_WHY is not None, reason=_WHY or "")

MODEL = """\
name: repair-demo
items:
  issue: {{id: issue/*, states: [open, closed], on: {{issue.seen: open, issue.closed: closed}}}}
stocks:
  open-issues: {{unit: issues, cumulative: true, sensor: {{items: issue, state: open, every: 1h}}}}
flows:
  issues-found: {{to: open-issues, sensor: {{items: issue, entering: open, over: 10m}}}}
blocks:
  collector:
    type: program
    run: {run}
    read-only: {read_only}
{extra}    every: 1h
    out: flow.issues-found
uses:
  repair:
    use: repair
    with: {{count-every: 1h, approver: {approver}{with_}}}
"""
BROKEN = """\
import json
import os
answer = json.loads(open("answer.json").read())
for issue in answer["issues"]:
    print(json.dumps({"event": "issue.seen", "item": f"issue/{issue['key']}"}))
"""
FIXED = BROKEN.replace('["issues"]', '["values"]').replace("issue['key']", "issue['id']")
FAKE = r'''
import json, pathlib, sys
prompt = sys.stdin.read()
with open({log!r}, "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "prompt": prompt}}) + "\n")
ans = {fix!r} if prompt.startswith("You repair") else {review!r}
print(json.dumps({{"type": "result", "total_cost_usd": 0.01, "usage": {{"input_tokens": 100, "output_tokens": 50}},
                  "result": ans if isinstance(ans, str) else json.dumps(ans)}}))
'''


@pytest.fixture(autouse=True)
def _quick(monkeypatch):
    monkeypatch.setenv("ERGOSTAT_IMPACT_SECONDS", "3")
    yield
    from ergostat import runner
    runner.STOPPING.clear()


def git(*args, cwd) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def project(tmp_path, monkeypatch, program=FIXED, review=None, collect=BROKEN, approver="person", read_only="true",
            extra="", with_="", files=None, run="python3 collect.py") -> tuple[Project, Engine]:
    """A project in a repository of its own, its collector broken by a tracker's new answer, and a stand-in AI."""
    from ergostat import runner
    runner.STOPPING.clear()                                  # (an engine closed before stops every run: not this one's)
    d = tmp_path / "proj"
    d.mkdir(parents=True)
    (d / "ergostat.yaml").write_text(MODEL.format(run=run, read_only=read_only, extra=extra, approver=approver, with_=with_))
    (d / "collect.py").write_text(collect)
    (d / "answer.json").write_text(json.dumps({"values": [{"id": "DEMO-1"}], "apiVersion": 3}))
    (d / "notes.txt").write_text("the tracker moved to v3")
    (d / ".env").write_text("TOKEN=dot-file-secret-1234")
    for k, v in (files or {}).items():
        (d / k).write_text(v)
    git("init", "-q", "-b", "main", cwd=d)
    git("add", "-A", cwd=d)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "start", cwd=d)
    (d / "untracked.txt").write_text("never committed: untracked-secret-5678")
    fake = tmp_path / "fake_ai.py"
    answer = {"explanation": "the tracker answers in v3", "program": program} if isinstance(program, str) else program
    fake.write_text(FAKE.format(log=str(tmp_path / "ai.jsonl"), fix=answer,
                                review=review if review is not None else {"approve": True, "reasons": ["small, tested"]}))
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {fake}")
    m = mdl.load(d)
    assert not [x for x in m.problems if x.level == "error"], [str(x) for x in m.problems]
    p = Project(m)
    return p, Engine(p, say=lambda s: None)


def calls(tmp_path) -> list[dict]:
    f = tmp_path / "ai.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


def failures(p) -> list:
    return its.project(p.events, p.model.spec, FAILURE)


def one(p, fid):
    return its.one(p.events, p.model.spec, fid)


def broken(p, e) -> str:
    e.run_block(p.model.spec.blocks["collector"], "test")
    got = failures(p)
    assert len(got) == 1, got
    return got[0].id


def fixed(p, e, fid) -> object:
    e.run_block(p.model.spec.blocks["repair-fix"], "test")
    return one(p, fid)


def tree(d: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(d.rglob("*")):
        if f.is_file():
            h.update(str(f).encode() + f.read_bytes())
    return h.hexdigest()


# ---- triage


def test_a_failed_run_is_triaged_into_one_failure_a_signature_and_counted(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    try:
        fid = broken(p, e)
        e.run_block(p.model.spec.blocks["collector"], "test")
    finally:
        e.close()
    it = one(p, fid)
    f = it.fields
    assert fid.startswith(f"{FAILURE}/collector-") and it.state == "open" and f["count"] == 2
    assert f["traceback"]["type"] == "KeyError" and f["traceback"]["file"] == "collect.py" and f["program"] == "collect.py"
    assert "KeyError: 'issues'" in f["stderr"] and f["read_only"] is True and f["block"] == "collector"
    assert (p.dir / "repair" / f"{fid.split('/')[1]}.input").is_file()


def test_a_timeout_or_a_failure_with_no_program_is_noted_not_opened(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, collect="import time\ntime.sleep(5)\n", extra="    timeout: 0.5s\n")
    try:
        fid = broken(p, e)
    finally:
        e.close()
    assert one(p, fid).state == "noted", "a timeout is not the code's to fix"
    p, e = project(tmp_path / "b", monkeypatch, run="exit 3")
    try:
        fid = broken(p, e)
    finally:
        e.close()
    assert one(p, fid).state == "noted" and one(p, fid).fields["program"] is None


def test_the_repair_loops_own_runs_record_no_failures(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    spec = p.model.spec
    try:
        monkeypatch.setattr(e.spec.blocks["repair-settle"], "params", {**spec.blocks["repair-settle"].params, "run": "exit 1"})
        e.run_block(e.spec.blocks["repair-settle"], "test")
        assert p.events.query(n=1, item="repair-settle", type="agent.failed")
        assert not p.events.query(n=None, type="ergostat.run.failed"), "the loop's own block"
        cause = p.events.add(f"{FAILURE}.opened", item=f"{FAILURE}/x-00000000", source="ergostat")
        e.run_block(spec.blocks["collector"], "test", cause=cause["id"])
        assert not p.events.query(n=None, type="ergostat.run.failed"), "a run a failure's event caused"
    finally:
        e.close()


def test_m1_a_failures_fields_cannot_be_spoofed_by_any_event_not_ergostats(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    try:
        fid = broken(p, e)
    finally:
        e.close()
    for src in ("collector", "owner", "push", "sensor"):            # whatever the way in, a type not ergostat's own
        p.events.add("issue.note", item=fid, source=src, data={"block": "repair-fix", "program": "../../evil.py",
                                                                   "fix": "0" * 40, "state": "applied"})
    it = one(p, fid)
    assert it.fields["block"] == "collector" and it.fields["program"] == "collect.py" and "fix" not in it.fields
    assert it.state == "open" and len(it.refused) == 4
    from ergostat.numbers import impact
    assert impact.resolve(p, p.model.spec, [fid])["block"] == "collector"
    assert one(p, f"{FAILURE}/made-up-00000000") is None or one(p, f"{FAILURE}/made-up-00000000").fields == {}


def test_use_repair_is_a_system_in_all_three_views(tmp_path, monkeypatch):
    from ergostat.blockdiagram import diagram
    from ergostat.process import kinds_of
    p, e = project(tmp_path, monkeypatch)
    e.close()
    spec = p.model.spec
    assert all(spec.stocks[n].system == "repair" for n in ("open-failures", "fixing", "awaiting-approval", "applied-fixes"))
    for g in ("no-open-failures", "fixes-answered"):
        assert spec.loop(g).actuators or spec.loop(g).through, f"{g}: a loop closes it"
    b = spec.blocks["repair-fix"]
    assert (b.type, b.params["model"], b.takes.kind) == ("ai", "haiku", FAILURE), "its rung shown: ai, on haiku"
    assert spec.actions["apply-fix"].gate == "approve"
    drawn = {n["id"] for n in diagram(p.model, None, None, "repair")["nodes"]}
    assert {"blk:repair-fix", "blk:repair-settle"} <= drawn
    assert kinds_of(spec, "repair") == [FAILURE]


# ---- the loop, end to end


def test_the_loop_fixes_in_a_clone_proposes_with_an_impact_report_and_the_person_approves(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    spec, root = p.model.spec, p.model.path.parent
    base = git("rev-parse", "HEAD", cwd=root)
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
        assert it.state == "awaiting-approval", (it.state, it.fields.get("test"))
        assert (root / "collect.py").read_text() == BROKEN, "nothing reaches the project before it is approved"
        f = it.fields
        assert f["tests"] == "passed" and f["test"]["how"] == "exited 0 on the input that failed, in the sandbox" and f["base"] == base
        assert '+for issue in answer["values"]:' in f["diff"] and f["explanation"] == "the tracker answers in v3"
        assert f["impact"]["said"] and f["risk"] in ("low", "medium", "high")
        assert (p.dir / f["report"][5:]).is_file()
        held = actions.about(p, fid)
        assert [(a["action"], a["state"]) for a in held] == [("apply-fix", "requested")], "held for the person"
        from ergostat.inbox import entries
        why = [x["why"] for x in entries.entries(p, spec) if x["kind"] == "action"][0]
        assert why.startswith("Approving merges this code into your repository; it then runs with your rights, outside "
                              "the sandbox. Diff: /item/" + fid) and "exited 0 on the input that failed, in the sandbox" in why
        assert "passed" not in why
        ran = p.events.query(n=1, item="repair-fix", type="agent.ran")[0]["data"]
        assert ran["ai"]["cost_usd"] == pytest.approx(0.01), "the AI call's cost is the run's"
        gate.approve(p, spec, held[0]["id"])                    # the person, from the inbox
        assert one(p, fid).state == "applied", actions.about(p, fid)[0]
        assert (root / "collect.py").read_text() == FIXED and git("rev-parse", "HEAD", cwd=root) == f["fix"]
        assert git("rev-parse", "HEAD~1", cwd=root) == base and not (p.dir / "repair" / fid.split("/")[1]).exists()
        e.run_block(spec.blocks["collector"], "test")
        assert p.events.query(n=1, item="collector", type="agent.ran"), "the collector works again"
    finally:
        e.close()
    moved = [x["type"].rsplit(".", 1)[1] for x in p.events.query(n=None, item=fid) if x["type"].startswith(FAILURE)]
    assert moved == ["opened", "passed", "applied"], moved


def test_a_fix_that_fails_its_test_is_given_back_and_nothing_is_asked(tmp_path, monkeypatch):
    half = BROKEN.replace('["issues"]', '["values"]')                     # half a fix: the key moved too
    p, e = project(tmp_path, monkeypatch, program=half, with_=", tries: 2")
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
        assert it.state == "open" and it.fields["tests"] == "failed" and "KeyError: 'key'" in it.fields["test"]["stderr"]
        assert not actions.about(p, fid)
        assert "last_test" in calls(tmp_path)[-1]["prompt"]
        e.dispatch.due_now.clear()
        p.events.add("ergostat.lease.nudge", item="x/y", source="ergostat")
        it = fixed(p, e, fid)
    finally:
        e.close()
    assert it.state == "dead", "a dead letter after its tries"
    assert '"last_test": {' in calls(tmp_path)[-1]["prompt"], "the fixer is told what its last fix did"


# ---- X1: the owner's git


def test_x1_the_clone_has_its_own_git_and_a_repair_cannot_write_the_owners(tmp_path, monkeypatch):
    attack = FIXED + textwrap.dedent("""
        import os, pathlib
        for t in ("../../.git/config", os.environ.get("OWNER_GIT", "/nonexistent") + "/config", ".git/config"):
            try:
                open(t, "a").write("[core]\\n\\tfsmonitor = touch /tmp/pwned-x1\\n")
                print("WROTE", t)
            except OSError as e:
                print("denied", t, type(e).__name__)
        """)
    p, e = project(tmp_path, monkeypatch, program=attack)
    root = p.model.path.parent
    before = tree(root / ".git")
    try:
        fid = broken(p, e)
        name = fid.split("/")[1]
        clone = p.dir / "repair" / name
        e.run_block(p.model.spec.blocks["repair-fix"], "test")
        it = one(p, fid)
    finally:
        e.close()
    assert git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=clone) == str((clone / ".git").resolve())
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists() and (clone / ".git").is_dir()
    own = {f.stat().st_ino for f in (root / ".git" / "objects").rglob("*") if f.is_file()}
    assert not own & {f.stat().st_ino for f in (clone / ".git" / "objects").rglob("*") if f.is_file()}, "no hard links"
    assert "WROTE" not in it.fields["test"]["stdout"] and it.fields["test"]["stdout"].count("denied") == 3
    assert tree(root / ".git") == before, "the owner's git metadata is untouched"
    assert "fsmonitor" not in (clone / ".git" / "config").read_text()
    assert not Path("/tmp/pwned-x1").exists()


@pytest.mark.parametrize("bad", ["other", "git", "link", "same"])
def test_x1_a_proposal_naming_another_file_or_a_link_is_refused(tmp_path, monkeypatch, bad):
    p, e = project(tmp_path, monkeypatch, program=BROKEN if bad == "same" else FIXED)
    c, base = fix.clone(fix.owner_repo(p.model.path.parent), tmp_path / "c")
    e.close()
    work = Path(c.work)
    if bad == "link":
        (work / "collect.py").unlink()
        (work / "collect.py").symlink_to(tmp_path / "outside.py")
        (tmp_path / "outside.py").write_text(BROKEN)
    path = {"other": "ergostat.yaml-missing", "git": ".git/config", "link": "collect.py", "same": "collect.py"}[bad]
    with pytest.raises(fix.Refused):
        fix.propose(c, path, FIXED if bad != "same" else BROKEN, f"{FAILURE}/collector-00000000")
    assert c("rev-parse", "HEAD").strip() == base and not c("status", "--porcelain", "--untracked-files=no").strip() \
        or bad == "link", "nothing committed, nothing written"
    if bad == "link":
        assert (tmp_path / "outside.py").read_text() == BROKEN, "never written through a link"


# ---- X2: reads by allowlist


def test_x2_the_ai_is_given_only_the_allowlisted_files_and_has_no_tools(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, files={"secret.key": "a" * 40000})
    try:
        fid = broken(p, e)
        fixed(p, e, fid)
    finally:
        e.close()
    prompt = calls(tmp_path)[0]["prompt"]
    given = json.loads(prompt.rsplit("\n", 1)[-1])
    assert list(given["files"]) == ["collect.py", "answer.json", "ergostat.yaml", "notes.txt"], list(given["files"])
    assert "dot-file-secret" not in prompt and "untracked-secret" not in prompt and "a" * 1000 not in prompt
    monkeypatch.delenv("ERGOSTAT_AI")
    cmd = fix.command("haiku", 0.25, fix.SYSTEM)
    assert cmd[cmd.index("--tools") + 1] == "" and "--strict-mcp-config" in cmd and "--max-budget-usd" in cmd
    assert cmd[cmd.index("--model") + 1] == "haiku"


def test_x2_a_fix_under_test_reads_nothing_outside_its_allowlist_and_its_output_is_scrubbed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    secrets = {"jira_token": "jira-secret-0001", ".claude.json": "claude-secret-0002", ".ssh/id_rsa": "ssh-secret-0003",
               ".zsh_history": "history-secret-0004"}
    for k, v in secrets.items():
        (home / k).write_text(v)
    monkeypatch.setenv("HOME", str(home))
    reads = "".join(f"\ntry:\n    print(open({str(home / k)!r}).read())\nexcept OSError as e:\n    print('denied', type(e).__name__)\n"
                    for k in secrets)
    attack = FIXED + reads + "print('key: sk-ant-api03-' + 'x' * 40)\n"
    p, e = project(tmp_path, monkeypatch, program=attack)
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
    finally:
        e.close()
    out = it.fields["test"]["stdout"]
    assert out.count(DENIED) == 4 and not any(v in out for v in secrets.values()), out
    assert "sk-ant-api03-xxxx" not in out, "the test's output is scrubbed"


def test_m2_m3_a_fix_cannot_tell_it_is_under_test_and_leaves_no_process_behind(tmp_path, monkeypatch):
    marker = tmp_path / "proj" / "alive"
    attack = FIXED + textwrap.dedent("""
        import os, subprocess
        print("ENV", sorted(k for k in os.environ if "ERGOSTAT" in k or "DRY" in k or "PYTEST" in k))
        subprocess.Popen(["/bin/sh", "-c", "sleep 3; echo late > alive"], start_new_session=True)
        """)
    p, e = project(tmp_path, monkeypatch, program=attack)
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
    finally:
        e.close()
    assert "ENV []" in it.fields["test"]["stdout"]
    import time
    time.sleep(3.5)
    assert not marker.exists() and it.fields["test"]["passed"]


class _Server(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def _any(self):
        self.seen.append(self.command)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = do_POST = _any

    def log_message(self, *a):
        pass


def test_m6_a_read_only_rerun_reaches_its_hosts_for_get_only(tmp_path, monkeypatch):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Server)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    _Server.seen = []
    attack = FIXED + textwrap.dedent(f"""
        import urllib.request
        print("GET", urllib.request.urlopen("http://localhost:{port}/x").read())
        try:
            urllib.request.urlopen(urllib.request.Request("http://localhost:{port}/x", data=b"x", method="POST"))
            print("POSTED")
        except Exception as e:
            print("refused", type(e).__name__)
        """)
    try:
        p, e = project(tmp_path, monkeypatch, program=attack, extra=f"    network: ['localhost:{port}']\n")
        try:
            fid = broken(p, e)
            it = fixed(p, e, fid)
        finally:
            e.close()
    finally:
        srv.shutdown()
    out = it.fields["test"]["stdout"]
    assert "GET b'ok'" in out and "POSTED" not in out and "refused" in out, out
    assert _Server.seen == ["GET"]


def test_m7_the_daily_cap_fails_closed_and_never_overshoots(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, with_=", daily: 1, budget: 0.5")
    try:
        fid = broken(p, e)
        (p.dir / "repair" / "spend.jsonl").write_text(json.dumps({"time": 9e12, "usd": 0.6}) + "\n")
        assert fixed(p, e, fid).state == "open" and not calls(tmp_path), "0.6 spent and 0.5 more would pass 1"
        (p.dir / "repair" / "spend.jsonl").write_text("not json\n")
        e.dispatch.due_now.clear()
        it = fixed(p, e, fid)
        assert it.state == "open" and not calls(tmp_path), "an unreadable ledger: no call"
    finally:
        e.close()
    (p.dir / "repair" / "spend.jsonl").write_text("")
    plain = tmp_path / "plain_ai.py"                         # a cost it does not say: counted as the whole budget
    plain.write_text(f"import sys\nsys.stdin.read()\nopen({str(tmp_path / 'ai.jsonl')!r}, 'a').write('{{}}\\n')\nprint('{{}}')\n")
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {plain}")
    a = type("A", (), {"budget": 0.5, "daily": 1.0, "timeout": 30, "model": "haiku"})
    fix.ask(p, "You repair", fix.SYSTEM, a)
    fix.ask(p, "You repair", fix.SYSTEM, a)
    with pytest.raises(fix.Capped):
        fix.ask(p, "You repair", fix.SYSTEM, a)
    assert len(calls(tmp_path)) == 2


@pytest.mark.parametrize("how", ["moved", "local", "tampered"])
def test_m8_apply_refuses_a_moved_head_a_local_change_or_a_tampered_clone(tmp_path, monkeypatch, how):
    p, e = project(tmp_path, monkeypatch)
    root = p.model.path.parent
    try:
        fid = broken(p, e)
        f = fixed(p, e, fid).fields
        clone = p.dir / "repair" / fid.split("/")[1]
        if how == "moved":
            (root / "notes.txt").write_text("moved on")
            git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "later", cwd=root)
        elif how == "local":
            (root / "collect.py").write_text(BROKEN + "# the owner's own edit\n")
        else:
            (clone / ".git").rename(clone / "git-moved")
            (clone / ".git").write_text(f"gitdir: {clone / 'git-moved'}\n")
        head = git("rev-parse", "HEAD", cwd=root)
        gate.approve(p, p.model.spec, actions.about(p, fid)[0]["id"])
    finally:
        e.close()
    it = one(p, fid)
    assert it.state == "open" and git("rev-parse", "HEAD", cwd=root) == head != f["fix"], it.fields.get("why")
    if how == "local":
        assert (root / "collect.py").read_text().endswith("# the owner's own edit\n")
    assert it.fields["why"]


# ---- the macOS kernel's limits


def test_seatbelt_profiles_keep_filter_lists_short_and_no_syscall_rules(tmp_path):
    from ergostat.sandbox import seatbelt
    reads, libs = sandbox.toolchain(PY)
    prof = seatbelt.profile(str(tmp_path / "copy"), str(tmp_path / "t"), reads, libs, 4321)
    assert prof.startswith("(version 1)\n(deny default)")
    for rule in prof.splitlines():
        assert len(re.findall(r"\((?:subpath|literal|regex|sysctl-name|sysctl-name-prefix|remote) ", rule)) <= 5, rule
        assert "syscall" not in rule, rule
    src = (Path(fix.__file__).parent).glob("*.py")
    assert not any("sandbox-exec" in f.read_text() or "seatbelt" in f.read_text() for f in src), \
        "the repair loop builds no profile of its own: only ergostat.sandbox does"


# ---- the second review's findings


def test_r2_a_large_fix_is_refused_and_the_diff_is_shown_whole(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, program=FIXED + "#" * 40000 + "\nimport os; os.system('evil')\n")
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
    finally:
        e.close()
    assert it.state == "open" and not actions.about(p, fid), "a program past 32,000 characters is no fix"
    p, e = project(tmp_path / "b", monkeypatch, program=FIXED + "#" * 25000 + "\nprint('payload')\n")
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
    finally:
        e.close()
    assert it.state == "awaiting-approval" and "print('payload')" in it.fields["diff"], "the diff is never cut"


def test_r3_a_call_killed_midway_still_counts_its_whole_budget(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, with_=", daily: 1, budget: 0.4")
    e.close()
    a = type("A", (), {"budget": 0.4, "daily": 1.0, "timeout": 30, "model": "haiku"})
    hang = tmp_path / "hang.py"
    hang.write_text("import sys, time\nsys.stdin.read()\ntime.sleep(30)\n")
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {hang}")
    code = f"from tests.test_repair2 import *\nfrom ergostat.store import Project\nfrom ergostat import model as m\n" \
           f"p = Project(m.load(__import__('pathlib').Path({str(p.model.path.parent)!r})))\n" \
           f"a = type('A', (), {{'budget': 0.4, 'daily': 1.0, 'timeout': 30, 'model': 'haiku'}})\nfix.ask(p, 'x', '', a)\n"
    child = subprocess.Popen([PY, "-c", code], cwd=Path(__file__).parent.parent, start_new_session=True)
    import time
    time.sleep(3)
    os.killpg(child.pid, 9)                                  # as the engine kills a run past its timeout
    child.wait()
    rows = [json.loads(x) for x in (p.dir / "repair" / "spend.jsonl").read_text().splitlines()]
    assert sum(r["usd"] for r in rows) == pytest.approx(0.4), rows
    with pytest.raises(fix.Capped):                          # 0.4 counted, 0.4 more would be 0.8, 0.4 again past 1
        monkeypatch.setenv("ERGOSTAT_AI", f"{PY} -c print")
        fix.ask(p, "x", "", a)
        fix.ask(p, "x", "", a)


def test_r4_an_uncommitted_program_or_one_that_cannot_be_applied_goes_to_a_person(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    try:
        fid = broken(p, e)
        (p.model.path.parent / "collect.py").write_text(BROKEN + "# an edit not committed\n")
        it = fixed(p, e, fid)
    finally:
        e.close()
    assert it.state == "open" and not calls(tmp_path), "no AI call for a program it would fix from other text"
    assert any("not committed" in str((x.get("data") or {}).get("why")) for x in p.events.query(n=None, item=fid))


# ---- the gate review's round


def test_g2_an_approval_after_a_denial_is_ignored_counted_as_denied_and_never_runs(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    root = p.model.path.parent
    head = git("rev-parse", "HEAD", cwd=root)
    try:
        fid = broken(p, e)
        fixed(p, e, fid)
    finally:
        e.close()
    real = actions.step

    def denied_in_between(p_, aid, what, data, by="ergostat", causedby=None):   # between the check and the write
        if what == "approved":
            real(p_, aid, "denied", {"denied_by": "owner on the phone"}, by="owner")
        return real(p_, aid, what, data, by, causedby)
    monkeypatch.setattr(actions, "step", denied_in_between)
    aid = actions.about(p, fid)[0]["id"]
    gate.approve(p, p.model.spec, aid)
    a = actions.about(p, fid)[0]
    assert a["state"] == "denied" and a["ignored"] == ["approved"] and a["denied_by"] == "owner on the phone"
    assert gate.run_once(p, p.model.spec, aid) is None and gate.sweep(p, p.model.spec) == 0
    assert git("rev-parse", "HEAD", cwd=root) == head
    got = actions.counts(p, cls="apply-fix")
    assert (got["approved"], got["denied"]) == (0, 1), "counted as denied: never evidence for promoting"
    real(p, aid, "ran", {"exit": 0, "output": "merged"})        # a run that got through before the denial was seen
    assert actions.about(p, fid)[0]["state"] == "ran despite denial"
    assert its.one(p.events, p.model.spec, aid).state == "ran despite denial", "and so on the action's own page"


def test_g2_approver_ai_is_refused_by_check(tmp_path, monkeypatch):
    with pytest.raises(mdl.ModelError, match="approver: ai: not yet: a sound allowlist guard is needed"):
        project(tmp_path, monkeypatch, approver="ai")


def test_g2_a_notification_of_a_repair_always_says_what_approving_does(tmp_path, monkeypatch):
    from ergostat.inbox import deliver, entries
    p, e = project(tmp_path, monkeypatch)
    try:
        fid = broken(p, e)
        fixed(p, e, fid)
    finally:
        e.close()
    es = [x for x in entries.entries(p, p.model.spec) if x["kind"] == "action"]
    n = type("N", (), {"wait_at_most": None})
    for scrub in (None, lambda t: t):                        # detail: minimal, and full
        _, text = deliver.message(n, [{**x, "age": 60} for x in es], False, "http://x", scrub)
        assert entries.MERGES in text, text


def test_g3_apply_refuses_an_action_for_another_fix(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    try:
        fid = broken(p, e)
        fixed(p, e, fid)
        aid = actions.about(p, fid)[0]["id"]
        p.events.add("ergostat.action.requested", item=aid, source="ergostat", data={"key": "collector-0-other"})
        gate.approve(p, p.model.spec, aid)
    finally:
        e.close()
    assert one(p, fid).state == "open" and "another fix" in one(p, fid).fields["why"]


def test_g4_the_ledger_takes_a_calls_real_cost_over_its_budget(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch)
    e.close()
    over = tmp_path / "over.py"
    over.write_text("import sys, json\nsys.stdin.read()\nprint(json.dumps({'type': 'result', 'total_cost_usd': 0.7, "
                    "'result': '{}'}))\n")
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {over}")
    a = type("A", (), {"budget": 0.5, "daily": 1.0, "timeout": 30, "model": "haiku"})
    fix.ask(p, "x", "", a)
    rows = [json.loads(x) for x in (p.dir / "repair" / "spend.jsonl").read_text().splitlines()]
    assert sum(r["usd"] for r in rows) == pytest.approx(0.7), rows
    with pytest.raises(fix.Capped):
        fix.ask(p, "x", "", a)


def test_g4_an_ai_that_does_not_answer_in_time_is_a_nack_not_a_crash(tmp_path, monkeypatch):
    p, e = project(tmp_path, monkeypatch, with_=", timeout: 4s")
    hang = tmp_path / "hang.py"
    hang.write_text("import sys, time\nsys.stdin.read()\ntime.sleep(20)\n")
    monkeypatch.setenv("ERGOSTAT_AI", f"{PY} {hang}")
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
        ran = p.events.query(n=1, item="repair-fix", type="agent.*")[0]
    finally:
        e.close()
    assert ran["type"] == "agent.ran" and it.state == "open"
    assert any("did not answer" in str((x.get("data") or {}).get("why")) for x in p.events.query(n=None, item=fid))


def test_g5_a_committed_gitattributes_filter_never_runs(tmp_path, monkeypatch):
    marker = tmp_path / "filter-ran"
    p, e = project(tmp_path, monkeypatch, files={".gitattributes": "*.py filter=pwn\n"})
    root = p.model.path.parent
    git("config", "filter.pwn.clean", f"touch {marker}; cat", cwd=root)       # (as if planted in the owner's config)
    git("config", "filter.pwn.smudge", f"touch {marker}; cat", cwd=root)
    try:
        fid = broken(p, e)
        assert fixed(p, e, fid).state == "awaiting-approval"
        gate.approve(p, p.model.spec, actions.about(p, fid)[0]["id"])
        assert one(p, fid).state == "applied"
    finally:
        e.close()
    assert not marker.exists(), "no filter driver ran: not in the clone, the test or the apply"


def test_g5_a_symlinked_directory_is_neither_given_nor_readable(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "token.txt").write_text("linked-secret-9999")
    reads = "try:\n    print(open('data/token.txt').read())\nexcept OSError as e:\n    print('denied', type(e).__name__)\n"
    d = tmp_path / "proj"
    p, e = project(tmp_path, monkeypatch, program=FIXED + reads, files={})
    (d / "data").symlink_to(outside)
    git("add", "data", cwd=d)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a link", cwd=d)
    try:
        fid = broken(p, e)
        it = fixed(p, e, fid)
    finally:
        e.close()
    assert "linked-secret" not in calls(tmp_path)[0]["prompt"]
    assert DENIED in it.fields["test"]["stdout"] and "linked-secret" not in it.fields["test"]["stdout"]
