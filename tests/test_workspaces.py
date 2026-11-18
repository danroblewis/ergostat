"""Workspace pools (SPEC §12k): a git worktree per item, acquired for its run (the same one again on a retry), held while
the item is under review, cleaned when it finishes, quarantined when dirty or broken; released by lease events; and an
AI block's working directory (workdir:, or its item's workspace) passed to the session it starts."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from ergostat import model as mdl
from ergostat import state as st
from ergostat.numbers import measures
from ergostat.spec.engine import Engine
from ergostat.store import Project
from ergostat.workspaces import leases
from ergostat.workspaces import pool as pl

PY = sys.executable


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def make_repo(d: Path) -> Path:
    d.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=d)
    (d / "app.py").write_text("print('hi')\n")
    git("add", "app.py", cwd=d)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=d)
    return d


MODEL = """
name: t
items:
  ticket:
    id: ticket/*
    states: [open, review, done]
    on: {ticket.review: review, ticket.done: done}
    show: [title]
stocks:
  open-tickets:
    sensor: {items: ticket, state: open, every: 5s}
flows:
  closed:
    from: open-tickets
    sensor: {items: ticket, entering: done, over: 10m}
workspaces:
  code:
    repo: product
    pool: pool
    size: 2
    branch: "{kind}/{id}-{slug}"
    base: main
"""


def project(tmp_path, blocks: str = "", extra: str = "") -> Project:
    if not (tmp_path / "product").exists():
        make_repo(tmp_path / "product")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent(MODEL) + textwrap.dedent(extra) +
                                            ("blocks:\n" + textwrap.indent(textwrap.dedent(blocks), "  ") if blocks else ""))
    m = mdl.load(tmp_path)
    errors = [x for x in m.problems if x.level == "error"]
    assert not errors, errors
    return Project(m)


def ticket(p, n: int, title: str = "Fix the login page", state: str | None = None):
    p.events.add("ticket.opened", item=f"ticket/{n}", source="watch", data={"title": title})
    if state:
        p.events.add(f"ticket.{state}", item=f"ticket/{n}", source="watch")


def test_the_branch_is_made_from_the_items_fields():
    assert pl.branch_for("{kind}/{id}-{slug}", "ticket/12", {"title": "Fix the Login page!"}) == "ticket/12-fix-the-login-page"
    assert pl.branch_for("work/{item}", "ticket/12") == "work/ticket/12"
    assert pl.branch_for("{kind}/{team}/{id}", "ticket/3", {"team": "pay ments"}) == "ticket/pay-ments/3"
    assert pl.branch_for("{kind}/{missing}..{id}.lock", "ticket/3") == "ticket/3"   # no "..", no ".lock": a safe ref


def test_a_fresh_worktree_on_a_new_branch_and_the_same_one_again_on_a_retry(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    ticket(p, 1)
    got = pl.acquire(p, spec, "code", "ticket/1", {"title": "Fix the login page"}, run="r1")
    d = Path(got["dir"])
    assert d == (tmp_path / "pool" / "1").resolve() and d.is_dir()
    assert got["branch"] == "ticket/1-fix-the-login-page" and "fresh" in got["how"]
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=d) == got["branch"]
    assert got["writes"] and any(w.endswith("objects") for w in got["writes"])
    (d / "app.py").write_text("print('changed')\n")                 # work in progress, not committed
    again = pl.acquire(p, spec, "code", "ticket/1", {}, run="r2")
    assert again["dir"] == got["dir"] and "same one" in again["how"]
    assert (d / "app.py").read_text() == "print('changed')\n"       # its work as it left it
    assert pl.counts(p, spec, "code") == {"free": 1, "in-use": 1, "held": 0, "quarantined": 0}


def test_held_while_under_review_cleaned_when_finished_then_reused_after_a_reset(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    ticket(p, 1)
    got = pl.acquire(p, spec, "code", "ticket/1", {"title": "a"})
    d = Path(got["dir"])
    (d / "new.py").write_text("x = 1\n")
    git("add", "new.py", cwd=d)
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "work", cwd=d)
    p.events.add("ticket.review", item="ticket/1", source="watch")
    pl.release(p, spec, "ticket/1", leases.finished(p, spec, "ticket/1"), "its lease ended")
    assert pl.counts(p, spec, "code")["held"] == 1                  # under review: kept for it
    assert pl.acquire(p, spec, "code", "ticket/1", {})["dir"] == str(d)   # review asked for more: the same one
    pl.release(p, spec, "ticket/1", False, "its lease ended")
    p.events.add("ticket.done", item="ticket/1", source="watch")
    assert leases.finished(p, spec, "ticket/1")
    leases.sweep(p, spec)                                           # the item finished: cleaned
    assert pl.counts(p, spec, "code") == {"free": 2, "in-use": 0, "held": 0, "quarantined": 0}
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=d) == "HEAD"   # detached at the base; its branch kept
    assert git("branch", "--list", got["branch"], cwd=tmp_path / "product")
    ticket(p, 2, "Second")
    two = pl.acquire(p, spec, "code", "ticket/2", {"title": "Second"})
    assert two["dir"] == str(d) and "reused" in two["how"]          # the existing worktree, reset onto its branch
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=d) == "ticket/2-second"
    assert not (d / "new.py").exists()                              # from the base, not from ticket/1's work


def test_a_dirty_or_broken_worktree_is_quarantined_not_reused_until_freed(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    ticket(p, 1)
    d = Path(pl.acquire(p, spec, "code", "ticket/1", {})["dir"])
    (d / "scratch.txt").write_text("left behind\n")
    p.events.add("ticket.done", item="ticket/1", source="watch")
    pl.release(p, spec, "ticket/1", True, "its lease ended")
    s = pl.slots(p, spec, spec.workspaces["code"])[1]
    assert s["state"] == "quarantined" and "dirty" in s["why"]
    assert (d / "scratch.txt").exists()                              # kept for the owner, not thrown away
    ticket(p, 2)
    two = pl.acquire(p, spec, "code", "ticket/2", {})
    assert Path(two["dir"]).name == "2"                              # never given the quarantined one
    assert any(a["what"] == "workspace code-1" for a in st.attention(st.snapshot(p), False, p.model))
    pl.free(p, spec, "code", 1)
    assert not d.exists() and pl.slots(p, spec, spec.workspaces["code"])[1]["state"] == "free"
    with pytest.raises(pl.PoolError):
        pl.free(p, spec, "code", 2)                                  # only a quarantined one is freed by hand
    # a folder there that is no worktree of the repository: quarantined when it would be reused
    d.mkdir()
    (d / "junk").write_text("x")
    ticket(p, 3)
    with pytest.raises(pl.PoolError, match="none free"):            # 2 is in use, 1 is broken
        pl.acquire(p, spec, "code", "ticket/3", {})
    s = pl.slots(p, spec, spec.workspaces["code"])[1]
    assert s["state"] == "quarantined" and "not a git worktree" in s["why"]
    assert measures.measure(p, "ergostat.workspaces.quarantined@code") == 1.0
    assert measures.measure(p, "workspaces.in-use") == 1.0


def test_lease_events_hold_and_release_the_workspace(tmp_path):
    p = project(tmp_path)
    spec = p.model.spec
    ticket(p, 1)
    pl.acquire(p, spec, "code", "ticket/1", {}, lease="ergostat.lease/a")
    seq = leases.sweep(p, spec)
    p.events.add("ergostat.lease.expired", item="ergostat.lease/a", source="ergostat", data={"item": "ticket/1"})
    seq = leases.sweep(p, spec, seq)
    assert pl.slots(p, spec, spec.workspaces["code"])[1]["state"] == "held"     # expired, not finished: kept
    p.events.add("ergostat.lease.taken", item="ergostat.lease/b", source="ergostat", data={"item": "ticket/1"})
    seq = leases.sweep(p, spec, seq)
    s = pl.slots(p, spec, spec.workspaces["code"])[1]
    assert s["state"] == "in-use" and s["lease"] == "ergostat.lease/b"           # taken again: in use again
    p.events.add("ticket.done", item="ticket/1", source="watch")
    p.events.add("ergostat.lease.ended", item="ergostat.lease/b", source="ergostat", data={"item": "ticket/1"})
    leases.sweep(p, spec, seq)
    assert pl.counts(p, spec)["free"] == 2                                       # ended, finished: cleaned
    p.events.add("ergostat.lease.ended", item="ergostat.lease/c", source="ergostat", data={"item": "ticket/9"})
    leases.sweep(p, spec, seq)                                                   # an item with no workspace: nothing


def test_the_pool_is_checked(tmp_path):
    make_repo(tmp_path / "product")
    (tmp_path / "ergostat.yaml").write_text(textwrap.dedent("""
        name: t
        workspaces:
          code: {repo: product, type: svn}
          third: {repo: product, size: 0, branch: "{kind}/{}"}
          other: {size: 1}
        actions:
          push: {run: "git push origin HEAD:{branch}"}
        blocks:
          dev:
            type: ai
            prompt: work
            workdir: product
            workspace: nowhere
            tools: [Read, "mcp__x__y"]
            actions: [pull]
            every: 1h
    """))
    from ergostat import spec
    msgs = [x.message for x in spec.read(tmp_path / "ergostat.yaml")[1] if x.level == "error"]
    assert any("workspace code.type" in m for m in msgs)
    assert any("workspace other: repo:" in m for m in msgs)
    assert any("workspace third.size" in m for m in msgs) and any("workspace third.branch" in m for m in msgs)
    assert any("workdir: or workspace:, not both" in m for m in msgs)
    assert any("'nowhere' is not a pool" in m for m in msgs)
    assert any("outward acts are actions:, not tools" in m for m in msgs)
    assert any("'pull' is not one of the actions" in m for m in msgs)


def fake_claude(tmp_path) -> Path:
    """A stand-in for ``claude -p``: it writes where it ran, its arguments and its environment, and answers."""
    f = tmp_path / "fake-claude.py"
    f.write_text(textwrap.dedent(f"""
        import json, os, sys
        sys.stdin.read()
        open({str(tmp_path / 'claude-call.json')!r}, 'w').write(json.dumps({{"cwd": os.getcwd(), "argv": sys.argv[1:],
            "sandbox": os.environ.get("ERGOSTAT_SANDBOX"), "item": os.environ.get("ERGOSTAT_ITEM"),
            "branch": os.environ.get("ERGOSTAT_BRANCH"), "timeout": os.environ.get("MCP_TOOL_TIMEOUT")}}))
        print('{{"decision": "done", "why": "a stand-in"}}')
    """))
    return f


def test_an_ai_block_without_run_starts_claude_in_its_items_workspace_gated(tmp_path, monkeypatch):
    import ergostat.spec.engine as eng
    f = fake_claude(tmp_path)
    monkeypatch.setattr(eng, "AI_COMMAND", f"{PY} {f}")
    (tmp_path / "docs").mkdir()
    p = project(tmp_path, """
        dev:
          type: ai
          prompt: "Fix it."
          workspace: code
          read: [docs]
          tools: [Read, Edit, Bash]
          actions: [push]
          every: 1h
    """, """
        actions:
          push:
            run: git push origin HEAD:{branch}
            gate: approve
    """)
    ticket(p, 4, "Speed up search")
    monkeypatch.setenv("ERGOSTAT_ITEM", "ticket/4")
    monkeypatch.setenv("ERGOSTAT_LEASE", "ergostat.lease/x")
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["dev"], "schedule")
    call = json.loads((tmp_path / "claude-call.json").read_text())
    ws = (tmp_path / "pool" / "1").resolve()
    assert call["cwd"] == str(ws) and call["item"] == "ticket/4" and call["branch"] == "ticket/4-speed-up-search"
    a = call["argv"]
    assert a[a.index("--add-dir") + 1] == str((tmp_path / "docs").resolve())
    assert "--restricted" in a and a[a.index("--tools") + 1] == "Bash,Edit,Read"
    assert a[a.index("--permission-mode") + 1] == "dontAsk" and "--strict-mcp-config" in a
    assert "mcp__actions" in a[a.index("--allowedTools") + 1].split(",")
    deny = a[a.index("--disallowedTools") + 1].split(",")
    assert {"Bash(git push:*)", "Bash(gh:*)", "Bash(curl:*)", "WebFetch"} <= set(deny)
    settings = json.loads(a[a.index("--settings") + 1])
    assert settings["sandbox"]["enabled"] and settings["sandbox"]["allowUnsandboxedCommands"] is False
    assert settings["sandbox"]["network"]["allowedDomains"] == []
    assert str((tmp_path / "docs").resolve()) in settings["sandbox"]["filesystem"]["denyWrite"]
    mcp = json.loads(a[a.index("--mcp-config") + 1])["mcpServers"]["actions"]
    assert mcp["args"] == ["-m", "ergostat.actions.server"] and mcp["env"]["ERGOSTAT_SANDBOX"] == call["sandbox"]
    assert int(call["timeout"]) >= 300_000                          # a tool call may wait for the owner
    # under a lease, the run's end leaves the workspace in use: the lease's end releases it
    assert pl.slots(p, p.model.spec, p.model.spec.workspaces["code"])[1]["state"] == "in-use"


def test_a_session_started_by_the_helper_runs_in_the_workdir(tmp_path, monkeypatch):
    monkeypatch.setenv("ERGOSTAT_CLAUDE", "echo")
    monkeypatch.setenv("ERGOSTAT_ECHO_WORK", "0")
    monkeypatch.setenv("ERGOSTAT_ECHO_RUN", f"{PY} -c \"import os; print('cwd=' + os.getcwd())\"")
    make_repo(tmp_path / "product")
    p = project(tmp_path, """
        dev:
          type: ai
          prompt: "Fix it."
          workdir: product
          run: $ERGOSTAT_CMD session dev --model haiku --no-live
          every: 1h
    """)
    Engine(p, say=lambda s: None).run_block(p.model.spec.blocks["dev"], "schedule")
    started = p.events.query(n=1, type="session.started")[-1]
    assert started["data"]["workdir"] == str((tmp_path / "product").resolve())
    ran = p.events.query(n=1, type="session.ran")[-1]
    assert f"cwd={(tmp_path / 'product').resolve()}" in ran["data"]["said"]


def test_a_run_with_no_lease_releases_its_workspace_when_it_ends(tmp_path, monkeypatch):
    import ergostat.spec.engine as eng
    monkeypatch.setattr(eng, "AI_COMMAND", f"{PY} {fake_claude(tmp_path)}")
    monkeypatch.delenv("ERGOSTAT_ITEM", raising=False)
    monkeypatch.delenv("ERGOSTAT_LEASE", raising=False)
    p = project(tmp_path, """
        dev:
          type: ai
          prompt: "Fix it."
          workspace: code
          every: 1h
    """)
    e = Engine(p, say=lambda s: None)
    e.run_block(p.model.spec.blocks["dev"], "schedule")              # no item: it does not start
    failed = p.events.query(n=1, type="agent.failed")[-1]
    assert "names no item" in failed["data"]["note"]
    ticket(p, 5)
    e.run_block(p.model.spec.blocks["dev"], "schedule", {"command": {"amount": 1, "item": "ticket/5"}})
    assert json.loads((tmp_path / "claude-call.json").read_text())["cwd"] == str((tmp_path / "pool" / "1").resolve())
    s = pl.slots(p, p.model.spec, p.model.spec.workspaces["code"])[1]
    assert s["state"] == "held" and s["item"] == "ticket/5"          # its run was its lease; not finished: held
