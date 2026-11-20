"""scripts/in_container.sh and compose.yaml: the hard limits and the mounts a container run gets (docs/DEVELOPMENT.md).
Docker is not needed: the script's --print shows what it would run."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "in_container.sh"
pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="needs git")


def printed(*args, **env) -> tuple[dict, str]:
    full = {k: v for k, v in os.environ.items() if not k.startswith("ERGOSTAT_")} | env
    out = subprocess.run(["sh", str(SCRIPT), "--print", *args], capture_output=True, text=True, env=full, check=True).stdout
    lines = out.strip().splitlines()
    return dict(ln.split("=", 1) for ln in lines[:-1]), lines[-1]


def test_compose_sets_the_hard_limits_and_no_network():
    dev = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]["dev"]
    assert dev["pids_limit"] == "${ERGOSTAT_PIDS:-4096}"
    assert dev["mem_limit"] == dev["memswap_limit"] == "${ERGOSTAT_MEM:-12g}"
    assert dev["init"] is True and dev["network_mode"] == "${ERGOSTAT_NET:-none}"
    assert any(t.startswith("/tmp:") for t in dev["tmpfs"]) and "${ERGOSTAT_WORK:-.}:/work" in dev["volumes"]


def test_the_command_runs_in_the_dev_service_with_half_the_cpus():
    env, cmd = printed("uv", "run", "python", "-m", "pytest", "-q")
    assert cmd.endswith(" dev uv run python -m pytest -q") and " run --rm " in cmd
    host = os.cpu_count() or 2
    assert 1 <= int(env["ERGOSTAT_CPUS"]) <= max(1, host // 2)
    assert env["ERGOSTAT_WORK"] == str(ROOT) and "ERGOSTAT_NET" not in env


def test_settings_and_net_pass_through():
    env, cmd = printed("--net", "true", ERGOSTAT_CPUS="3", ERGOSTAT_MEM="6g")
    assert env["ERGOSTAT_CPUS"] == "3" and env["ERGOSTAT_MEM"] == "6g" and env["ERGOSTAT_NET"] == "bridge"
    assert cmd.endswith(" dev true")


def test_a_worktree_gets_its_git_directory_mounted_at_the_same_path(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q", str(main)], check=True)
    subprocess.run([*git, "-C", str(main), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    subprocess.run([*git, "-C", str(main), "worktree", "add", "-q", str(wt)], check=True)
    common = str((main / ".git").resolve())
    env, cmd = printed("true", ERGOSTAT_WORK=str(wt), ERGOSTAT_CPUS="1")
    assert env["ERGOSTAT_WORK"] == str(wt.resolve()) and f"-v {common}:{common} dev true" in cmd
    _, cmd = printed("true", ERGOSTAT_WORK=str(main), ERGOSTAT_CPUS="1")
    assert " -v " not in cmd
