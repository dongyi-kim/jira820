"""Mutable in-memory store: seeded deterministically, then mutated by write endpoints.

Holds issues, users, boards, sprints, versions, activity and Confluence pages, plus indexes.
Optionally persists to a JSON file (JIRA820_PERSIST) so a client's changes survive restarts.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

from . import world
from .config import SUBTASK_TYPE, Config
from .serialize import Serializer
from .workflow import Workflow

_DATE_FIELDS = {"created", "updated", "resolved", "due"}


class JiraError(Exception):
    def __init__(self, status_code: int, messages, errors=None):
        self.status_code = status_code
        self.messages = messages if isinstance(messages, list) else [messages]
        self.errors = errors or {}
        super().__init__("; ".join(self.messages))

    def body(self):
        return {"errorMessages": self.messages, "errors": self.errors}


class Store:
    def __init__(self, config: Config, seed: bool = True):
        # seed=False builds an empty store; fill .issues/.users/... yourself then call .reindex()
        # (used to inject an external world while reusing this package's serializers/endpoints).
        self.config = config
        self.workflow = Workflow(config)
        self.serializer = Serializer(self)
        self.issues: dict = {}
        self.users: dict = {}
        self.module_users: dict = {}
        self.boards: dict = {}
        self.sprints: dict = {}
        self.versions: list = []
        self.activity: dict = {}
        self.confluence: dict = {}
        self.by_label: dict = {}
        self.by_assignee: dict = {}
        self.epic_children: dict = {}
        self.attachments: dict = {}   # id -> {id, issueKey, filename, mimeType, size, data, author, created}
        self._counter = 0
        self._comment_seq = 100000
        self._sprint_seq = 0
        self._attach_seq = 30000

        if not seed:
            return  # empty store; caller populates + reindex()
        if config.persist and os.path.exists(config.persist):
            self._load(config.persist)
        else:
            world.seed(self)
            self._counter = self._max_counter()
            self._sprint_seq = max(self.sprints) if self.sprints else 0
            if config.persist:
                self.save()

    # ── clock ──
    @property
    def now(self) -> date:
        return self.config.base_date

    # ── indexes ──
    def reindex(self):
        by_label, by_assignee, epic_children = {}, {}, {}
        for k, it in self.issues.items():
            for lb in it.get("labels", []):
                by_label.setdefault(lb, []).append(k)
            if it.get("assignee"):
                by_assignee.setdefault(it["assignee"], []).append(k)
            if it.get("epicKey"):
                epic_children.setdefault(it["epicKey"], []).append(k)
        self.by_label, self.by_assignee, self.epic_children = by_label, by_assignee, epic_children

    def _max_counter(self) -> int:
        mx = 0
        for k in self.issues:
            try:
                mx = max(mx, int(k.rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                pass
        return mx

    def new_key(self) -> str:
        self._counter += 1
        return f"{self.config.project_key}-{self._counter}"

    def _require_writable(self):
        if self.config.readonly:
            raise JiraError(403, "This mock is running in read-only mode (JIRA820_READONLY).")

    def get_issue(self, key: str) -> dict:
        it = self.issues.get(key)
        if not it:
            raise JiraError(404, f"Issue Does Not Exist: {key}")
        return it

    # ── issue mutations ──
    def create_issue(self, fields: dict) -> dict:
        self._require_writable()
        f = fields or {}
        proj = ((f.get("project") or {}).get("key")) or self.config.project_key
        if proj != self.config.project_key:
            raise JiraError(400, f"Unknown project: {proj}", {"project": "project is required"})
        itype = ((f.get("issuetype") or {}).get("name")
                 or self._type_by_id((f.get("issuetype") or {}).get("id")))
        if not itype or itype not in {t[0] for t in self.config.issue_types}:
            raise JiraError(400, "Valid issue type is required", {"issuetype": "issue type is required"})
        summary = f.get("summary")
        if not summary:
            raise JiraError(400, "You must specify a summary of the issue.", {"summary": "summary is required"})

        key = self.new_key()
        assignee = (f.get("assignee") or {}).get("name")
        module = self.config.modules[0]
        comp = None
        if f.get("components"):
            comp = f["components"][0].get("name")
        status = self.workflow.default_status()
        parent_key = (f.get("parent") or {}).get("key")
        it = {
            "key": key, "project": proj, "type": itype, "summary": summary,
            "description": f.get("description"),
            "module": module, "component": comp,
            "assignee": assignee, "reporter": (f.get("reporter") or {}).get("name") or "admin",
            "statusCategory": self.workflow.category_of(status), "statusName": status,
            "resolution": None,
            "labels": list(f.get("labels", [])),
            "sp": f.get(self.config.sp_field),
            "epicKey": f.get(self.config.epic_link_field),
            "parentKey": parent_key,
            "created": self.now, "updated": self.now, "resolved": None,
            "due": _parse_date(f.get("duedate")),
            "tcreated": "09:00", "tupdated": "09:00", "tresolved": None,
            "comments": [], "worklog": [], "subtasks": [],
            "sprints": [], "fixVersions": [], "changelog": [],
            "watches": 0, "votes": 0,
        }
        self.issues[key] = it
        if parent_key and parent_key in self.issues:
            self.issues[parent_key]["subtasks"].append(key)
        self.reindex()
        self._touch_persist()
        return {"id": _iid(key), "key": key, "self": f"/rest/api/2/issue/{key}"}

    def update_issue(self, key: str, fields: dict):
        self._require_writable()
        it = self.get_issue(key)
        f = fields or {}
        if "summary" in f:
            it["summary"] = f["summary"]
        if "description" in f:
            it["description"] = f["description"]
        if "labels" in f:
            it["labels"] = list(f["labels"])
        if "duedate" in f:
            it["due"] = _parse_date(f["duedate"])
        if "assignee" in f:
            it["assignee"] = (f["assignee"] or {}).get("name")
        if "components" in f:
            it["component"] = (f["components"][0].get("name") if f["components"] else None)
        if self.config.sp_field in f:
            it["sp"] = f[self.config.sp_field]
        if self.config.epic_link_field in f:
            it["epicKey"] = f[self.config.epic_link_field]
        it["updated"] = self.now
        it["tupdated"] = "09:00"
        self.reindex()
        self._touch_persist()

    def delete_issue(self, key: str):
        self._require_writable()
        it = self.get_issue(key)
        for sk in list(it.get("subtasks", [])):
            self.issues.pop(sk, None)
        self.issues.pop(key, None)
        self.reindex()
        self._touch_persist()

    def transition_issue(self, key: str, transition_id: str):
        self._require_writable()
        it = self.get_issue(key)
        target = self.workflow.target_of(transition_id)
        if not target:
            raise JiraError(400, f"Transition id {transition_id} is not valid.")
        old_status = it["statusName"]
        old_id = self.workflow.by_name.get(old_status, ("", "1"))[1]
        it["statusName"] = target
        it["statusCategory"] = self.workflow.category_of(target)
        if it["statusCategory"] == "done":
            if not it["resolved"]:
                it["resolved"] = self.now
                it["tresolved"] = "09:00"
            it["resolution"] = it.get("resolution") or "Done"
        else:
            it["resolved"] = None
            it["resolution"] = None
        it["updated"] = self.now
        it["changelog"].append({
            "author": "admin", "date": self.now, "time": "09:00",
            "items": [{"field": "status", "fieldtype": "jira",
                       "from": old_id, "fromString": old_status,
                       "to": self.workflow.by_name.get(target, ("", "1"))[1], "toString": target}],
        })
        self._touch_persist()

    def add_comment(self, key: str, body: str, author: str = "admin") -> dict:
        self._require_writable()
        it = self.get_issue(key)
        self._comment_seq += 1
        cid = str(self._comment_seq)
        c = {"id": cid, "author": author, "body": body, "kind": "comment", "text": body,
             "created": self.now, "tcreated": "09:00", "updated": self.now, "tupdated": "09:00"}
        it["comments"].append(c)
        it["updated"] = self.now
        self._touch_persist()
        idx = len(it["comments"]) - 1
        return self.serializer.comment_obj(key, idx, c)

    def update_comment(self, key: str, cid: str, body: str) -> dict:
        self._require_writable()
        it = self.get_issue(key)
        for idx, c in enumerate(it["comments"]):
            if str(c.get("id")) == str(cid):
                c["body"] = body
                c["text"] = body
                c["updated"] = self.now
                self._touch_persist()
                return self.serializer.comment_obj(key, idx, c)
        raise JiraError(404, f"Comment {cid} does not exist.")

    def delete_comment(self, key: str, cid: str):
        self._require_writable()
        it = self.get_issue(key)
        before = len(it["comments"])
        it["comments"] = [c for c in it["comments"] if str(c.get("id")) != str(cid)]
        if len(it["comments"]) == before:
            raise JiraError(404, f"Comment {cid} does not exist.")
        self._touch_persist()

    def add_worklog(self, key: str, seconds: int, started=None, author="admin", comment="") -> dict:
        self._require_writable()
        it = self.get_issue(key)
        w = {"id": str(20000 + len(it["worklog"])), "author": author, "seconds": int(seconds),
             "date": _parse_date(started) or self.now, "time": "09:00", "comment": comment}
        it["worklog"].append(w)
        it["updated"] = self.now
        self._touch_persist()
        return self.serializer.worklog_obj(key, len(it["worklog"]) - 1, w)

    def set_assignee(self, key: str, name):
        self._require_writable()
        it = self.get_issue(key)
        it["assignee"] = name
        it["updated"] = self.now
        self.reindex()
        self._touch_persist()

    # ── attachments (files/images on issues; referenced from description/comment markup) ──
    def add_attachment(self, key: str, filename: str, mimetype: str, data: bytes, author: str = "admin") -> dict:
        self._require_writable()
        it = self.get_issue(key)
        self._attach_seq += 1
        aid = str(self._attach_seq)
        att = {"id": aid, "issueKey": key, "filename": filename or f"file-{aid}",
               "mimeType": mimetype or "application/octet-stream", "size": len(data or b""),
               "data": bytes(data or b""), "author": author, "created": self.now}
        self.attachments[aid] = att
        it.setdefault("attachments", []).append(aid)
        it["updated"] = self.now
        self._touch_persist()
        return att

    def get_attachment(self, aid) -> dict:
        a = self.attachments.get(str(aid))
        if not a:
            raise JiraError(404, f"Attachment {aid} does not exist.")
        return a

    def delete_attachment(self, aid):
        self._require_writable()
        a = self.attachments.pop(str(aid), None)
        if not a:
            raise JiraError(404, f"Attachment {aid} does not exist.")
        it = self.issues.get(a["issueKey"])
        if it and it.get("attachments"):
            it["attachments"] = [x for x in it["attachments"] if x != str(aid)]
        self._touch_persist()

    # ── agile mutations ──
    def create_sprint(self, board_id: int, name: str, goal: str = "", state: str = "future") -> dict:
        self._require_writable()
        if board_id not in self.boards:
            raise JiraError(404, f"Board {board_id} does not exist.")
        self._sprint_seq = max(self._sprint_seq, max(self.sprints) if self.sprints else 0) + 1
        sid = self._sprint_seq
        self.sprints[sid] = {"id": sid, "name": name or f"Sprint {sid}", "state": state,
                             "boardId": board_id, "goal": goal,
                             "startDate": None, "endDate": None, "completeDate": None}
        self._touch_persist()
        return self.sprint_json(sid)

    def update_sprint(self, sid: int, patch: dict) -> dict:
        self._require_writable()
        s = self.sprints.get(sid)
        if not s:
            raise JiraError(404, f"Sprint {sid} does not exist.")
        if "name" in patch:
            s["name"] = patch["name"]
        if "goal" in patch:
            s["goal"] = patch["goal"]
        if "startDate" in patch:
            s["startDate"] = _parse_date(patch["startDate"])
        if "endDate" in patch:
            s["endDate"] = _parse_date(patch["endDate"])
        if "state" in patch:
            s["state"] = patch["state"]
            if patch["state"] == "active" and not s["startDate"]:
                s["startDate"] = self.now
                s["endDate"] = self.now + timedelta(days=14)
            if patch["state"] == "closed":
                s["completeDate"] = self.now
                # incomplete issues drop back to backlog
                for it in self.issues.values():
                    if sid in it.get("sprints", []) and it["statusCategory"] != "done":
                        it["sprints"] = [x for x in it["sprints"] if x != sid]
        self._touch_persist()
        return self.sprint_json(sid)

    def move_issues_to_sprint(self, sid: int, keys: list):
        self._require_writable()
        if sid not in self.sprints:
            raise JiraError(404, f"Sprint {sid} does not exist.")
        for k in keys:
            it = self.issues.get(k)
            if it:
                it["sprints"] = [sid]  # an issue lives in one active/future sprint
                it["updated"] = self.now
        self._touch_persist()

    def move_issues_to_backlog(self, keys: list):
        self._require_writable()
        for k in keys:
            it = self.issues.get(k)
            if it:
                it["sprints"] = []
                it["updated"] = self.now
        self._touch_persist()

    def _type_by_id(self, tid):
        if tid is None:
            return None
        for name, t in self.config.issue_types:
            if str(t) == str(tid):
                return name
        return None

    # ── serialization convenience ──
    def jira_issue(self, key):
        it = self.issues.get(key)
        return {"key": key, "fields": self.serializer.issue_fields(it)} if it else None

    def jira_comments(self, key):
        it = self.issues.get(key)
        if not it:
            return []
        out = [self.serializer.comment_obj(key, i, c) for i, c in enumerate(it["comments"])]
        out.sort(key=lambda c: c["created"], reverse=True)
        return out

    def confluence_pages(self):
        """검색용 평면 Confluence 페이지 코퍼스 — (title, space) 로 유니크.
        각 항목: {id, title, body?, space, author, date, time?, action?}."""
        import hashlib
        seen = {}
        for uid, pages in self.confluence.items():
            for p in pages:
                key = (p.get("title") or "", str(p.get("space") or ""))
                if key in seen:
                    continue
                pid = int(hashlib.md5(("%s|%s" % key).encode("utf-8")).hexdigest()[:8], 16)
                seen[key] = dict(p, author=uid, id=pid)
        return list(seen.values())

    def sprint_json(self, sid) -> dict:
        s = self.sprints[sid]
        from .serialize import dt as _dt
        return {"id": s["id"], "self": f"/rest/agile/1.0/sprint/{s['id']}",
                "state": s["state"], "name": s["name"], "goal": s.get("goal", ""),
                "originBoardId": s["boardId"],
                "startDate": _dt(s.get("startDate")), "endDate": _dt(s.get("endDate")),
                "completeDate": _dt(s.get("completeDate"))}

    # ── persistence ──
    def save(self):
        if not self.config.persist:
            return
        tmp = self.config.persist + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._to_dict(), fh, ensure_ascii=False, default=_json_default)
        os.replace(tmp, self.config.persist)

    def _touch_persist(self):
        if self.config.persist:
            self.save()

    def _to_dict(self):
        return {
            "issues": {k: _issue_to_json(it) for k, it in self.issues.items()},
            "users": self.users, "module_users": self.module_users,
            "boards": {str(k): v for k, v in self.boards.items()},
            "sprints": {str(k): _sprint_to_json(v) for k, v in self.sprints.items()},
            "versions": self.versions,
            "activity": {u: [_ev_to_json(e) for e in evs] for u, evs in self.activity.items()},
            "confluence": {u: [_page_to_json(p) for p in ps] for u, ps in self.confluence.items()},
            "attachments": {aid: _att_to_json(a) for aid, a in self.attachments.items()},
        }

    def _load(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        self.users = d.get("users", {})
        self.module_users = d.get("module_users", {})
        self.boards = {int(k): v for k, v in d.get("boards", {}).items()}
        self.sprints = {int(k): _sprint_from_json(v) for k, v in d.get("sprints", {}).items()}
        self.versions = d.get("versions", [])
        self.issues = {k: _issue_from_json(it) for k, it in d.get("issues", {}).items()}
        self.activity = {u: [_ev_from_json(e) for e in evs] for u, evs in d.get("activity", {}).items()}
        self.confluence = {u: [_page_from_json(p) for p in ps] for u, ps in d.get("confluence", {}).items()}
        self.attachments = {aid: _att_from_json(a) for aid, a in d.get("attachments", {}).items()}
        self.reindex()
        self._counter = self._max_counter()
        self._sprint_seq = max(self.sprints) if self.sprints else 0
        self._attach_seq = max((int(x) for x in self.attachments), default=30000)


# ── (de)serialization helpers for persistence ──
import base64  # noqa: E402

from .serialize import iid as _iid  # noqa: E402


def _att_to_json(a):
    return {**{k: v for k, v in a.items() if k not in ("data", "created")},
            "created": _d(a.get("created")),
            "data": base64.b64encode(a.get("data") or b"").decode("ascii")}


def _att_from_json(a):
    return {**{k: v for k, v in a.items() if k not in ("data", "created")},
            "created": _parse_date(a.get("created")),
            "data": base64.b64decode(a.get("data") or "")}


def _parse_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _json_default(o):
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(repr(o))


def _issue_to_json(it):
    d = dict(it)
    for k in _DATE_FIELDS:
        d[k] = it[k].isoformat() if it.get(k) else None
    d["comments"] = [dict(c, created=_d(c.get("created")), updated=_d(c.get("updated"))) for c in it["comments"]]
    d["worklog"] = [dict(w, date=_d(w.get("date"))) for w in it["worklog"]]
    d["changelog"] = [dict(ch, date=_d(ch.get("date"))) for ch in it["changelog"]]
    return d


def _issue_from_json(d):
    it = dict(d)
    for k in _DATE_FIELDS:
        it[k] = _parse_date(d.get(k))
    it["comments"] = [dict(c, created=_parse_date(c.get("created")), updated=_parse_date(c.get("updated")))
                      for c in d.get("comments", [])]
    it["worklog"] = [dict(w, date=_parse_date(w.get("date"))) for w in d.get("worklog", [])]
    it["changelog"] = [dict(ch, date=_parse_date(ch.get("date"))) for ch in d.get("changelog", [])]
    return it


def _sprint_to_json(s):
    return dict(s, startDate=_d(s.get("startDate")), endDate=_d(s.get("endDate")),
                completeDate=_d(s.get("completeDate")))


def _sprint_from_json(s):
    return dict(s, startDate=_parse_date(s.get("startDate")), endDate=_parse_date(s.get("endDate")),
                completeDate=_parse_date(s.get("completeDate")))


def _ev_to_json(e):
    return dict(e, date=_d(e.get("date")))


def _ev_from_json(e):
    return dict(e, date=_parse_date(e.get("date")))


def _page_to_json(p):
    return dict(p, date=_d(p.get("date")))


def _page_from_json(p):
    return dict(p, date=_parse_date(p.get("date")))


def _d(v):
    return v.isoformat() if isinstance(v, date) else v
