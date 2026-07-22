"""Serialize canonical internal objects into Jira Data Center 8.20.8 REST JSON.

Kept faithful to real DC response shapes (statusCategory keys new/indeterminate/done,
custom-field indirection for Story Points / Epic Link / Sprint, avatar URL patterns, etc.).
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Optional

from .render import render_wiki

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
        self.prio_map = {name: pid for name, pid in c.priorities}
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

    def priority_obj(self, name=None) -> Optional[dict]:
        """우선순위 객체. name 이 없으면 config.default_priority, 그것도 없으면 목록 가운데.

        목록에 없는 이름도 그대로 돌려준다(id 는 "0") — 인스턴스가 임의 스킴을 쓸 수 있고,
        mock 이 이름을 검열할 이유가 없다.
        """
        if not self.c.priorities:
            return None
        if not name:
            name = self.c.default_priority or self.c.priorities[len(self.c.priorities) // 2][0]
        pid = self.prio_map.get(name, "0")
        return {"self": f"/rest/api/2/priority/{pid}", "id": pid, "name": name,
                "iconUrl": f"/images/icons/priorities/{str(name).lower().replace(' ', '')}.svg"}

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
            "priority": self.priority_obj(it.get("priority")),
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
            "project": self.project_ref(it.get("project")),
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
        f["issuelinks"] = self.issuelinks(it)
        return f

    # Issue links — Jira DC 형태: {id, type:{id,name,inward,outward}, inwardIssue|outwardIssue}
    # store 의 링크 항목: {"type": "Relates", "dir": "outward"|"inward", "key": "<상대 키>"}
    LINK_TYPES = {
        "Relates":    ("relates to", "relates to"),
        "Blocks":     ("is blocked by", "blocks"),
        "Duplicate":  ("is duplicated by", "duplicates"),
        "Cloners":    ("is cloned by", "clones"),
    }

    def issuelinks(self, it) -> list:
        out = []
        for i, ln in enumerate(it.get("links", [])):
            other = ln.get("key")
            if not other or other not in self.store.issues:
                continue
            o = self.store.issues[other]
            name = ln.get("type", "Relates")
            inward, outward = self.LINK_TYPES.get(name, self.LINK_TYPES["Relates"])
            ref = {"id": iid(other), "key": other, "fields": {
                "summary": o["summary"], "status": self.status_obj(o["statusName"]),
                "issuetype": self.issuetype_obj(o["type"])}}
            side = "outwardIssue" if ln.get("dir", "outward") == "outward" else "inwardIssue"
            out.append({"id": str(9000 + i),
                        "type": {"id": str(10000 + sorted(self.LINK_TYPES).index(name)),
                                 "name": name, "inward": inward, "outward": outward},
                        side: ref})
        return out

    def project_ref(self, key=None) -> dict:
        """이슈별 프로젝트 참조 — 멀티프로젝트(주입) 지원. key 없으면 config 기본 프로젝트."""
        k = key or self.c.project_key
        name = self.c.project_name if k == self.c.project_key else k
        pid = str(int(hashlib.md5(("proj:" + k).encode()).hexdigest()[:6], 16))
        return {"self": f"/rest/api/2/project/{k}", "id": pid,
                "key": k, "name": name, "projectTypeKey": "software"}

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
        if expand and "renderedFields" in expand:
            # 실 Jira DC 처럼 wiki 소스를 서버 렌더한 HTML 제공 (table/image/code/quote/panel/맨션 등)
            res["renderedFields"] = {"description": render_wiki(it.get("description"), self._mention_name)}
        return res

    def _mention_name(self, uid):
        u = self.store.users.get(uid)
        return u["displayName"] if u else uid

    def comment_obj(self, key: str, idx: int, c) -> dict:
        au = self.user_obj(c["author"])
        when = dt(c["created"], c.get("tcreated"))
        upd = dt(c.get("updated") or c["created"], c.get("tupdated") or c.get("tcreated"))
        cid = c.get("id") or f"{10000 + idx}"
        body = c["body"] if "body" in c else f"({c['kind']}) {c['text']}"
        return {"self": f"/rest/api/2/issue/{key}/comment/{cid}", "id": str(cid),
                "author": au, "updateAuthor": au, "body": body,
                "renderedBody": render_wiki(body, self._mention_name),   # 렌더된 HTML(맨션 이름 해석)
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


# ── Confluence (linked DC) 검색 결과 직렬화 ──────────────────────────────
def _conf_slug(title):
    return (title or "").replace(" ", "+")


def _conf_webui(page):
    return "/spaces/%s/pages/%s/%s" % (
        page.get("space", ""), page.get("id", ""), _conf_slug(page.get("title", "")))


_HL_A, _HL_B = "@@@hl@@@", "@@@endhl@@@"     # Confluence DC 하이라이트 마커


def _conf_excerpt(page, terms=None):
    """검색 스니펫. term 이 있으면 **매칭 부분 주변**을 잘라 마커로 감싼다(실 Confluence 동작).
    term 이 없으면(둘러보기 등) 앞부분을 준다."""
    body = (page.get("body") or page.get("title") or "").strip()
    for t in (terms or []):
        i = body.lower().find(t.lower())
        if i < 0:
            continue
        start = max(0, i - 60)
        seg = body[start:i + len(t) + 100]
        hit = seg.lower().find(t.lower())          # 잘린 구간 내 위치
        seg = seg[:hit] + _HL_A + seg[hit:hit + len(t)] + _HL_B + seg[hit + len(t):]
        return ("…" if start > 0 else "") + seg + ("…" if i + len(t) + 100 < len(body) else "")
    return body[:180]


# 스페이스 키 → 표시 이름(경로 루트). 주입 world 가 space_names 를 안 주면 키 그대로.
_CONF_SPACE_NAMES = {"DL": "데이터플랫폼", "PMO": "PMO", "ARCH": "아키텍처", "OPS": "운영"}


def _space_name(page, sp):
    return page.get("spaceName") or _CONF_SPACE_NAMES.get(sp, sp)


def conf_content_obj(page, base_url=""):
    """Confluence /rest/api/content 형태의 content object (search 결과에도 중첩됨).

    ancestors: 상위 폴더 페이지들 [최상위 … 직계부모] 순(실 Confluence 형태).
    문서의 'ancestors'(폴더 제목 리스트)를 페이지 객체로 부풀린다.
    """
    sp = str(page.get("space") or "")
    pid = str(page.get("id", ""))
    anc = []
    for i, title in enumerate(page.get("ancestors") or []):
        anc.append({"id": f"{pid}a{i}", "type": "page", "title": title,
                    "_links": {"webui": _conf_webui(page)}})
    return {
        "id": pid, "type": "page", "status": "current",
        "title": page.get("title", ""),
        "space": {"key": sp, "name": _space_name(page, sp), "type": "global"},
        "ancestors": anc,
        "version": {"when": dt(page.get("date"), page.get("time")), "number": 1},
        "_links": {"webui": _conf_webui(page),
                   "self": (base_url + "/rest/api/content/" + pid) if base_url else "/rest/api/content/" + pid},
    }


def conf_search_result(page, base_url="", terms=None):
    """Confluence /rest/api/search 결과 아이템 (excerpt 포함) — DC 9.x 형태."""
    return {
        "content": conf_content_obj(page, base_url),
        "title": page.get("title", ""),
        "excerpt": _conf_excerpt(page, terms),
        "url": _conf_webui(page),
        "entityType": "content",
        "iconCssClass": "aui-iconfont-page-default",
        "lastModified": dt(page.get("date"), page.get("time")),
    }
