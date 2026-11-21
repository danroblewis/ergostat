"""Break each guard and run the tests that should catch it; restore the file after. (Not committed.)"""
import subprocess
from pathlib import Path

T = "tests/test_mirror.py::"
M = [
    ("string order of int positions", "ergostat/mirror.py", "        return int(value)\n", "        return value\n",
     ["test_position_types_and_order", "test_the_confirmed_cursor_crosses_9_to_10"]),
    ("recorded orders by text", "ergostat/mirror.py", "key(t, pos, best[0], log) > best[1]", "str(pos) > str(best[1])",
     ["test_lost_memory_resumes_after_10_not_9"]),
    ("no rollup cites", "ergostat/rollup.py", "    if cites:  ", "    if False:  ", ["test_lost_memory_after_rollup_keeps_the_cite"]),
    ("collector skips position check", "ergostat/library/run/collect.py", "                pos = mi.position(raw, want)\n",
     "                pos = raw\n", ["test_a_position_the_engine_would_refuse_fails_the_poll_with_its_reason"]),
    ("cursor moved on saying", "ergostat/library/run/collect.py", "    m[\"said\"] = [entries[x][\"id\"] for x in new]\n",
     "    m[\"said\"] = []\n    m[\"cursor\"] = new[-1] if new else cursor\n",
     ["test_a_said_position_not_recorded_fails_the_next_poll_then_is_read_again"]),
    ("said not cleared", "ergostat/library/run/collect.py", "        m[\"said\"] = []\n", "        pass\n",
     ["test_a_said_position_not_recorded_fails_the_next_poll_then_is_read_again"]),
    ("valid has no log check", "ergostat/mirror.py", "return None if log == sensor else", "return None if True else",
     ["test_the_engine_refuses_a_cite_of_another_sensor_s_log"]),
    ("recorded drops source filter", "ergostat/mirror.py", "for e in page if e.get(\"source\") == sensor)", "for e in page)",
     ["test_lost_memory_reads_only_this_sensor_s_cites"]),
    ("greatest drops log check", "ergostat/mirror.py", "if lg == log and (best", "if (best",
     ["test_lost_memory_reads_only_this_sensor_s_cites"]),
    ("no envelope check", "ergostat/intake/envelope.py", "str(e[\"id\"]).startswith(PREFIX)", "False",
     ["test_push_refuses_a_cite_id", "test_a_webhook_refuses_a_cite_id", "test_the_socket_event_op_refuses_a_cite_id"]),
    ("observations pass any id", "ergostat/spec/engine.py",
     "cited = isinstance(obj.get(\"id\"), str) and obj[\"id\"].startswith(mirror.PREFIX)",
     "cited = obj.get(\"id\") is not None", ["test_a_sensor_line_with_a_plain_id_is_recorded_as_on_main"]),
    ("no went-back check", "ergostat/library/run/collect.py", "            if top < cursor:", "            if False:",
     ["test_a_log_that_went_back_stops_the_mirror"]),
    ("no restart check", "ergostat/library/run/collect.py", "and _same(was) != _same(entries[cursor])", "and False",
     ["test_a_restarted_log_that_grew_past_the_cursor_stops_the_mirror"]),
    ("key coerces", "ergostat/mirror.py", "    if other is not None and other != type:", "    if False:",
     ["test_mixed_position_types_in_the_record_fail_closed"]),
    ("no ceiling", "ergostat/library/run/collect.py", "if cursor is None or x > cursor)[:MOST]", "if cursor is None or x > cursor)",
     ["test_at_most_5000_entries_a_poll"]),
    ("no ERGOSTAT_SENSOR", "ergostat/spec/engine.py", "\"ERGOSTAT_SENSOR\": sensor_name(s.of.name, s.name)", "\"X\": \"\"",
     ["test_mirror_end_to_end_through_the_engine"]),
    ("recovery error as nothing", "ergostat/library/run/collect.py", "            got = mi.recorded(p.events, log)",
     "            try:\n                got = mi.recorded(p.events, log)\n            except Exception:\n                got = None",
     ["test_a_store_error_while_recovering_fails_the_poll"]),
]
for name, f, old, new, tests in M:
    p = Path(f)
    text = p.read_text()
    assert text.count(old) == 1, (name, text.count(old))
    p.write_text(text.replace(old, new))
    try:
        r = subprocess.run(["uv", "run", "python", "-m", "pytest", "-q", *[T + t for t in tests]],
                           capture_output=True, text=True)
        last = r.stdout.strip().splitlines()[-1]
        print(f"{'CAUGHT' if r.returncode else 'MISSED'}  {name}: {last}", flush=True)
    finally:
        p.write_text(text)
