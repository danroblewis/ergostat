"""Asking a remote ergostat (SPEC §4c): one GET under ``/remote/v1/``, with the consumer's token, bounded in time.
Never raises for the remote's failings: (status, body, etag, why) with status 0 when it did not answer."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AGENT = "ergostat-remote/1"


def token_of(token_file: str | None, root: Path) -> tuple[str | None, str]:
    """The token in ``token_file`` (``~`` expanded, relative to the model's folder), or None and why."""
    if not token_file:
        return None, "no token-file: given"
    f = Path(token_file).expanduser()
    if not f.is_absolute():
        f = Path(root) / f
    try:
        tok = f.read_text().strip()
    except OSError as e:
        return None, f"token-file {f}: {e.strerror or e}"
    return (tok or None), ("" if tok else f"token-file {f} is empty")


def get(url: str, path: str, token: str | None, params: dict | None = None, etag: str | None = None,
        timeout: float = 5.0) -> tuple[int, object, str | None, str]:
    q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
    full = f"{url.rstrip('/')}/remote/v1/{path.lstrip('/')}" + (f"?{q}" if q else "")
    req = urllib.request.Request(full, headers={"User-Agent": AGENT, "Accept": "application/json",
                                                **({"Authorization": f"Bearer {token}"} if token else {}),
                                                **({"If-None-Match": f'"{etag}"'} if etag else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (a URL the owner wrote)
            body = r.read()
            return r.status, json.loads(body.decode() or "null"), (r.headers.get("ETag") or "").strip('"') or None, ""
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, None, etag, ""
        try:
            why = json.loads(e.read().decode()).get("error") or e.reason
        except Exception:
            why = e.reason
        return e.code, None, None, f"{e.code} {why}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        why = getattr(e, "reason", None) or e
        return 0, None, None, f"unreachable ({why})"
