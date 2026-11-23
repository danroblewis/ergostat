import os
import time

from ergostat import history, runner, state


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
    assert off["type"] == "loop.off" and off["item"] == "disk-under-80" and off["data"]["error"] == -10


def test_state_a_loop_is_unknown_holding_or_off(project):
    assert state.snapshot(project)["loops"]["disk-under-80"]["status"] == "unknown"
    project.measurements.add("sensor/disk-usage", 81)        # within the tolerance of 2
    assert state.snapshot(project)["loops"]["disk-under-80"]["status"] == "holding"
    project.measurements.add("sensor/disk-usage", 83)
    lp = state.snapshot(project)["loops"]["disk-under-80"]
    assert lp["status"] == "off" and lp["error"] == -3


def test_each_goal_says_its_word_and_its_row_once(repo):
    """state.snapshot gives every goal the one word a reader sees and its row's columns (goalrow.js draws them)."""
    from ergostat import model
    from ergostat.store import Project
    from tests.conftest import FOUR_GOALS
    (repo.path / "ergostat.toml").write_text(FOUR_GOALS)
    project = Project(model.load(repo.path))
    project.measurements.add("sensor/disk-usage", 70)
    loops = state.snapshot(project)["loops"]
    words = {n: lp["word"] for n, lp in loops.items()}
    assert words == {"disk-under-80": "holding", "disk-under-50": "off", "disk-cleaned-nightly": "open",
                     "inodes-under-90": "unknown"}, words
    assert all(lp["word"] == lp["status"] for lp in loops.values())
    assert loops["disk-under-80"]["row"] == {"measure": "disk-used", "value": 70, "unit": "%", "bound_words": "<= 80 (+2)",
                                             "trend": None, "expected": None}
    assert loops["inodes-under-90"]["row"]["value"] is None and loops["disk-under-50"]["row"]["bound_words"] == "<= 50"
    assert state.goal_row({"status": "something new", "stock": "s", "value": 1, "setpoint": "<= 2"})["word"] == "unknown"


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
    assert started and started[-1]["data"] == {"trigger": "disk.check.requested", "model": history.version(p.model)}


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
    assert hint["controller"] == "disk-under-80" and hint["says"].endswith("a decision or a rule could fill it")
    (entry,) = [a for a in state.attention(snap) if a["level"] == "hint"]
    from ergostat.dynamics import attention
    for a in (entry, *attention([entry], snap)):                          # Blocks, and Dynamics' words: the goal once
        assert (a["what"] + " " + a["says"]).count("disk-under-80") == 1, a
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
    assert "off 8" in hint["says"] and "slowest stage" in hint["says"] and "saturated" not in hint["says"]


def test_a_week_of_readings_is_sampled_in_sql_and_the_ends_kept_exact(project):
    import sqlite3
    t0 = time.time() - 7 * 86400
    with sqlite3.connect(project.measurements.path) as c:
        c.executemany("insert into samples(series, time, value) values (?,?,?)",
                      [("sensor/disk-usage", t0 + i * 5, 50 + (i % 40)) for i in range(120000)])
    t = time.time()
    snap = state.snapshot(project, window=8 * 86400)
    assert time.time() - t < 3
    pts = state.history(project, "disk-used", t0 - 1)
    assert len(pts) < 700 and pts[0] == (t0, 50) and pts[-1][1] == 50 + (119999 % 40)
    assert snap["stocks"]["disk-used"]["value"] == 50 + (119999 % 40)


def test_pruning_forgets_old_record_but_not_the_model_history(project):
    old = time.time() - 100 * 86400
    project.events.add("x.y.z", at=old)
    project.events.add("model.changed", at=old, data={"parts": {}, "added": [], "removed": [], "changed": []})
    project.measurements.add("sensor/disk-usage", 1, at=old)
    assert project.events.prune(time.time() - 30 * 86400) == 1 and project.measurements.prune(time.time() - 30 * 86400) == 1
    assert [e["type"] for e in project.events.query(n=None)] == ["model.changed"]


def test_a_loop_whose_valve_cannot_keep_up_is_called_saturated(project):
    t = time.time() - 1200
    project.events.add("ergostat.started", source="ergostat", at=t)
    for i, v in enumerate([60, 70, 80, 90, 100]):               # the stock climbs though the valve keeps opening
        project.measurements.add("sensor/disk-usage", v, at=t + 10 + i * 290)
        project.events.add("valve.opened", item="delete-old-files", source="cleaner", at=t + 20 + i * 290, data={"amount": 2})
        project.events.add("controller.decided", item="disk-under-80", source="cleaner", at=t + 20 + i * 290, data={"decision": "free 2"})
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t + 30, data={})
    (hint,) = [h for h in state.snapshot(project)["hints"] if h["controller"] == "disk-under-80"]
    assert "of the time: saturated, moving its most each run." in hint["says"]   # every opening moved 2


def test_a_suggestion_waits_for_its_verdict_and_names_its_goal_once(project):
    """Too little record to tell why a loop is off: no suggestion, its goal's entry says when; once
    there is, the suggestion is headed by the loop and its text does not name it again."""
    t = time.time() - 300
    project.events.add("ergostat.started", source="ergostat", at=t)
    project.measurements.add("sensor/disk-usage", 90, at=t + 10)
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t + 10, data={})
    project.events.add("controller.decided", item="disk-under-80", source="cleaner", at=t + 290, data={"decision": "x"})
    snap = state.snapshot(project)
    assert not [h for h in snap["hints"] if h["controller"] == "disk-under-80"]
    att = state.attention(snap, True, project.model)
    (entry,) = [a for a in att if a["what"] == "loop disk-under-80"]
    assert entry["level"] == "bad" and 250 < entry["diagnosis_in"] <= 300
    snap["hints"] = [{"controller": "disk-under-80", "about": "loop", "says": "loop disk-under-80 was off 90% of the time: x"}]
    snap["loops"]["disk-under-80"].pop("diagnosis_in")
    (hint,) = [a for a in state.attention(snap, True, project.model) if a["level"] == "hint"]
    assert (hint["what"], hint["says"]) == ("loop disk-under-80", "was off 90% of the time: x")


def test_a_loop_whose_valve_moves_nothing_acts_but_moves_nothing_not_more_per_run(project):
    t = time.time() - 1200
    project.events.add("ergostat.started", source="ergostat", at=t)
    for i, v in enumerate([60, 70, 80, 90, 100]):               # the stock climbs; its controller decides, its valve never opens
        project.measurements.add("sensor/disk-usage", v, at=t + 10 + i * 290)
        project.events.add("controller.decided", item="disk-under-80", source="cleaner", at=t + 20 + i * 290, data={"decision": "free 2"})
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t + 30, data={})
    (hint,) = [h for h in state.snapshot(project)["hints"] if h["controller"] == "disk-under-80"]
    assert "nothing ran to move any" in hint["says"] and "per run" not in hint["says"].lower()   # its cleaner never ran
    for i in range(4):
        project.events.add("agent.ran", item="cleaner", source="ergostat", at=t + 25 + i * 290, data={"exit": 0, "seconds": 1})
    (hint,) = [h for h in state.snapshot(project)["hints"] if h["controller"] == "disk-under-80"]
    assert "acts but moves nothing" in hint["says"] and "per run" not in hint["says"].lower()    # it ran, and moved nothing


def test_a_disturbance_that_would_run_backwards_is_not_hidden(project):
    t = time.time() - 600
    project.measurements.add("sensor/disk-usage", 80, at=t)
    project.measurements.add("sensor/disk-usage", 60, at=t + 300)        # fell 20 with no valve opening
    r = state.snapshot(project)["residuals"]["disk-used"]
    assert r["significant"] and "logs-written would have to run backwards" in r["why"]


def test_a_disturbance_may_declare_its_rate(repo):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text()
    repo.write("ergostat.toml", text.replace('into = "disk-used"', 'into = "disk-used"\nrate = 12'))
    p = Project(model.load(repo.path))
    t = time.time() - 3000
    p.measurements.add("sensor/disk-usage", 50, at=t)
    p.measurements.add("sensor/disk-usage", 56, at=t + 1800)             # half an hour at 12/h: explained
    snap = state.snapshot(p)
    assert snap["flows"]["logs-written"]["how"] == "declared" and snap["residuals"]["disk-used"]["unexplained"] == 0


def test_bad_lines_are_refused_and_unreadable_ones_counted(project, repo):
    r = run_with(project, repo, """
        import json
        print(json.dumps({"valve": "delete-old-files"}))                       # neither amount nor position
        print(json.dumps({"valve": "delete-old-files", "amount": -4}))
        print(json.dumps({"sensor": "disk-usage", "value": "7"}))               # a string, not a number
        print(json.dumps({"controller": "disk-under-80"}))                       # no decision
        print(json.dumps({"event": "spool written"}))                            # not a type name
        print(json.dumps({"event": "spool.written", "data": [1, 2]}))
        print('{"sensor": "disk-usage", "value": 1')                            # broken JSON
        print(json.dumps({"sensr": "disk-usage", "value": 1}))                   # names nothing
        print("plain text is fine")
    """)
    assert r["refused"] == 6 and r["unread"] == 2 and len(r["unread_lines"]) == 2
    assert not project.measurements.latest("sensor/disk-usage") and not project.events.query(type="valve.opened")
    snap = state.snapshot(project)
    assert snap["agents"]["cleaner"]["unread"] == 2
    assert any("could not be read" in a["says"] for a in state.attention(snap))


def test_a_run_by_hand_is_not_kept_as_a_problem(project, repo):
    repo.write("clean.py", 'import json\nprint(json.dumps({"valve": "nobodys", "amount": 1}))\n')
    runner.run_agent(project, project.model.agents["cleaner"], why="by hand")
    assert project.events.query(type="agent.refused")                         # recorded
    assert state.snapshot(project)["agents"]["cleaner"]["refused"] == 0      # but not a problem


def test_a_one_off_jump_long_ago_in_the_window_is_not_flagged(project, repo):
    text = repo.path.joinpath("ergostat.toml").read_text()
    repo.write("ergostat.toml", text.replace("[[disturbance]]", "[[flow]]").replace('into = "disk-used"', 'to = "disk-used"'))
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    t = time.time() - 3000
    values = [50, 50, 70, 70, 70, 70, 70, 70, 70, 70]               # one jump, early; flat since
    for i, v in enumerate(values):
        p.measurements.add("sensor/disk-usage", v, at=t + i * 290)
    r = state.snapshot(p)["residuals"]["disk-used"]
    assert r["unexplained"] == 20 and not r["significant"]


def test_in_and_out_disturbances_share_the_rest_by_direction(repo):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text() + '\n[[disturbance]]\nname = "departures"\nout_of = "disk-used"\n'
    repo.write("ergostat.toml", text)
    p = Project(model.load(repo.path))
    t = time.time() - 600
    p.measurements.add("sensor/disk-usage", 60, at=t)
    p.measurements.add("sensor/disk-usage", 50, at=t + 300)          # fell 10: departures, not arrivals
    snap = state.snapshot(p)
    assert snap["residuals"]["disk-used"]["absorbed_by"] == ["departures"]
    assert snap["flows"]["departures"]["rate"] > 0 and not snap["residuals"]["disk-used"]["significant"]


def test_pruning_keeps_each_loops_last_crossing(project):
    old = time.time() - 100 * 86400
    project.events.add("loop.holding", item="disk-under-80", source="ergostat", at=old - 10, data={})
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=old, data={})
    assert project.events.prune(time.time() - 30 * 86400) == 1
    assert [e["type"] for e in project.events.query(n=None, type="loop.*")] == ["loop.off"]


def test_a_bad_line_never_leaves_a_run_half_done(project, repo):
    r = run_with(project, repo, """
        import json
        print(json.dumps({"sensor": ["x"], "value": 1}))
        print('{"sensor": "disk-usage", "value": NaN}')
        print('{"sensor": "disk-usage", "value": Infinity}')
        print(json.dumps({"event": "x.y", "item": {"a": 1}}))
        print(json.dumps({"sensor": "disk-usage", "value": 5}))
    """)
    assert r["exit"] == 0 and r["refused"] == 4 and r["readings"] == 1 and not runner.LIVE
    assert project.events.query(type="agent.ran")


def test_the_timeout_runs_while_stdin_is_still_being_written(project, repo):
    repo.write("ergostat.toml", repo.path.joinpath("ergostat.toml").read_text().replace('every = "1s"', 'every = "1s"\ntimeout = "1s"'))
    from ergostat import model
    from ergostat.store import Project
    p = Project(model.load(repo.path))
    t = time.time()
    r = runner.run_agent(p, p.model.agents["cleaner"].__class__(**{**p.model.agents["cleaner"].__dict__, "command": "sleep 8"}),
                         trigger={"id": "x", "type": "big.event", "data": {"blob": "x" * 300000}})
    assert time.time() - t < 6 and r["note"] == "stopped after its timeout of 1s"


def test_one_runner_per_repository_and_a_stale_pid_file_is_not_running(project):
    runner.pid_file(project).write_text("1")                    # a pid file left by a crash: nobody holds its lock
    assert runner.running_pid(project) is None
    assert runner.take_lock(project) and runner.running_pid(project) == os.getpid()
    assert not runner.take_lock(project)                         # a second runner is refused
    runner._LOCK.close()
    runner._LOCK = None
    assert runner.running_pid(project) is None


def _with_meters(repo, n):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text()
    for i in range(n):
        text += f'\n[[sensor]]\nname = "meter{i}"\nmeasures = "cleaned"\nagent = "cleaner"\n'
    repo.write("ergostat.toml", text)
    return Project(model.load(repo.path))


def test_a_measured_flow_is_averaged_over_the_time_its_readings_cover(repo):
    p = _with_meters(repo, 1)
    now = time.time()
    for k in range(4):                                   # a steady 50/h, read every 2h: still 50/h over the last hour
        p.measurements.add("sensor/meter0", 50.0, at=now - 7200 * k - 600)
    assert abs(state.mean_rate(p, "cleaned", now - 3600, now) - 50) < 1e-6
    snap = state.snapshot(p, window=3600, now=now)
    assert abs(snap["flows"]["cleaned"]["rate"] - 50) < 1e-6


def test_two_sensors_on_one_flow_are_averaged_not_added(repo):
    p = _with_meters(repo, 2)
    now = time.time()
    for i in range(2):
        for k in range(12):
            p.measurements.add(f"sensor/meter{i}", 50.0, at=now - 300 * k - 60)
    assert abs(state.mean_rate(p, "cleaned", now - 3600, now) - 50) < 1e-6


def test_a_refused_valve_line_records_nothing(project, repo):
    r = run_with(project, repo, """
        import json
        print(json.dumps({"valve": "delete-old-files", "position": 5, "amount": -1}))
    """)
    assert r["refused"] == 1 and project.measurements.latest("valve/delete-old-files") is None


def test_a_reader_checking_the_lock_never_stops_a_runner_starting(project):
    import threading
    stop = threading.Event()

    def read():
        while not stop.is_set():
            runner.running_pid(project)
    t = threading.Thread(target=read)
    t.start()
    try:
        for _ in range(200):
            assert runner.take_lock(project)
            runner._LOCK.close()
            runner._LOCK = None
    finally:
        stop.set()
        t.join()


def test_a_reload_hands_the_lock_on(project):
    assert runner.take_lock(project)
    env = runner.keep_lock_across_exec()
    assert os.get_inheritable(int(env["ERGOSTAT_LOCK_FD"]))
    kept = os.dup(runner._LOCK.fileno())                  # as execv would: the open file outlives the old process
    runner._LOCK.close()
    runner._LOCK = None
    os.environ["ERGOSTAT_LOCK_FD"] = str(kept)
    try:
        assert runner.take_lock(project) and runner._LOCK.fileno() == kept
        assert runner.running_pid(project) == os.getpid()
    finally:
        runner._LOCK.close()
        runner._LOCK = None
        runner.RELOADED.clear()


def test_defaults_filled_in_are_not_model_edits(repo):
    from ergostat import history, model
    a = history.fingerprints(model.load(repo.path))
    text = repo.path.joinpath("ergostat.toml").read_text().replace('kind = "program"', 'kind = "person"')
    repo.write("ergostat.toml", text)
    b = history.fingerprints(model.load(repo.path))
    assert a["valve:delete-old-files"] == b["valve:delete-old-files"]       # manual by default for a person, not written
    repo.write("ergostat.toml", text.replace('flow = "cleaned"', 'flow = "cleaned"\nmode = "auto"'))
    c = history.fingerprints(model.load(repo.path))
    assert c["valve:delete-old-files"] == a["valve:delete-old-files"]       # writing the default is no change


def test_a_valves_last_opening_is_what_its_last_run_moved(project):
    ev = project.events
    ev.add("valve.opened", item="delete-old-files", source="cleaner", causedby="run-1", data={"amount": 9.0})
    for _ in range(3):
        ev.add("valve.opened", item="delete-old-files", source="cleaner", causedby="run-2", data={"amount": 2.0})
    last = ev.last_opening("delete-old-files")
    assert last["count"] == 3 and last["amount"] == 6.0
    assert ev.last_opening("nothing") is None


def test_a_plain_program_filling_one_sensor_or_valve_may_print_a_bare_number(repo):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text()
    text = text.replace('name = "disk-usage"\nmeasures = "disk-used"\nagent = "cleaner"',
                        'name = "disk-usage"\nmeasures = "disk-used"\nagent = "df"')
    text = text.replace('name = "delete-old-files"\nflow = "cleaned"\nagent = "cleaner"',
                        'name = "delete-old-files"\nflow = "cleaned"\nagent = "find"')
    text += '\n[[agent]]\nname = "df"\nkind = "program"\ncommand = "echo 71.5"\n'
    text += '\n[[agent]]\nname = "find"\nkind = "program"\ncommand = "printf \'      12\\\\n\'"\n'
    repo.write("ergostat.toml", text)
    p = Project(model.load(repo.path))
    assert runner.run_agent(p, p.model.agents["df"])["readings"] == 1
    assert p.measurements.latest("sensor/disk-usage")[1] == 71.5
    assert runner.run_agent(p, p.model.agents["find"])["openings"] == 1
    assert p.events.opened("delete-old-files", 0)["amount"] == 12
    r = runner.run_agent(p, p.model.agents["cleaner"])     # fills a controller only now: a bare number is just log
    assert r["readings"] == 0 and r["openings"] == 0


def test_a_bare_number_counts_only_when_the_run_said_no_json(repo):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text()
    text = text.replace('name = "disk-usage"\nmeasures = "disk-used"\nagent = "cleaner"',
                        'name = "disk-usage"\nmeasures = "disk-used"\nagent = "bc"')
    text += '\n[[agent]]\nname = "bc"\nkind = "program"\ncommand = "echo .50"\n'
    repo.write("ergostat.toml", text)
    p = Project(model.load(repo.path))
    assert runner.run_agent(p, p.model.agents["bc"])["readings"] == 1       # what bc prints is a number too
    assert p.measurements.latest("sensor/disk-usage")[1] == 0.5
    # the cleaner now fills a controller and a valve: its JSON lines count, a stray number does not
    repo.write("clean.py", 'import json\nprint(json.dumps({"valve": "delete-old-files", "amount": 3}))\nprint(2)\n')
    r = runner.run_agent(p, p.model.agents["cleaner"].__class__(**{**p.model.agents["cleaner"].__dict__, "command": "python3 clean.py"}))
    assert r["openings"] == 1 and p.events.opened("delete-old-files", 0)["amount"] == 3


def test_a_wrong_reading_can_be_set_aside(project):
    now = time.time()
    for i, v in enumerate([70, 71, 1.7e9, 72]):
        project.measurements.add("sensor/disk-usage", v, at=now - 300 + i * 60)
    gone = project.measurements.forget("sensor/disk-usage", above=1000)
    assert [v for _, v in gone] == [1.7e9]
    assert max(v for _, v in project.measurements.range("sensor/disk-usage", now - 600)) == 72
    assert project.measurements.forget("sensor/disk-usage", above=1000) == []


def test_a_loop_off_at_start_is_said_again_and_a_stop_is_not_a_failure(project):
    project.measurements.add("sensor/disk-usage", 95.0)
    r = runner.Runner(project, say=lambda s: None)
    r.start()
    try:
        offs = project.events.query(type="loop.off", item="disk-under-80")
        assert offs and offs[-1]["data"].get("still")
    finally:
        r.close()
        runner.STOPPING.clear()
    import sys
    repo_cmd = f"{sys.executable} -c 'import time; time.sleep(5)'"
    a = project.model.agents["cleaner"]
    slow = a.__class__(**{**a.__dict__, "command": repo_cmd})
    import threading
    t = threading.Thread(target=runner.run_agent, args=(project, slow))
    t.start()
    time.sleep(0.5)
    runner.kill_all()                                            # as ergostat's own stop does
    t.join()
    runner.STOPPING.clear()
    last = project.events.query(n=1, item="cleaner", type="agent.*")[-1]
    assert last["type"] == "agent.ran" and last["data"]["note"] == runner.STOPPED_WITH_US
    assert not state.snapshot(project)["agents"]["cleaner"]["failing"]


def test_forgetting_a_reading_forgets_the_crossing_it_caused(project, repo):
    import subprocess
    import sys
    for v in (50.0, 9999.0, 82.0):
        project.measurements.add("sensor/disk-usage", v)
        runner.edges(project, None, sensor="disk-usage")
    assert state.snapshot(project)["loops"]["disk-under-80"]["status"] == "off"      # the 9999 crossed, 82 is in the band
    env = {**os.environ}
    r = subprocess.run([sys.executable, "-m", "ergostat", "-C", str(repo.path), "sensor", "disk-usage", "--forget-above", "1000"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    snap = state.snapshot(project)
    assert snap["loops"]["disk-under-80"]["status"] == "holding" and snap["loops"]["disk-under-80"]["off_share"] < 0.05


def test_how_fast_a_loop_answers_is_measured_from_the_record(project):
    t = time.time() - 1500
    project.events.add("ergostat.started", source="ergostat", at=t)
    project.measurements.add("sensor/disk-usage", 70, at=t + 1)
    for k, (gap, back) in enumerate([(30, 60), (10, 20), (50, 300)]):
        t0 = t + 100 + k * 400
        project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t0, data={})
        project.events.add("valve.opened", item="delete-old-files", source="cleaner", at=t0 + gap, data={"amount": 1})
        project.events.add("loop.holding", item="disk-under-80", source="ergostat", at=t0 + back, data={})
    lp = state.snapshot(project)["loops"]["disk-under-80"]
    assert lp["answers_in"] == 30 and lp["back_in"] == 60 and lp["back_in_slowest"] == 300 and lp["times_off"] == 3


def test_an_agent_may_take_its_number_from_its_own_words(repo):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text()
    text = text.replace('name = "delete-old-files"\nflow = "cleaned"\nagent = "cleaner"',
                        'name = "delete-old-files"\nflow = "cleaned"\nagent = "tidy"')
    text += '\n[[agent]]\nname = "tidy"\ncommand = "echo starting; echo cleaned up 3 old files in 12s"\nparse = "cleaned up (\\\\d+)"\n'
    repo.write("ergostat.toml", text)
    p = Project(model.load(repo.path))
    r = runner.run_agent(p, p.model.agents["tidy"])
    assert r["openings"] == 1 and p.events.opened("delete-old-files", 0)["amount"] == 3 and r["printed"] == 2
    repo.write("ergostat.toml", text.replace('parse = "cleaned up (\\\\d+)"', 'parse = "no group"'))
    import pytest as _pytest
    with _pytest.raises(model.ModelError):
        model.load(repo.path)


def test_an_answer_counts_only_an_opening_while_off_and_a_spell_begun_in_the_window(project):
    t = time.time() - 3000
    project.events.add("ergostat.started", source="ergostat", at=t - 2000)
    project.measurements.add("sensor/disk-usage", 70, at=t)
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t - 1000, data={})       # before the window
    project.events.add("loop.holding", item="disk-under-80", source="ergostat", at=t + 100, data={})
    project.events.add("loop.off", item="disk-under-80", source="ergostat", at=t + 1000, data={})
    project.events.add("loop.holding", item="disk-under-80", source="ergostat", at=t + 1100, data={})     # back, no opening
    project.events.add("valve.opened", item="delete-old-files", source="cleaner", at=t + 2000, data={"amount": 1})
    lp = state.snapshot(project, window=3600)["loops"]["disk-under-80"]
    assert lp["answers_in"] is None and lp["back_in"] == 100


def test_parse_leaves_json_lines_to_json_and_a_failed_run_takes_nothing(repo):
    from ergostat import model
    from ergostat.store import Project
    text = repo.path.joinpath("ergostat.toml").read_text()
    text = text.replace('name = "disk-usage"\nmeasures = "disk-used"\nagent = "cleaner"',
                        'name = "disk-usage"\nmeasures = "disk-used"\nagent = "watch"')
    text = text.replace('name = "delete-old-files"\nflow = "cleaned"\nagent = "cleaner"',
                        'name = "delete-old-files"\nflow = "cleaned"\nagent = "watch"')
    text = text.replace('agent = "cleaner"\n\n[[valve]]', 'agent = "watch"\n\n[[valve]]')
    text += ('\n[[agent]]\nname = "watch"\ncommand = "echo freed 4; echo \'{\\"controller\\": \\"disk-under-80\\", '
             '\\"decision\\": \\"go\\"}\'"\nparse = "freed (\\\\d+)"\n')
    repo.write("ergostat.toml", text)
    m = model.load(repo.path)
    assert any("parse takes one number" in x for _, x in model.check(m))        # it fills a sensor and a valve
    p = Project(m)
    assert runner.run_agent(p, m.agents["watch"])["decisions"] == 1
