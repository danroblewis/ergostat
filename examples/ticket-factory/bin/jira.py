"""Jira: every call the factory makes to it, each in one function, so pointing it at another Jira is a change
here and in factory.conf, nowhere else.

    waiting()                 issues labelled JIRA_LABEL in JIRA_PROJECT, in status JIRA_PICK_FROM
    counts()                  the labelled issues by status (for Prometheus)
    linked()                  links() of each labelled issue, by key: one search, paged, at most LINKS_MOST (500)
    links(fields)             one issue's raw fields as {blocked_by, duplicates, relates_to, parent} (ticket/KEY ids),
                              or None when any part can't be read
    get(key)                  one issue: key, summary, status, labels, description (plain text), url
    transitions(key)          the transitions the issue has now: [{id, name, to}]
    transition(key, status)   move it to a status, by the transition that leads there (looked up, never assumed)
    comment(key, text)        add a comment
    whoami(), check()         who the token signs in as; the project and its statuses (./setup)
    create(...), delete(key)  the demo's own test issues only (bin/demo_issues.py), always labelled

Cloud (JIRA_API=3, JIRA_AUTH=basic: email and API token) and Data Center (JIRA_API=2, JIRA_AUTH=bearer: a
personal access token) differ only in what is marked DC below: the search endpoint, and bodies as Atlassian
Document Format (Cloud) or plain text (Data Center).

The token is read from JIRA_TOKEN_FILE at each call and never printed, logged or recorded. Offline, the same
calls go to bin/fakes.py. Writes (transition, comment) are made only by the gated actions (factory/actions.yaml),
which run the commands below, and only on issues carrying JIRA_LABEL: refused here otherwise.

    jira.py waiting | get KEY | transitions KEY      read, for a person checking the setup
    jira.py transition KEY STATUS | comment KEY TEXT  the gated actions' commands
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import fakes
from tf import OFFLINE, conf, ticket_id


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


LINKS_MOST = 500                                   # a constant, like counts()'s 500: never read from config
KEY = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")
RELATIONS = ("blocked_by", "duplicates", "relates_to", "parent")
OWN = {"Blocks": "inwardIssue", "Duplicate": "outwardIssue"}   # the other side of these is the inverse ergostat derives


def _key(issue) -> str | None:
    k = issue.get("key") if isinstance(issue, dict) else None
    return k if isinstance(k, str) and KEY.match(k) else None


def links(fields) -> dict[str, list[str]] | None:
    """One issue's links as the ticket's relations, matched by the link type's name: Blocks inward is blocked_by,
    Duplicate outward is duplicates, any other type either way is relates_to, and fields.parent is parent. None for
    the whole issue when any part can't be read (lesson-3): a full set written from the rest would clear a real link."""
    ls = fields.get("issuelinks") if isinstance(fields, dict) else None
    if not isinstance(ls, list):
        return None
    got: dict[str, set[str]] = {r: set() for r in RELATIONS}
    for e in ls:
        name = e.get("type", {}).get("name") if isinstance(e, dict) and isinstance(e.get("type"), dict) else None
        side = next((s for s in ("inwardIssue", "outwardIssue") if s in e), None) if isinstance(e, dict) else None
        key = _key(e[side]) if side else None
        if not isinstance(name, str) or key is None:
            return None
        if name not in OWN:
            got["relates_to"].add(ticket_id(key))
        elif OWN[name] == side:
            got["blocked_by" if name == "Blocks" else "duplicates"].add(ticket_id(key))
    if fields.get("parent") is not None:
        if (key := _key(fields["parent"])) is None:
            return None
        got["parent"].add(ticket_id(key))
    return {r: sorted(v) for r, v in got.items()}


def linked() -> dict[str, dict | None]:
    """links() of each labelled issue, by Jira key: one search over _scope(), paged (Jira answers fewer than asked on a
    page), up to LINKS_MOST issues. An issue past that is not looked at, so it keeps what it has."""
    if OFFLINE:
        return {k: links(f) for k, f in fakes.jira_linked().items()}
    fields, out, token = ["issuelinks", "parent"], {}, None
    while len(out) < LINKS_MOST:
        most = LINKS_MOST - len(out)
        if _cloud():                                                        # Cloud: by nextPageToken
            got = _call("POST", "/search/jql", {"jql": _scope(), "fields": fields, "maxResults": most,
                                                **({"nextPageToken": token} if token else {})})
            token = got.get("nextPageToken")
        else:                                                               # DC: GET /rest/api/2/search, by startAt
            got = _call("GET", "/search", query={"jql": _scope(), "fields": ",".join(fields), "maxResults": most,
                                                 "startAt": len(out)})
            token = len(out) + len(got.get("issues") or []) < got.get("total", 0) or None
        page = (got.get("issues") or [])[:most]
        if not all(isinstance(i, dict) and isinstance(i.get("key"), str) for i in page):
            raise JiraError("Jira's search answered an issue with no key")
        out.update({i["key"]: links(i.get("fields")) for i in page})
        if not page or not token:
            break
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


def whoami() -> str:
    if OFFLINE:
        return "the offline fake"
    me = _call("GET", "/myself")
    return me.get("displayName") or me.get("name") or "?"


def check() -> str:
    """The project exists, and has every status factory.conf names."""
    if OFFLINE:
        return "offline: the fake board"
    wanted = {conf(k) for k in ("JIRA_PICK_FROM", "JIRA_IN_PROGRESS", "JIRA_IN_REVIEW", "JIRA_DONE")}
    have = {s["name"] for t in _call("GET", f"/project/{conf('JIRA_PROJECT')}/statuses") for s in t["statuses"]}
    missing = wanted - have
    if missing:
        raise JiraError(f"{conf('JIRA_PROJECT')} has no status {', '.join(sorted(missing))}; it has {', '.join(sorted(have))}")
    return f"{conf('JIRA_PROJECT')}: statuses {', '.join(sorted(have))}"


def create(summary: str, description: str, issuetype: str = "Task") -> str:
    """A test issue for the demo, labelled JIRA_LABEL (bin/demo_issues.py)."""
    if OFFLINE:
        raise JiraError("offline, issues arrive on their own")
    got = _call("POST", "/issue", {"fields": {"project": {"key": conf("JIRA_PROJECT")}, "summary": summary,
                                             "issuetype": {"name": issuetype}, "labels": [conf("JIRA_LABEL")],
                                             "description": _body(description)}})
    return got["key"]


def delete(key: str) -> None:
    """Delete one of the demo's own test issues (refused unless labelled)."""
    _ours(key)
    _call("DELETE", f"/issue/{key}")


if __name__ == "__main__":
    what = sys.argv[1:] or ["waiting"]
    fn = {"waiting": waiting, "counts": counts, "get": get, "transitions": transitions, "whoami": whoami,
          "check": check, "transition": transition, "comment": comment}[what[0]]
    try:
        got = fn(*what[1:])
    except JiraError as e:
        sys.exit(str(e))
    print(got if isinstance(got, str) else json.dumps(got, indent=1))
