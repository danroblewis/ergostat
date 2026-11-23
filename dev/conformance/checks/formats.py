"""The checks of the model-formats conformance list (``dev/conformance/model-formats.yaml``).

``python3 dev/conformance/checks/formats.py CASE [ROOT]``: exit 0 met, 1 unmet, 2 broken (the check itself could not
say). A feature that is absent, or that fails, is unmet; only the check's own failure is broken. ROOT (default: this
repository) is where ``examples/`` and ``tests/fixtures/toml/`` are read, so a broken copy can be checked."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
SQUEEZE = "examples/image-squeeze/ergostat.yaml"
SMALL = Path(__file__).resolve().parent / "fixtures" / "small.xmile"
NS = "{http://docs.oasis-open.org/xmile/ns/XMILE/v1.0}"
EXPORTS = ("export", "to_xmile", "write")                     # the export gap's module is ergostat/xmile.py
IMPORTS = (("ergostat.xmile", ("draft", "from_xmile")), ("ergostat.spec.discover", ("from_xmile",)))


class Unmet(Exception):
    pass


def ergostat(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")])}
    return subprocess.run([sys.executable, "-m", "ergostat", *args], capture_output=True, text=True, env=env,
                          timeout=120)


def tail(r: subprocess.CompletedProcess) -> str:
    return " | ".join((r.stdout + r.stderr).strip().splitlines()[-3:])


def found(paths: list[Path], what: str) -> list[Path]:
    if not paths:                                    # nothing to check is the check's failure, never met
        raise RuntimeError(f"no {what}")
    return paths


def ergostat_yaml(root: Path) -> None:
    bad = []
    for p in found(sorted((root / "examples").glob("*/ergostat.yaml")), f"examples/*/ergostat.yaml in {root}"):
        r = ergostat("-C", str(p.parent), "check", "--no-coherence")      # (coherence reads a machine's record)
        if r.returncode:
            bad.append(f"{p.parent.name}: exit {r.returncode}: {tail(r)}")
    if bad:
        raise Unmet("; ".join(bad))


def ergostat_toml(root: Path) -> None:
    from ergostat.spec import read
    bad = []
    for toml in found(sorted((root / "tests/fixtures/toml").glob("*.toml")), f"tests/fixtures/toml/*.toml in {root}"):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / toml.stem
            d.mkdir()
            shutil.copy(toml, d / "ergostat.toml")
            r = ergostat("-C", str(d), "convert")
            if r.returncode or not (d / "ergostat.yaml").is_file():
                bad.append(f"{toml.stem}: convert exit {r.returncode}: {tail(r)}")
                continue
            errors = [str(p) for p in read(d / "ergostat.yaml")[1] if p.level == "error"]
            if errors:
                bad.append(f"{toml.stem}: {'; '.join(errors[:3])}")
    if bad:
        raise Unmet("; ".join(bad))


def compiled(root: Path):
    from ergostat.spec import read
    spec, problems = read(root / SQUEEZE)
    errors = [str(p) for p in problems if p.level == "error"]
    if errors or not spec.stocks:
        raise RuntimeError(f"{SQUEEZE} does not compile: {errors[:3]}")
    return spec


def served_model(root: Path) -> None:
    from ergostat.remote import serve
    from ergostat.spec.load import load
    stocks = set(compiled(root).stocks)
    answer = serve.document(load(root / SQUEEZE), "conformance")
    if answer.get("format") != "ergostat-model/1":
        raise Unmet(f"the served answer says format {answer.get('format')!r}")
    missing = stocks - set((answer.get("sections") or {}).get("stocks") or {})
    if missing:
        raise Unmet(f"the served answer leaves out stocks {sorted(missing)}")


def norm(name: str) -> str:
    return re.sub(r"[-_\s]+", "_", name.strip().lower())


def xmile_export(root: Path) -> None:
    if importlib.util.find_spec("ergostat.xmile") is None:
        raise Unmet("no XMILE export: ergostat/xmile.py does not exist")
    mod = importlib.import_module("ergostat.xmile")
    fn = next((getattr(mod, n) for n in EXPORTS if callable(getattr(mod, n, None))), None)
    if fn is None:                                   # the module is there, the check does not know its call
        raise RuntimeError(f"ergostat.xmile has none of {EXPORTS}: update this check")
    spec = compiled(root)
    out = fn(spec)
    top = out if isinstance(out, ET.Element) else ET.fromstring(out)
    if top.tag != f"{NS}xmile":
        raise Unmet(f"the root is {top.tag}, not XMILE 1.0's {NS}xmile")
    for kind, want in (("stock", spec.stocks), ("flow", spec.flows)):
        got = sorted(norm(e.get("name", "")) for e in top.iter(f"{NS}{kind}"))
        if got != sorted(norm(n) for n in want):
            raise Unmet(f"<{kind}> elements {got} are not one per {kind} {sorted(want)}")
    names = [n for s in ("stocks", "flows", "auxiliaries", "parameters") for n in getattr(spec, s) if "-" in n]
    for e in top.iter(f"{NS}eqn"):
        text = e.text or ""
        odd = re.findall(r"\b(?:stock|flow|auxiliary|parameter|goal|block)\.[\w-]+|\$\{", text) + [
            n for n in names if re.search(rf"(?<![\w.-]){re.escape(n)}(?![\w-])", text)]
        if odd:
            raise Unmet(f"<eqn>{text}</eqn> has ergostat-only syntax: {odd}")


def signed(refs) -> set[str]:
    refs = refs if isinstance(refs, list) else [refs] if refs else []
    out = set()
    for r in refs:
        r = str(r.get("cause", "") if isinstance(r, dict) else r).strip()
        sign, r = (r[0], r[1:]) if r[:1] in ("+", "-") else ("?", r)
        out.add(sign + norm(r.split(".", 1)[-1]))
    return out


def xmile_import(root: Path) -> None:
    import yaml
    fn = None
    for mod, names in IMPORTS:
        if importlib.util.find_spec(mod) is not None:
            m = importlib.import_module(mod)
            fn = fn or next((getattr(m, n) for n in names if callable(getattr(m, n, None))), None)
    if fn is None:
        raise Unmet("no XMILE importer: none of " + ", ".join(f"{m}.{n}" for m, ns in IMPORTS for n in ns))
    out = fn(SMALL.read_text())
    out = out[0] if isinstance(out, tuple) else out
    draft = out if isinstance(out, dict) else yaml.safe_load(out)
    stocks, flows = draft.get("stocks") or {}, draft.get("flows") or {}
    if sorted(map(norm, stocks)) != ["backlog", "done"]:
        raise Unmet(f"the draft's stocks are {sorted(stocks)}, not backlog and done")
    work = {norm(k): v for k, v in flows.items()}.get("work") if len(flows) == 1 else None
    if not isinstance(work, dict) or (norm(str(work.get("from"))), norm(str(work.get("to")))) != ("backlog", "done"):
        raise Unmet(f"the draft's flows are {flows}, not one flow work from backlog to done")
    if signed(work.get("driven-by")) != {"+backlog", "-done"}:
        raise Unmet(f"flow work is driven by {work.get('driven-by')}, not +stock.backlog and -stock.done")


CASES = {"ergostat-yaml": ergostat_yaml, "ergostat-toml": ergostat_toml, "served-model": served_model,
         "xmile-export": xmile_export, "xmile-import": xmile_import}


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2) or argv[0] not in CASES:
        print(f"usage: formats.py {{{','.join(CASES)}}} [ROOT]", file=sys.stderr)
        return 2
    try:
        CASES[argv[0]](Path(argv[1]).resolve() if len(argv) > 1 else ROOT)
    except Unmet as e:
        print(f"unmet: {e}")
        return 1
    except Exception as e:                           # the check's own failure: broken, never unmet
        print(f"broken: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print("met")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
