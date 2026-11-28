"""library-sandbox-sensors-proven: a sensor's ``run:`` runs on the owner's shell only when compile proved it the owner's
or ergostat's; any other runs only through ``ergostat.sandbox`` (SPEC §2a, *Untrusted libraries*). What would run is
proven here on a captured ``Policy`` and argv; that the sandbox enforces a ``Policy`` is tests/test_sandbox_attacks.py's."""

from __future__ import annotations

import json
import subprocess
import textwrap
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ergostat import sandbox
from ergostat.library import runs
from ergostat.library.expand import Via
from ergostat.remote.compose import RemoteVia
from ergostat.sensing import reads
from ergostat.spec import engine, read
from ergostat.spec.engine import callback_env, read_sensor
from ergostat.spec.ir import Ref, Sensor
from ergostat.spec.load import Where

CMD = "fetch tickets --all"


def write(root: Path, lib: dict[str, str], use: str = "l", given: str = "{}", own: dict | None = None,
          main: str = "") -> Path:
    for folder, temps in (("lib", lib), ("own", own or {})):
        (root / folder).mkdir(exist_ok=True)
        for name, text in temps.items():
            (root / folder / f"{name}.yaml").write_text(textwrap.dedent(text))
    (root / "ergostat.yaml").write_text(f"name: t\nlibrary: [{{folder: lib}}, own]\nuses:\n  u:\n    use: {use}\n"
                                        f"    with: {given}\n{main}")
    return root / "ergostat.yaml"


def compiles(path: Path):
    spec, ps = read(path)
    assert not [p for p in ps if p.level == "error"], ps
    return spec


def sensor(spec, part: str = "u-s"):
    return next(iter(spec.stocks[part].sensors.values()))


HOSTED = "template: l\nstocks:\n  s: {unit: u, sensor: {run: 'curl -s https://evil.example/n; cat n.txt'}}\n"


class Captured:
    """Stands in for ``sandbox.run``: records what it was asked to run, and answers 7."""

    def __init__(self, out: str = "7\n"):
        self.calls, self.out = [], out

    def __call__(self, argv, policy, *, stdin="", timeout=60, cwd=None):
        self.calls.append(SimpleNamespace(argv=argv, policy=policy, timeout=timeout, cwd=cwd))
        return sandbox.Result(0, self.out, "", 0.1)


@pytest.fixture
def no_shell(monkeypatch):
    """The owner's shell, refused: a run that reaches it fails the test."""
    def shell(*a, **k):
        raise AssertionError(f"ran on the owner's shell: {a}")
    monkeypatch.setattr(engine.subprocess, "run", shell)


def test_unknown_provenance_is_sandboxed(tmp_path, monkeypatch, no_shell):
    of = Ref("stock", "s")
    via = Via(tmp_path / "ergostat.yaml", 5, "l", "u")

    class Raising(dict):
        def get(self, *a):
            raise RuntimeError("unreadable")

    class Mine(Where):
        pass
    cases = {"no where": (None, {}), "a missing use": (via, {}), "a Where subclass": (Mine(tmp_path, 1), {}),
             "a remote's": (RemoteVia(tmp_path, 1, "r"), {}),
             "a raising verdict": (via, Raising(u={"untrusted": False}))}
    for case, (where, uses) in cases.items():
        assert runs.verdict(uses, where, of, "main") == runs.SANDBOX, case
    assert runs.verdict({"u": {"untrusted": True}}, via, of, "main") == runs.SANDBOX       # no proof given for it
    assert runs.verdict({"u": {"untrusted": False}}, via, of, "main") == runs.OWNER       # a trusted chain's
    assert runs.verdict({}, Where(tmp_path, 1), of, "main") == runs.OWNER                  # the model's own file
    # at run time, run_in None (a sensor compile never judged) goes to the sandbox, never the shell
    got = Captured()
    monkeypatch.setattr(sandbox, "run", got)
    spec = SimpleNamespace(uses={}, name="t", root=tmp_path)
    for where in (None, via, Mine(tmp_path, 1)):
        s = Sensor("main", of, run="echo 1", where=where)
        assert s.run_in is None and runs.sandboxed(s)
        assert read_sensor(spec, s, env={"ERGOSTAT_STATE_DIR": str(tmp_path / "state")}) == (7.0, "")
    assert len(got.calls) == 3 and all(c.policy.read == [] for c in got.calls)
    unknown = [c.cwd for c in got.calls if c.cwd.name != "u"]   # no instance: a fresh folder each run, then gone
    assert len(unknown) == 2 and unknown[0] != unknown[1] and all(c.name.startswith(runs.UNKNOWN) for c in unknown)
    assert not any(c.exists() for c in unknown)
    # compiled: a library's own run is judged sandboxed; the owner's command given whole, the owner's
    path = write(tmp_path, {"l": HOSTED})
    s = sensor(compiles(path))
    assert s.run_in == runs.SANDBOX and reads(compiles(path), s).endswith(", sandboxed")
    own = "template: l\nparams:\n  cmd: {type: command}\nstocks:\n  s: {unit: u, sensor: {run: '${cmd}'}}\n"
    path = write(tmp_path, {"l": own}, given=f"{{cmd: '{CMD}'}}")
    s = sensor(compiles(path))
    assert s.run == CMD and s.run_in == runs.OWNER and not reads(compiles(path), s).endswith("sandboxed")
    # a verdict that raises proves nothing: the owner's command, then, is sandboxed too
    monkeypatch.setattr(runs, "SECTION_OF", None)
    assert sensor(compiles(path)).run_in == runs.SANDBOX


def test_policy_captured(tmp_path, monkeypatch, no_shell):
    path = write(tmp_path, {"l": HOSTED})
    spec = compiles(path)
    s = sensor(spec)
    got = Captured()
    monkeypatch.setattr(sandbox, "run", got)
    state = tmp_path / "state"
    assert read_sensor(spec, s, env=callback_env(spec, state)) == (7.0, "")
    c = got.calls[0]
    assert c.argv == ["/bin/sh", "-c", s.run]
    assert c.policy.hosts == {} and c.policy.env == {} and c.policy.tls_unchecked == []
    assert c.policy.read == [str((tmp_path / "lib").resolve())]
    assert c.policy.work == c.cwd == state / "library-work" / "u"
    assert c.timeout == 30
    for t in (99999, float("nan"), float("inf"), 0, -5):
        s.timeout = t
        read_sensor(spec, s, env=callback_env(spec, state))
        assert got.calls[-1].timeout == runs.CEILING, t


def test_slot_check_and_take_hold_one_lock(monkeypatch):
    monkeypatch.setattr(runs, "MOST", 1)
    monkeypatch.setattr(runs, "_held", [0])
    room, second = runs._room, {}

    def take_second():
        with runs._slot() as slot:
            second["slot"] = slot

    def window():                      # between the first's check and its take, a second starts
        free = room()
        t = threading.Thread(target=take_second, daemon=True)
        t.start()
        t.join(0.3)
        return free

    monkeypatch.setattr(runs, "_room", window)
    with runs._slot() as first:
        monkeypatch.setattr(runs, "_room", room)
        assert first is not None
        for _ in range(50):
            if "slot" in second:
                break
            threading.Event().wait(0.05)
        assert second == {"slot": None}            # refused: the first had taken the only slot
    assert runs._held == [0]
    with runs._slot() as slot:                     # an escaped run keeps its slot
        slot.keep = True
    with runs._slot() as slot:
        assert slot is None


def test_no_sandbox_no_run(tmp_path, monkeypatch, no_shell):
    made = tmp_path / "ran"
    path = write(tmp_path, {"l": f"template: l\nstocks:\n  s: {{unit: u, sensor: {{run: 'touch {made}; echo 3'}}}}\n"})
    spec = compiles(path)
    s = sensor(spec)
    monkeypatch.setattr(sandbox, "backend", lambda: None)
    monkeypatch.setattr(sandbox.subprocess, "Popen", lambda *a, **k: pytest.fail("a process was started"))
    v, why = read_sensor(spec, s, env=callback_env(spec, tmp_path / "state"))
    assert v is None and why.startswith("not run: no OS sandbox"), why
    assert not made.exists()
    # through the engine's own reading: a sensor.failed, and no measurement
    added, events = [], []
    eng = SimpleNamespace(spec=spec, socket=None, lock=threading.Lock(), reading={s.series}, dirty_series=set(),
                          read_cause={}, say=lambda m: None, evaluate=lambda c=None: None,
                          _observer=lambda n: None, read_back=lambda s, failed=False: None,
                          p=SimpleNamespace(dir=tmp_path / "state", events=SimpleNamespace(add=lambda *a, **k: events.append(a)),
                                            measurements=SimpleNamespace(add=lambda *a: added.append(a))))
    engine.Engine._read(eng, s)
    assert added == [] and [e[0] for e in events] == ["sensor.failed"] and not made.exists()


NEST = "template: {name}\nuses:\n  in:\n    use: inner\n"
INNER = "template: inner\nstocks:\n  s: {unit: u, sensor: {run: 'cat n.txt'}}\n"


def test_nested_remake_under_another_library_clears_work_folder(tmp_path):
    lib = {"a": NEST.format(name="a"), "b": NEST.format(name="b"), "inner": INNER}
    state = tmp_path / "state"

    def folder(use):
        spec = compiles(write(tmp_path, lib, use=use))
        assert sensor(spec, "u-in-s").run_in == runs.SANDBOX and spec.uses["u-in"]["above"] == "u"
        (work / "kept").write_text("1")
        for name in ("u-in.made", "marker", ".made"):    # the marker the new chain would leave, forged inside
            (work / name).write_text(json.dumps(runs.chain(spec.uses, "u-in")))
        return runs.work_folder(spec.uses, state, "u-in")

    work = runs.work_folder({}, state, "u-in")
    assert folder("a") == work and not (work / "kept").exists()      # made under another chain: cleared
    assert (folder("a") / "kept").exists()               # the same chain: kept
    assert not (folder("b") / "kept").exists()           # the library above it switched: cleared
    lib["b"] = NEST.format(name="b") + "description: changed\n"
    assert not (folder("b") / "kept").exists()           # its file changed: cleared
    lib["inner"] = INNER + "description: changed\n"
    assert not (folder("b") / "kept").exists()           # the nested template's own file changed: cleared
    assert (folder("b") / "kept").exists()
    with pytest.raises(ValueError):
        runs.work_folder({}, state, "../x")


def test_long_instance_name_has_its_own_work_folder(tmp_path, monkeypatch, no_shell):
    """A name past 64 chars gets a folder of its own (a digest), cleared when the library above it switches."""
    long, other = "u" + "-x" * 40, "v" + "-x" * 40
    got = Captured()
    monkeypatch.setattr(sandbox, "run", got)
    state = tmp_path / "state"

    def run(use: str, inst: str = long):
        (tmp_path / "lib").mkdir(exist_ok=True)
        for name in ("a", "b"):
            (tmp_path / "lib" / f"{name}.yaml").write_text(HOSTED.replace("template: l", f"template: {name}"))
        (tmp_path / "ergostat.yaml").write_text(f"name: t\nlibrary: [{{folder: lib}}]\nuses:\n  {inst}:\n    use: {use}\n")
        spec = compiles(tmp_path / "ergostat.yaml")
        s = sensor(spec, f"{inst}-s")
        assert s.run_in == runs.SANDBOX and read_sensor(spec, s, env=callback_env(spec, state)) == (7.0, "")
        return got.calls[-1].cwd
    work = run("a")
    assert work.parent == state / "library-work" and work.name.startswith("0-") and work.name != runs.UNKNOWN
    (work / "planted").write_text("1")
    assert run("a") == work and (work / "planted").exists()           # the same chain: kept
    assert run("b") == work and not (work / "planted").exists()       # the library above it switched: cleared
    (work / "planted").write_text("1")
    assert run("a", other) != work and (work / "planted").exists()    # another long name: another folder
    with pytest.raises(ValueError):
        runs.work_folder({}, state, "a" * 70 + "/../x")


def test_owner_file_sensor_runs_as_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "run", lambda *a, **k: pytest.fail("sandboxed"))
    (tmp_path / "ergostat.yaml").write_text("name: t\nstocks:\n  s:\n    unit: u\n    sensor: "
                                            "{run: 'test -n \"$ERGOSTAT_STATE_DIR\" && echo 3'}\n")
    spec = compiles(tmp_path / "ergostat.yaml")
    s = spec.stocks["s"].sensors["main"]
    assert s.run_in == runs.OWNER and not reads(spec, s).endswith("sandboxed")
    assert read_sensor(spec, s, env=callback_env(spec, tmp_path / "state")) == (3.0, "")


def test_sandboxed_run_cannot_relay_a_message(tmp_path, monkeypatch):
    spec = compiles(write(tmp_path, {"l": HOSTED}))
    monkeypatch.setattr(sandbox, "run", Captured('{"message": {"text": "hi"}}\n{"type": "k.seen", "item": "k-1"}\n5\n'))
    got = []
    v, _ = read_sensor(spec, sensor(spec), observe=lambda seen, refused: got.append((seen, refused)),
                       env=callback_env(spec, tmp_path / "state"))
    assert v == 5.0 and not [o for o in got[0][0] if "message" in o]
    assert got[0][1] == ["message: a sandboxed run cannot relay a message"]


def test_library_daemon_refused_unsandboxed(tmp_path):
    path = write(tmp_path, {"l": "template: l\nauxiliaries:\n  a: {sensor: {daemon: x}}\n"})
    _, ps = read(path)
    assert [p.code for p in ps if p.level == "error"] == ["library-unsandboxed"]


# ---- live: these run only where an OS sandbox can start (they skip without one, and say so)


@pytest.fixture
def live():
    if sandbox.backend() is None:
        pytest.skip("no OS sandbox here (bwrap, sandbox-exec)")
    if sandbox.backend() == "bwrap" and subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "true"],
                                                       capture_output=True).returncode:
        pytest.skip("bwrap cannot make its namespaces here")


def live_read(tmp_path, run: str):
    spec = compiles(write(tmp_path, {"l": f"template: l\nstocks:\n  s: {{unit: u, sensor: {{run: '{run}'}}}}\n"}))
    return read_sensor(spec, sensor(spec), env=callback_env(spec, tmp_path / "state"))


def test_live_reads_its_template_folder(tmp_path, live):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "n.txt").write_text("11\n")
    assert live_read(tmp_path, f"cat {tmp_path / 'lib' / 'n.txt'}") == (11.0, "")


def test_live_cannot_read_the_owners_files(tmp_path, live):
    (tmp_path / "secret.txt").write_text("42\n")
    v, why = live_read(tmp_path, f"cat {tmp_path / 'secret.txt'}")
    assert v is None and "exited" in why


def test_live_has_no_callback_environment(tmp_path, live):
    assert live_read(tmp_path, "test -z \"$ERGOSTAT_STATE_DIR$ERGOSTAT_SOCKET\" && echo 1")[0] == 1.0


def test_live_work_folder_kept_between_readings(tmp_path, live):
    run = "echo x >> seen; wc -l < seen"
    assert live_read(tmp_path, run)[0] == 1.0
    assert live_read(tmp_path, run)[0] == 2.0
