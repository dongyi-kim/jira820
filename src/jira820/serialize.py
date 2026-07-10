"""Serialize canonical internal objects into Jira Data Center 8.20.8 REST JSON.

Kept faithful to real DC response shapes (statusCategory keys new/indeterminate/done,
custom-field indirection for Story Points / Epic Link / Sprint, avatar URL patterns, etc.).
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional

# internal category -> real Jira DC statusCategory
JIRA_CAT = {
    "todo": {"id": 2, "key": "new", "colorName": "blue-gray", "name": "To Do"},
    "inprogress": {"id": 4, "key": "indeterminate", "colorName": "yellow", "name": "In Progress"},
    "done": {"id": 3, "key": "done", "colorName": "green", "name": "Done"},
}
CAT_COLOR = {"new": "blue-gray", "indeterminate": "yellow", "done": "green"}


def iid(key: str) -> str:
    """Issue key -> deterministic numeric Jira issue id."""
    return str(int(hashlib.md5(key.encode()).hexdigest()[:8], 16))


def dt(d, hm: Optional[str] = None) -> str:
    """date -> Jira timestamp '...T{hh:mm}:00.000+0000'."""
    if d is None:
        return None
    if isinstance(d, str):
        return d
    return d.isoformat() + "T" + (hm or "09:00") + ":00.000+0000"


class Serializer:
    def __init__(self, store):
        self.store = store
        c = store.config
        self.c = c
        # status name -> (category, id) ; issue type name -> id
        self.status_map = {name: (cat, sid) for name, cat, sid in c.statuses}
        self.type_map = {name: tid for name, tid in c.issue_types}
        self.comp_ids = {m: str(100 + i) for i, m in enumerate(c.components)}

    # ── small objects ──
    def status_obj(self, name: str) -> dict:
        cat, sid = self.status_map.get(name, ("todo", "1"))
        jc = JIRA_CAT[cat]
        return {
            "self": f"/rest/api/2/status/{sid}", "description": "",
            "iconUrl": f"/images/icons/statuses/{jc['key']}.png",
            "name": name, "id": sid,
            "statusCategory": {
                "self": f"/rest/api/2/statuscategory/{jc['id']}",
                "id": jc["id"], "key": jc["key"], "colorName": jc["colorName"], "name": jc["name"],
            },
        }

    def issuetype_obj(self, name: str) -> dict:
        tid = self.type_map.get(name, "0")
        slug = name.lower().replace(" ", "").replace("-", "")
        return {
            "self": f"/rest/api/2/issuetype/{tid}", "id": tid, "description": "",
            "iconUrl": f"/secure/viewavatar?avatarType=issuetype&avatarId=10300&type={slug}",
            "name": name, "subtask": name == self.c.subtask_type, "avatarId": 10300,
        }

    def user_obj(self, uid: str) -> dict:
        u = self.store.users.get(uid, {"name": uid, "displayName": uid})
        n = u["name"]
        return {
            "self": f"/rest/api/2/user?username={n}",
            "name": n, "key": n, "emailAddress": f"{n}@example.com",
            "avatarUrls": {
                "48x48": f"/secure/useravatar?ownerId={n}&avatarId=10122",
                "32x32": f"/secure/useravatar?size=medium&ownerId={n}&avatarId=10122",
                "24x24": f"/secure/useravatar?size=small&ownerId={n}&avatarId=10122",
                "16x16": f"/secure/useravatar?size=xsmall&ownerId={n}&avatarId=10122",
            },
            "displayName": u["displayName"], "active": True, "timeZone": "UTC",
        }

    def _resolution_obj(self, it) -> Optional[dict]:
        if it["statusCategory"] != "done":
            return None
        name = it.get("resolution") or "Done"
        return {"self": "/rest/api/2/resolution/1", "id": "1",
                "description": "Work has been completed.", "name": name}

    def _sprint_field(self, it) -> Optional[list]:
        ids = it.get("sprints") or []
        out = []
        for sid in ids:
            s = self.store.sprints.get(sid)
            if not s:
                continue
            out.append({
                "id": s["id"], "name": s["name"], "state": s["state"].upper(),
                "boardId": s["boardId"], "goal": s.get("goal", ""),
                "startDate": dt(s.get("startDate")), "endDate": dt(s.get("endDate")),
                "completeDate": dt(s.get("completeDate")),
            })
        return out or None

    def attachment_obj(self, a, base_url: str = "") -> dict:
        fn = a["filename"]
        obj = {
            "self": f"{base_url}/rest/api/2/attachment/{a['id']}",
            "id": str(a["id"]), "filename": fn,
            "author": self.user_obj(a.get("author") or "admin"),
            "created": dt(a.get("created")), "size": a.get("size", 0),
            "mimeType": a.get("mimeType", "application/octet-stream"),
            "content": f"{base_url}/secure/attachment/{a['id']}/{fn}",
        }
        if (a.get("mimeType") or "").startswith("image/"):
            obj["thumbnail"] = f"{base_url}/secure/thumbnail/{a['id']}/{fn}"
        return obj

    # ── issue ──
    def issue_fields(self, it, base_url: str = "") -> dict:
        f = {
            "summary": it["summary"], "description": it.get("description"),
            "issuetype": self.issuetype_obj(it["type"]),
            "status": self.status_obj(it["statusName"]),
            "resolution": self._resolution_obj(it),
            "assignee": self.user_obj(it["assignee"]) if it.get("assignee") else None,
            "reporter": self.user_obj(it["reporter"]) if it.get("reporter") else None,
            "creator": self.user_obj(it["reporter"]) if it.get("reporter") else None,
            "priority": {"self": "/rest/api/2/priority/3", "id": "3", "name": "Medium",
                         "iconUrl": "/images/icons/priorities/medium.svg"},
            "components": [
                {"self": f"/rest/api/2/component/{self.comp_ids.get(it.get('component'), '0')}",
                 "id": self.comp_ids.get(it.get("component"), "0"), "name": it.get("component")}
            ] if it.get("component") else [],
            "labels": it.get("labels", []),
            "created": dt(it["created"], it.get("tcreated")),
            "updated": dt(it["updated"], it.get("tupdated")),
            "resolutiondate": dt(it["resolved"], it.get("tresolved")) if it.get("resolved") else None,
            "duedate": it["due"].isoformat() if it.get("due") else None,
            "timespent": sum(wl.get("seconds", 0) for wl in it.get("worklog", [])) or None,
            "aggregatetimespent": sum(wl.get("seconds", 0) for wl in it.get("worklog", [])) or None,
            "watches": {"self": f"/rest/api/2/issue/{it['key']}/watchers",
                        "watchCount": it.get("watches", 0), "isWatching": False},
            "votes": {"self": f"/rest/api/2/issue/{it['key']}/votes",
                      "votes": it.get("votes", 0), "hasVoted": False},
            "fixVersions": [self.version_obj(v) for v in it.get("fixVersions", [])],
            "project": self.project_ref(),
            "attachment": [self.attachment_obj(self.store.attachments[aid], base_url)
                           for aid in it.get("attachments", []) if aid in self.store.attachments],
            self.c.sp_field: it.get("sp"),
            self.c.epic_link_field: it.get("epicKey"),
            self.c.sprint_field: self._sprint_field(it),
        }
        pk = it.get("parentKey")
        if pk and pk in self.store.issues:
            p = self.store.issues[pk]
            f["parent"] = {"id": iid(pk), "key": pk, "fields": {
                "summary": p["summary"], "status": self.status_obj(p["statusName"]),
                "issuetype": self.issuetype_obj(p["type"])}}
        f["subtasks"] = [
            {"id": iid(sk), "key": sk, "fields": {
                "summary": self.store.issues[sk]["summary"],
                "status": self.status_obj(self.store.issues[sk]["statusName"]),
                "issuetype": self.issuetype_obj(self.store.issues[sk]["type"])}}
            for sk in it.get("subtasks", []) if sk in self.store.issues
        ]
        return f

    def project_ref(self) -> dict:
        return {"self": f"/rest/api/2/project/{self.c.project_key}", "id": "10000",
                "key": self.c.project_key, "name": self.c.project_name, "projectTypeKey": "software"}

    def version_obj(self, v) -> dict:
        return {"self": f"/rest/api/2/version/{v['id']}", "id": str(v["id"]),
                "name": v["name"], "released": v.get("released", False),
                "archived": False, "releaseDate": v.get("releaseDate")}

    def changelog(self, it) -> dict:
        hist = []
        for i, ch in enumerate(it.get("changelog", [])):
            hist.append({
                "id": str(1000 + i), "author": self.user_obj(ch["author"]),
                "created": dt(ch["date"], ch.get("time")),
                "items": ch["items"],
            })
        return {"startAt": 0, "maxResults": len(hist), "total": len(hist), "histories": hist}

    def issue_res(self, it, base_url: str, fields: str = "", expand: str = "") -> dict:
        allf = self.issue_fields(it, base_url)
        projected = project_fields(allf, fields)
        res = {
            "expand": "renderedFields,names,schema,transitions,operations,editmeta,changelog",
            "id": iid(it["key"]), "self": f"{base_url}/rest/api/2/issue/{it['key']}",
            "key": it["key"], "fields": projected,
        }
        if expand and "changelog" in expand:
            res["changelog"] = self.changelog(it)
        return res

    def comment_obj(self, key: str, idx: int, c) -> dict:
        au = self.user_obj(c["author"])
        when = dt(c["created"], c.get("tcreated"))
        upd = dt(c.get("updated") or c["created"], c.get("tupdated") or c.get("tcreated"))
        cid = c.get("id") or f"{10000 + idx}"
        body = c["body"] if "body" in c else f"({c['kind']}) {c['text']}"
        return {"self": f"/rest/api/2/issue/{key}/comment/{cid}", "id": str(cid),
                "author": au, "updateAuthor": au, "body": body,
                "created": when, "updated": upd}

    def worklog_obj(self, key: str, idx: int, w) -> dict:
        au = self.user_obj(w["author"])
        wid = w.get("id") or f"{20000 + idx}"
        return {"self": f"/rest/api/2/issue/{key}/worklog/{wid}", "id": str(wid),
                "author": au, "updateAuthor": au, "comment": w.get("comment", ""),
                "created": dt(w.get("date")), "updated": dt(w.get("date")),
                "started": dt(w.get("date"), w.get("time")),
                "timeSpentSeconds": w.get("seconds", 0),
                "timeSpent": _fmt_secs(w.get("seconds", 0))}


def _fmt_secs(secs: int) -> str:
    # Jira duration string using 8h day / 5d week
    if not secs:
        return "0m"
    units = [("w", 5 * 8 * 3600), ("d", 8 * 3600), ("h", 3600), ("m", 60)]
    out = []
    for label, size in units:
        if secs >= size:
            n, secs = divmod(secs, size)
            out.append(f"{n}{label}")
    return " ".join(out) or "0m"


def project_fields(allf: dict, fields: str) -> dict:
    """Emulate Jira's `fields` query param projection."""
    if not fields:
        return allf
    want = {x.strip() for x in fields.split(",") if x.strip()}
    if not want or "*all" in want or "*navigable" in want:
        return allf
    return {k: v for k, v in allf.items() if k in want}
