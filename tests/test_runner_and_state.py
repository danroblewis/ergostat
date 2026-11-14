import json
import time

from ergostat import runner, state


def run_with(project, repo, script):
    repo.write("clean.py", script)
    return runner.run_agent(project, project.model.agents["cleaner"])


def test_a_run_records_readings_decisions_and_openings(project, repo):
    r = run_with(project, repo, """
        import json, sys
        ctx = json.load(sys.stdin)
        assert ctx["agent"] == "cleaner" and {"kind": "valve", "name": "delete-old-files"} in ctx["roles"]
        print(json.dumps({"sensor": "disk-usage", "value": 91}))
        print(json.dumps({"controller": "disk-under-80", "decision": "free 20"}))
        print(json.dumps({"valve": "delete-old-files", "amount": 20}))
        print("plain text goes to the log")
    """)
    assert r["exit"] == 0 and (r["readings"], r["decisions"], r["openings"], r["refused"]) == (1, 1, 1, 0)
    assert project.measurements.latest("sensor/disk-usage")[1] == 91
    (opened,) = project.events.query(type="valve.opened")
    assert opened["item"] == "delete-old-files" and opened["data"]["amount"] == 20 and opened["source"] == "cleaner"
    assert "plain text goes to the log" in runner.log_path(project, "cleaner").read_text()


def test_an_agent_acts_only_through_the_roles_it_fills(project, repo):
    r = run_with(project, repo, """
        import json
        print(json.dumps({"valve": "someone-elses-valve", "amount": 1}))
        print(json.dumps({"event": "loop.off", "item": "x"}))
    """)
    assert r["refused"] == 2 and not project.events.query(type="valve.opened")
    whys = [e["data"]["why"] for e in project.events.query(type="agent.refused")]
    assert "cleaner does not fill valve someone-elses-valve" in whys[0] and "ergostat's own" in whys[1]


def test_a_failing_run_is_recorded_as_failed(project, repo):
    r = run_with(project, repo, "import sys\nsys.exit(3)\n")
    assert r["note"] == "exited 3" and project.events.query(type="agent.failed")
    snap = state.snapshot(project)
    assert snap["agents"]["cleaner"]["failing"]
    assert any(a["what"] == "agent cleaner" for a in state.attention(snap))


def test_the_edge_detector_records_a_loop_crossing_its_setpoint_once(project):
    project.measurements.add("sensor/disk-usage", 70)
    assert [e["type"] for e in runner.edges(project)] == ["loop.holding"]
    assert runner.edges(project) == []                      # no change, no event
    project.measurements.add("sensor/disk-usage", 90)
    (off,) = runner.edges(project)
    assert off["type"] == "loop.off" and off["item"] == "disk-under-80" and off["data"]["error"] == 10


def test_state_a_loop_is_unknown_holding_or_off(project):
    assert state.snapshot(project)["loops"]["disk-under-80"]["status"] == "unknown"
    project.measurements.add("sensor/disk-usage", 81)        # within the tolerance of 2
    assert state.snapshot(project)["loops"]["disk-under-80"]["status"] == "holding"
    project.measurements.add("sensor/disk-usage", 83)
    lp = state.snapshot(project)["loops"]["disk-under-80"]
    assert lp["status"] == "off" and lp["error"] == 3


def test_an_estimated_disturbance_explains_what_the_valve_does_not(project):
    t = time.time() - 600
    project.measurements.add("sensor/disk-usage", 60, at=t)
    project.events.add("valve.opened", item="delete-old-files", source="cleaner", data={"amount": 5}, at=t + 100)
    project.measurements.add("sensor/disk-usage", 65, at=t + 300)    # +5 seen, -5 by the valve: +10 from logs
    snap = state.snapshot(project)
    r = snap["residuals"]["disk-used"]
    assert r["change"] == 5 and r["explained"] == -5 and r["unexplained"] == 10
    assert r["absorbed_by"] == ["logs-written"] and not r["significant"]
    assert snap["flows"]["logs-written"]["estimated"] and round(snap["flows"]["logs-written"]["rate"]) == 120


def test_with_no_disturbance_to_absorb_it_the_rest_is_unexplained(project, repo):
    text = repo.path.joinpath("ergostat.toml").read_text()
    text = text.replace("[[disturbance]]", "[[flow]]").replace('into = "disk-used"', 'to = "disk-used"')
    repo.write("ergostat.toml", text)
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    t = time.time() - 600
    p.measurements.add("sensor/disk-usage", 60, at=t)
    p.measurements.add("sensor/disk-usage", 70, at=t + 300)
    r = state.snapshot(p)["residuals"]["disk-used"]
    assert r["significant"] and r["unexplained"] == 10
    assert any("unexplained" in a["says"] for a in state.attention(state.snapshot(p)))


def test_an_agent_on_an_event_runs_when_it_arrives(project, repo):
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('every = "1s"', 'on = ["disk.check.requested"]'))
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    repo.write("clean.py", 'import json, sys\nctx = json.load(sys.stdin)\nprint(json.dumps({"sensor": "disk-usage", "value": 50}))\n')
    r = runner.Runner(p, say=lambda s: None)
    r.start()
    try:
        p.events.add("disk.check.requested", source="someone")
        for _ in range(60):
            if p.measurements.latest("sensor/disk-usage"):
                break
            time.sleep(0.1)
    finally:
        r.close()
    assert p.measurements.latest("sensor/disk-usage")[1] == 50
    started = p.events.query(type="agent.started")
    assert started and json.dumps(started[-1]["data"]) == '{"trigger": "disk.check.requested"}'


def test_a_residual_no_bigger_than_an_ordinary_step_is_noise(project, repo):
    text = repo.path.joinpath("ergostat.toml").read_text()
    repo.write("ergostat.toml", text.replace("[[disturbance]]", "[[flow]]").replace('into = "disk-used"', 'to = "disk-used"'))
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    t = time.time() - 600
    for i, v in enumerate([60, 61, 60, 61, 62, 61]):          # steps of 1; one unexplained step overall
        p.measurements.add("sensor/disk-usage", v, at=t + i * 60)
    r = state.snapshot(p)["residuals"]["disk-used"]
    assert r["unexplained"] == 1 and not r["significant"]


def test_a_controller_deciding_the_same_thing_is_a_hint_to_move_down_the_ladder(project, repo):
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('kind = "program"', 'kind = "ai"'))
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    for i in range(12):
        p.events.add("controller.decided", item="disk-under-80", source="cleaner",
                     data={"decision": f"under 80 ({60 + i}%): nothing to do" if i < 11 else "over 80: free 20"})
    d = state.decisions(p, "disk-under-80", 0)
    assert d["count"] == 12 and d["kinds"][0] == ("under # (#%): nothing to do", 11)
    snap = state.snapshot(p)
    (hint,) = snap["hints"]
    assert hint["controller"] == "disk-under-80" and "a decision or a rule could fill controller disk-under-80" in hint["says"]
    assert any(a["level"] == "hint" for a in state.attention(snap))
    assert state.ladder_hints(project, state.snapshot(project)) == []      # a program is low enough already


def test_a_run_past_its_timeout_is_stopped_with_what_it_started(project, repo):
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('every = "1s"', 'every = "1s"\ntimeout = "1s"'))
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    repo.write("clean.py", "import subprocess, time\nsubprocess.Popen(['sleep', '30'])\ntime.sleep(30)\n")
    t = time.time()
    r = runner.run_agent(p, p.model.agents["cleaner"])
    assert time.time() - t < 10 and r["note"] == "stopped after its timeout of 1s"
    import subprocess
    left = subprocess.run(["pgrep", "-f", "sleep 30"], capture_output=True, text=True).stdout.split()
    assert not [x for x in left if int(x) != 0 and _child_of_test(int(x))], "the run's own children were stopped too"


def _child_of_test(pid: int) -> bool:
    import subprocess
    cwd = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True).stdout
    return "/repo" in cwd and "pytest" in cwd


def test_a_valve_position_is_a_setting_kept_as_a_measurement(project, repo):
    r = run_with(project, repo, """
        import json
        print(json.dumps({"valve": "delete-old-files", "position": 3}))
        print(json.dumps({"valve": "delete-old-files", "position": 4, "amount": 2}))
    """)
    assert r["openings"] == 1 and r["refused"] == 0
    assert project.measurements.latest("valve/delete-old-files")[1] == 4
    from ergostat import graph
    assert graph.readings(project)["valve/delete-old-files"] == 4


def test_on_may_name_an_item_too():
    assert runner.matches("loop.off", {"type": "loop.off", "item": "x"})
    assert runner.matches("loop.off@backup-*", {"type": "loop.off", "item": "backup-fresh"})
    assert not runner.matches("loop.off@backup-fresh", {"type": "loop.off", "item": "queue-short"})
    assert not runner.matches("loop.*@x", {"type": "valve.opened", "item": "x"})


def test_a_loop_off_most_of_the_time_is_a_hint_to_sample_faster(project):
    t = time.time() - 1200
    project.events.add("ergostat.started", source="ergostat", at=t)
    project.measurements.add("sensor/disk-usage", 90, at=t + 10)
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t + 10, data={})
    project.events.add("loop.holding", item="disk-under-80", source="ergostat", at=t + 1000, data={})
    project.measurements.add("sensor/disk-usage", 70, at=t + 1190)
    project.events.add("controller.decided", item="disk-under-80", source="cleaner", at=t + 1190, data={"decision": "x"})
    snap = state.snapshot(project)
    assert 0.8 < snap["loops"]["disk-under-80"]["off_share"] < 0.85
    (hint,) = [h for h in snap["hints"] if h["controller"] == "disk-under-80"]
    assert "off 8" in hint["says"] and "run it more often" in hint["says"]
