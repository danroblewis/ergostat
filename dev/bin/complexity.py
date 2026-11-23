"""The code's complexity, measured on a git ref once per commit (dev/records/cx-measure-frame.md).

    complexity.py measure [SHA] [--family F]   compute what the commit file lacks (default: [git] base, resolved once)
    complexity.py value NAME [SHA]             the reading at the newest measured first parent at or before SHA
    complexity.py history NAME [--last N]      seq sha at value, per measured first parent of the base
    complexity.py rows [SHA] | list [--json] | report NAME [SHA] [--json]

Read from the ref (`git ls-tree -r`, then a `git cat-file --batch` per family for the blobs its cache lacks), never
the working files; one git child at a time.
Under `<run>/complexity/`: `commits/<sha>.json` (atomic rename), `blobs/<family>-v<VERSION>-<env>.jsonl` (keyed by
blob alone: a blob is measured once in all history) and `locks/<family>`, held across a family's read, compute and
write. A family is a sibling `cx_<family>.py` (the contract: the record, point 6); a change to its `EVERY` needs a new
`VERSION`. `value` never computes: a failed family at the newest measured commit is no value (exit 1), never an older
reading; a skipped one (off its stride) is passed over. It only measures and prints: it writes no record."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRIES = 3
CODE = ("product", "factory", "scripts")
AREAS = (("ergostat/", "product"), ("dev/bin/", "factory"), ("scripts/", "scripts"), ("tests/", "tests"),
         ("examples/", "examples"), ("docs/", "docs"))
STATIC = "ergostat/web/static/"
VENDORED = tuple(STATIC + p for p in ("elk.bundled.js", "highlight.min.js", "libavoid/", "uplot/", "marked.min.js"))
LANGS = {".py": "python", ".js": "javascript", ".css": "css", ".html": "html", ".md": "markdown", ".yaml": "yaml",
         ".yml": "yaml", ".toml": "toml", ".sh": "shell", ".json": "json", ".txt": "text"}
SHA = re.compile(r"[0-9a-f]{40}")


class Missing(RuntimeError):
    """What cannot be read: no value is made of it."""


def families(where: Path = HERE) -> dict:
    out = {}
    for p in sorted(where.glob("cx_*.py")):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out[p.stem[3:]] = mod
    return out


def version(f) -> int:
    return int(getattr(f, "VERSION", 0))


def env(f) -> str:
    return str(f.ENV()) if hasattr(f, "ENV") else ""


def series(f) -> dict:
    return getattr(f, "SERIES", {})


class Ctx:
    """Where a measure reads (a git repository) and keeps its cache, and the families it knows."""

    def __init__(self, repo: Path, run: Path, fams: dict):
        self.repo, self.run, self.families = repo, run, fams
        for d in ("commits", "blobs", "locks"):
            (run / d).mkdir(parents=True, exist_ok=True)

    def git(self, *args: str, stdin: bytes | None = None) -> bytes:
        r = subprocess.run(["git", "-C", str(self.repo), *args], input=stdin, capture_output=True, timeout=600)
        if r.returncode:
            raise Missing(f"git {' '.join(args[:2])}: {r.stderr.decode(errors='replace').strip()[-300:]}")
        return r.stdout

    def load(self, sha: str) -> dict | None:
        if not SHA.fullmatch(sha):
            raise ValueError(f"not a full sha: {sha!r}")
        try:
            return json.loads((self.run / "commits" / f"{sha}.json").read_text())
        except FileNotFoundError:
            return None

    @contextmanager
    def lock(self, name: str):
        with open(self.run / "locks" / name, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            yield


def tree(ctx: Ctx, sha: str) -> list[tuple[str, str]]:
    out = []
    for entry in ctx.git("ls-tree", "-r", "-z", sha).split(b"\0"):
        if entry:
            meta, path = entry.split(b"\t", 1)
            mode, kind, blob = meta.decode().split()
            if kind == "blob" and mode != "120000":
                out.append((path.decode(errors="replace"), blob))
    return out


def read(ctx: Ctx, blobs) -> dict[str, bytes]:
    blobs = sorted(set(blobs))
    if not blobs:
        return {}
    out, i, got = ctx.git("cat-file", "--batch", stdin="".join(b + "\n" for b in blobs).encode()), 0, {}
    for b in blobs:
        end = out.index(b"\n", i)
        head = out[i:end].split()
        if len(head) != 3:
            raise Missing(f"blob {b}: {out[i:end].decode(errors='replace')}")
        got[b], i = out[end + 1:end + 1 + int(head[2])], end + 2 + int(head[2])
    return got


def fill(ctx: Ctx, name: str, f, files: list, texts: dict) -> dict:
    """A family's per-file measures of these blobs: from its cache, the rest measured now and appended (the caller
    holds the family's lock)."""
    if not hasattr(f, "per_file"):
        return {}
    path, got = ctx.run / "blobs" / f"{name}-v{version(f)}-{re.sub(r'[^A-Za-z0-9.]+', '_', env(f))}.jsonl", {}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
                got[r["blob"]] = r["m"]
            except (ValueError, KeyError, TypeError):
                pass                                        # a torn line: that blob is measured again
    todo = {b: p for p, b in files if b not in got}
    texts.update(read(ctx, [b for b in todo if b not in texts]))
    with open(path, "a") as out:
        for blob, p in todo.items():
            got[blob] = f.per_file(p, texts[blob].decode(errors="replace"))
            out.write(json.dumps({"blob": blob, "m": got[blob]}) + "\n")
    return got


def slices(path: str) -> dict:
    area = next((a for p, a in AREAS if path.startswith(p)), "other")
    rest = path.removeprefix("ergostat/")
    suffix = Path(path).suffix.lower()
    return {"path": path, "area": area, "lang": LANGS.get(suffix, suffix.lstrip(".") or "none"),
            "package": ("top" if "/" not in rest else rest.split("/")[0]) if area == "product" else "",
            "vendored": path.startswith(VENDORED) or (path.startswith(STATIC) and suffix == ".wasm")}


class Snap:
    """One commit as a family sees it: its rows (these families' per-file measures) and what it may ask of git."""

    def __init__(self, ctx: Ctx, sha: str, seq: int, at: int, files: list, texts: dict, fams: dict):
        self.ctx, self.sha, self.seq, self.at, self._texts, self._blob = ctx, sha, seq, at, texts, dict(files)
        ms = [fill(ctx, n, f, files, texts) for n, f in fams.items()]
        self.rows = []
        for path, blob in files:
            row = {**slices(path), "blob": blob}
            for f in fams.values():
                row.update({k: str(v) for k, v in f.keys(path).items()} if hasattr(f, "keys") else {})
            row["m"] = {k: v for m in ms for k, v in m.get(blob, {}).items()}
            self.rows.append(row)

    def text(self, path: str) -> str:
        return self.texts([path])[path]

    def texts(self, paths) -> dict[str, str]:
        """These files' text, the blobs not read yet read in one git child."""
        self._texts.update(read(self.ctx, [self._blob[p] for p in paths if self._blob[p] not in self._texts]))
        return {p: self._texts[self._blob[p]].decode(errors="replace") for p in paths}

    def git(self, *args: str) -> str:
        return self.ctx.git(*args).decode()

    def sum(self, measure: str, **where) -> float:
        def ok(row):
            return all(row.get(k) in v if isinstance(v, tuple | list | set) else row.get(k) == v for k, v in where.items())
        return sum(r["m"][measure] for r in self.rows if not r["vendored"] and measure in r["m"] and ok(r))

    def commit(self, sha: str) -> dict | None:
        return self.ctx.load(sha)

    def first_parents(self, n: int) -> list[str]:
        return self.git("rev-list", "--first-parent", f"-n{int(n)}", self.sha).split()


def stamp(ctx: Ctx, sha: str) -> tuple[int, int]:
    return int(ctx.git("rev-list", "--count", "--first-parent", sha)), int(ctx.git("show", "-s", "--format=%ct", sha))


def measure(ctx: Ctx, sha: str, only: str | None = None) -> dict:
    """Each family apart, under its own lock: computed when its entry is missing, of another version or env, or
    failed fewer than TRIES times; skipped off its stride. The others' entries stand."""
    (seq, at), files, texts = stamp(ctx, sha), tree(ctx, sha), {}
    for name, f in ctx.families.items():
        if only not in (None, name):
            continue
        with ctx.lock(name):
            old = ((ctx.load(sha) or {}).get("families") or {}).get(name)
            same = bool(old) and old["version"] == version(f) and old["env"] == env(f)
            if same and (old["state"] != "failed" or old["tries"] >= TRIES):
                continue
            entry = {"version": version(f), "env": env(f), "state": "skipped", "error": None,
                     "tries": old["tries"] if same else 0, "seconds": 0}
            values, detail, t0 = {}, None, time.monotonic()
            if seq % max(1, int(getattr(f, "EVERY", 1))) == 0:
                entry["tries"] += 1
                try:
                    snap = Snap(ctx, sha, seq, at, files, texts, {name: f})
                    values = dict(f.per_commit(snap)) if hasattr(f, "per_commit") else {}
                    detail = values.pop("detail", None)
                    for k, v in values.items():
                        if k not in series(f) or isinstance(v, bool) or not isinstance(v, int | float) \
                                or not math.isfinite(v):
                            raise ValueError(f"{k}={v!r}: not a declared series with a finite number")
                    entry["state"] = "ok"
                except Exception as e:                      # (the family's own failure, recorded; the others stand)
                    entry.update(state="failed", error=f"{type(e).__name__}: {e}"[:500])
                    values, detail = {}, None
                entry["seconds"] = round(time.monotonic() - t0, 3)
            merge(ctx, sha, seq, at, name, entry, values, detail)
    return ctx.load(sha)


def merge(ctx: Ctx, sha: str, seq: int, at: int, name: str, entry: dict, values: dict, detail) -> None:
    """One family's entry into the commit file, under a short lock: its old series (and any no family declares) out."""
    path, declared = ctx.run / "commits" / f"{sha}.json", {s for f in ctx.families.values() for s in series(f)}
    with ctx.lock(".commits"):
        doc = ctx.load(sha) or {"v": 1, "sha": sha, "seq": seq, "at": at, "families": {}, "values": {}, "detail": {}}
        mine = series(ctx.families[name])
        doc["values"] = {k: v for k, v in doc["values"].items() if k in declared and k not in mine} | values
        doc["families"][name] = entry
        doc["detail"].pop(name, None)
        if detail is not None:
            doc["detail"][name] = detail
        tmp = path.with_name(f".{sha}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(doc, sort_keys=True))
        os.replace(tmp, path)


def value(ctx: Ctx, name: str, sha: str) -> tuple[str, float]:
    owner = next((n for n, f in ctx.families.items() if name in series(f)), None)
    if owner is None:
        raise Missing("not a series of any family")
    for c in ctx.git("rev-list", "--first-parent", sha).decode().split():
        doc = ctx.load(c)
        entry = (doc or {}).get("families", {}).get(owner)
        if not entry or entry["state"] == "skipped":
            continue
        if entry["state"] != "ok":
            raise Missing(f"{owner} {entry['state']} at {c}: {entry['error']}")
        if name not in doc["values"]:
            raise Missing(f"{owner} gave none at {c}")
        return c, doc["values"][name]
    raise Missing(f"no first parent at or before {sha[:12]} measured by {owner}")


def history(ctx: Ctx, name: str, base: str) -> list[tuple]:
    on = set(ctx.git("rev-list", "--first-parent", base).decode().split())
    docs = [ctx.load(p.stem) for p in (ctx.run / "commits").glob("*.json") if p.stem in on]
    return sorted((d["seq"], d["sha"], d["at"], d["values"][name]) for d in docs if name in d["values"])


def snapshot(ctx: Ctx, sha: str, fams: dict) -> Snap:
    with ExitStack() as held:
        for n in fams:                                      # (in name order, as measure takes them one at a time)
            held.enter_context(ctx.lock(n))
        return Snap(ctx, sha, *stamp(ctx, sha), tree(ctx, sha), {}, fams)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="complexity.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("measure", "value", "history", "rows", "list", "report"))
    ap.add_argument("args", nargs="*", metavar="[NAME] [SHA]")
    ap.add_argument("--family")
    ap.add_argument("--last", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    a, fams = ap.parse_args(argv), families()
    named = int(a.cmd in ("value", "history", "report"))
    if not named <= len(a.args) <= named + (a.cmd not in ("history", "list")):
        ap.error(f"{a.cmd} {'NAME ' * named}{'[SHA]' if a.cmd not in ('history', 'list') else ''}")
    name = a.args[0] if named else a.cmd

    def show(row: dict) -> None:
        print(json.dumps(row) if a.json else "\t".join(map(str, row.values())))
    if a.cmd == "list":
        for fam, f in fams.items():
            for n, s in series(f).items():
                show({"name": n, "unit": s["unit"], "family": fam, "part": bool(s["part"]), "description": s["description"]})
        return 0
    sys.path.insert(0, str(HERE))
    import fac
    cfg = fac.config()
    ctx = Ctx(fac.path(cfg, "checkout"), fac.path(cfg, "run") / "complexity", fams)
    try:
        ref = (a.args[named:] or [cfg["git"]["base"]])[0]
        sha = ctx.git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()      # (resolved once)
        if a.cmd == "value":
            at, v = value(ctx, name, sha)
            print(f"{name}: at {at}", file=sys.stderr)
            print(json.dumps(v))
        elif a.cmd == "measure":
            if a.family is not None and a.family not in fams:
                raise Missing(f"no family {a.family!r} (of {', '.join(fams)})")
            for n, e in measure(ctx, sha, a.family)["families"].items():
                print(f"{n}: {e['state']} (tries {e['tries']}, {e['seconds']}s) {e['error'] or ''}".rstrip())
        elif a.cmd == "history":
            for row in history(ctx, name, sha)[-a.last or None:]:
                print(*row)
        elif a.cmd == "rows":
            for row in snapshot(ctx, sha, fams).rows:
                print(json.dumps(row))
        else:
            fam = next((n for n, f in fams.items() if name in getattr(f, "REPORTS", {})), None)
            if fam is None:
                raise Missing(f"no report {name!r}")
            for row in fams[fam].REPORTS[name](snapshot(ctx, sha, {fam: fams[fam]})):
                show(row)
    except (Missing, OSError, ValueError, KeyError) as e:
        print(f"{name}: no value ({e})", file=sys.stderr)
        return 1 if a.cmd == "value" else 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
