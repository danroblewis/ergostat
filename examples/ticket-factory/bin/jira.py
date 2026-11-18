"""Jira: every call the factory makes to it, each in one function, so pointing it at another Jira is a change
here and in factory.conf, nowhere else.

    waiting()                 issues labelled JIRA_LABEL in JIRA_PROJECT, in status JIRA_PICK_FROM
    counts()                  the labelled issues by status (for Prometheus)
    get(key)                  one issue: key, summary, status, labels, description (plain text), url
    transitions(key)          the transitions the issue has now: [{id, name, to}]
    transition(key, status)   move it to a status, by the transition that leads there (looked up, never assumed)
    comment(key, text)        add a comment

Cloud (JIRA_API=3, JIRA_AUTH=basic: email and API token) and Data Center (JIRA_API=2, JIRA_AUTH=bearer: a
personal access token) differ only in what is marked DC below: the search endpoint, and bodies as Atlassian
Document Format (Cloud) or plain text (Data Center).

The token is read from JIRA_TOKEN_FILE at each call and never printed, logged or recorded. Offline, the same
calls go to bin/fakes.py. Writes (transition, comment) are only ever made through bin/act.py, under a gate,
and only on issues carrying JIRA_LABEL: refused here otherwise.

    jira.py waiting | get KEY | transitions KEY      read, for a person checking the setup
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import fakes
from tf import OFFLINE, conf


class JiraError(RuntimeError):
    pass


def _auth() -> str:
    path = os.path.expanduser(conf("JIRA_TOKEN_FILE", "~/.jira_token"))
    try:
        token = open(path).read().strip()
    except OSError as e:
        raise JiraError(f"no Jira token at {path}: {e.strerror}") from None
    if conf("JIRA_AUTH", "basic") == "bearer":                              # DC: a personal access token
        return "Bearer " + token
    return "Basic " + base64.b64encode(f"{conf('JIRA_EMAIL')}:{token}".encode()).decode()


def _call(method: str, path: str, body: dict | None = None, query: dict | None = None):
    url = conf("JIRA_URL").rstrip("/") + f"/rest/api/{conf('JIRA_API', '3')}" + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": _auth(), "Accept": "application/json",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise JiraError(f"Jira {method} {path}: HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise JiraError(f"Jira {method} {path}: {e.reason}") from None
    return json.loads(raw) if raw else {}


def _cloud() -> bool:
    return conf("JIRA_API", "3") == "3"


def _search(jql: str, fields: list[str], most: int = 100) -> list[dict]:
    if _cloud():
        got = _call("POST", "/search/jql", {"jql": jql, "fields": fields, "maxResults": most})
    else:                                                                   # DC: GET /rest/api/2/search
        got = _call("GET", "/search", query={"jql": jql, "fields": ",".join(fields), "maxResults": most})
    return got.get("issues", [])


def _text(desc) -> str:
    """A description as plain text: Atlassian Document Format (Cloud) walked for its text, or the string (DC)."""
    if desc is None or isinstance(desc, str):
        return desc or ""
    out: list[str] = []

    def walk(node):
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        for child in node.get("content", []) or []:
            walk(child)
        if node.get("type") in ("paragraph", "heading", "listItem", "codeBlock"):
            out.append("\n")
    walk(desc)
    return "".join(out).strip()


def _body(text: str):
    if not _cloud():                                                        # DC: plain text (wiki markup)
        return text
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": para}]} for para in text.split("\n\n") if para]}


def _issue(raw: dict) -> dict:
    f = raw.get("fields", {})
    return {"key": raw["key"], "summary": f.get("summary", ""), "status": (f.get("status") or {}).get("name", ""),
            "labels": f.get("labels", []), "description": _text(f.get("description")),
            "url": f"{conf('JIRA_URL').rstrip('/')}/browse/{raw['key']}"}


FIELDS = ["summary", "status", "labels", "description"]


def _scope() -> str:
    return f'project = "{conf("JIRA_PROJECT")}" AND labels = "{conf("JIRA_LABEL")}"'


def waiting() -> list[dict]:
    if OFFLINE:
        return fakes.jira_waiting()
    jql = f'{_scope()} AND status = "{conf("JIRA_PICK_FROM")}" ORDER BY created ASC'
    return [_issue(i) for i in _search(jql, FIELDS)]


def counts() -> dict[str, int]:
    if OFFLINE:
        return fakes.jira_counts()
    out: dict[str, int] = {}
    for i in _search(_scope(), ["status"], 500):
        s = i["fields"]["status"]["name"]
        out[s] = out.get(s, 0) + 1
    return out


def get(key: str) -> dict:
    if OFFLINE:
        return fakes.jira_get(key)
    return _issue(_call("GET", f"/issue/{key}", query={"fields": ",".join(FIELDS)}))


def transitions(key: str) -> list[dict]:
    if OFFLINE:
        return fakes.jira_transitions(key)
    return [{"id": t["id"], "name": t["name"], "to": t["to"]["name"]}
            for t in _call("GET", f"/issue/{key}/transitions").get("transitions", [])]


def _ours(key: str) -> dict:
    issue = get(key)
    if conf("JIRA_LABEL") not in issue["labels"]:
        raise JiraError(f"{key} is not labelled {conf('JIRA_LABEL')}: the factory writes only to its own issues")
    return issue


def transition(key: str, status: str) -> str:
    """Move the issue to `status`, by whichever transition leads there now. Already there: nothing to do."""
    issue = _ours(key)
    if issue["status"] == status:
        return f"{key} is already {status}"
    found = [t for t in transitions(key) if t["to"].lower() == status.lower()]
    if not found:
        names = ", ".join(f"{t['name']} (to {t['to']})" for t in transitions(key)) or "none"
        raise JiraError(f"{key} ({issue['status']}) has no transition to {status}; it has: {names}")
    if OFFLINE:
        fakes.jira_transition(key, found[0]["id"])
    else:
        _call("POST", f"/issue/{key}/transitions", {"transition": {"id": found[0]["id"]}})
    return f"{key}: {issue['status']} -> {status}"


def comment(key: str, text: str) -> str:
    _ours(key)
    if OFFLINE:
        fakes.jira_comment(key, text)
    else:
        _call("POST", f"/issue/{key}/comment", {"body": _body(text)})
    return f"{key}: commented"


if __name__ == "__main__":
    what = sys.argv[1:] or ["waiting"]
    fn = {"waiting": waiting, "counts": counts, "get": get, "transitions": transitions}[what[0]]
    print(json.dumps(fn(*what[1:]), indent=1))
