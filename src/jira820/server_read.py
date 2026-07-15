"""Read (GET) endpoints — Jira DC 8.20.8 REST v2 + metadata for building clients."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from . import atom
from . import jql as jqlmod

router = APIRouter()


def _store(request: Request):
    return request.app.state.store


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _avatars(owner):
    return {"48x48": f"/secure/useravatar?ownerId={owner}&avatarId=10122",
            "32x32": f"/secure/useravatar?size=medium&ownerId={owner}&avatarId=10122",
            "24x24": f"/secure/useravatar?size=small&ownerId={owner}&avatarId=10122",
            "16x16": f"/secure/useravatar?size=xsmall&ownerId={owner}&avatarId=10122"}


@router.get("/rest/api/2/serverInfo")
def server_info(request: Request):
    s = _store(request)
    ver = s.config.server_version
    nums = [int(x) for x in re.findall(r"\d+", ver)][:3] or [8, 20, 8]
    return {"baseUrl": _base(request), "version": ver, "versionNumbers": nums,
            "deploymentType": "Server", "buildNumber": 820008,
            "buildDate": "2022-05-31T00:00:00.000+0000", "databaseBuildNumber": 820008,
            "serverTime": "2026-01-01T09:00:00.000+0000", "serverTitle": "jira-dc-8.20-mock"}


@router.get("/rest/api/2/myself")
def myself(request: Request):
    return {"self": f"{_base(request)}/rest/api/2/user?username=admin",
            "key": "admin", "name": "admin", "emailAddress": "admin@example.com",
            "avatarUrls": _avatars("admin"), "displayName": "Administrator",
            "active": True, "deleted": False, "timeZone": "UTC", "locale": "en_US"}


@router.get("/rest/api/2/user")
def user(request: Request, username: str = "", key: str = ""):
    s = _store(request)
    uid = username or key
    if uid in s.users:
        obj = dict(s.serializer.user_obj(uid))
        obj["self"] = f"{_base(request)}/rest/api/2/user?username={uid}"
        obj["deleted"] = False
        return obj
    return {"self": f"{_base(request)}/rest/api/2/user?username={uid}", "name": uid, "key": uid,
            "avatarUrls": _avatars(uid), "displayName": uid, "active": True, "deleted": False}


@router.get("/rest/api/2/field")
def fields(request: Request):
    s = _store(request)

    def sysf(fid, name, stype, clause=None):
        return {"id": fid, "name": name, "custom": False, "orderable": True, "navigable": True,
                "searchable": True, "clauseNames": clause or [fid], "schema": {"type": stype, "system": fid}}

    def cf(fid, name, stype, custom_key, cid):
        return {"id": fid, "name": name, "custom": True, "orderable": True, "navigable": True,
                "searchable": True, "clauseNames": [f"cf[{cid}]", name],
                "schema": {"type": stype, "custom": custom_key, "customId": cid}}

    std = [
        sysf("summary", "Summary", "string"),
        sysf("status", "Status", "status"),
        sysf("issuetype", "Issue Type", "issuetype", ["issuetype", "type"]),
        sysf("assignee", "Assignee", "user"),
        sysf("reporter", "Reporter", "user"),
        sysf("components", "Component/s", "array", ["component"]),
        sysf("labels", "Labels", "array"),
        sysf("created", "Created", "datetime", ["created", "createdDate"]),
        sysf("updated", "Updated", "datetime", ["updated", "updatedDate"]),
        sysf("resolutiondate", "Resolved", "datetime", ["resolved", "resolutiondate"]),
        sysf("duedate", "Due Date", "date", ["due", "duedate"]),
        sysf("fixVersions", "Fix Version/s", "array", ["fixVersion"]),
    ]
    custom = [
        cf(s.config.sp_field, "Story Points", "number",
           "com.atlassian.jira.plugin.system.customfieldtypes:float", 10004),
        cf(s.config.epic_link_field, "Epic Link", "any",
           "com.pyxis.greenhopper.jira:gh-epic-link", 10008),
        cf(s.config.sprint_field, "Sprint", "array",
           "com.pyxis.greenhopper.jira:gh-sprint", 10007),
        cf("customfield_10011", "Epic Name", "string",
           "com.pyxis.greenhopper.jira:gh-epic-label", 10011),
    ]
    return std + custom


def _statuses(request):
    s = _store(request)
    return [s.serializer.status_obj(name) for name, _c, _sid in s.config.statuses]


@router.get("/rest/api/2/status")
def statuses(request: Request):
    return _statuses(request)


@router.get("/rest/api/2/issuetype")
def issuetypes(request: Request):
    s = _store(request)
    return [s.serializer.issuetype_obj(name) for name, _t in s.config.issue_types]


@router.get("/rest/api/2/priority")
def priorities():
    return [{"id": "3", "name": "Medium", "self": "/rest/api/2/priority/3",
             "iconUrl": "/images/icons/priorities/medium.svg"}]


@router.get("/rest/api/2/resolution")
def resolutions():
    return [{"id": "1", "name": "Done", "description": "Work has been completed."}]


def _project_obj(request, full=False):
    s = _store(request)
    base = _base(request)
    comps = [{"self": f"{base}/rest/api/2/component/{100 + i}", "id": str(100 + i),
              "name": m, "isAssigneeTypeValid": False} for i, m in enumerate(s.config.components)]
    obj = {"expand": "description,lead,url,projectKeys",
           "self": f"{base}/rest/api/2/project/{s.config.project_key}", "id": "10000",
           "key": s.config.project_key, "name": s.config.project_name,
           "avatarUrls": _avatars(s.config.project_key), "projectTypeKey": "software"}
    if full:
        obj["components"] = comps
        obj["issueTypes"] = [s.serializer.issuetype_obj(n) for n, _t in s.config.issue_types]
        obj["versions"] = [s.serializer.version_obj(v) for v in s.versions]
        obj["assigneeType"] = "UNASSIGNED"
    return obj, comps


@router.get("/rest/api/2/project")
def projects(request: Request):
    obj, _ = _project_obj(request)
    return [obj]


@router.get("/rest/api/2/project/{key}")
def project(key: str, request: Request):
    obj, _ = _project_obj(request, full=True)
    return obj


@router.get("/rest/api/2/project/{key}/components")
def components(key: str, request: Request):
    _, comps = _project_obj(request)
    return comps


@router.get("/rest/api/2/project/{key}/versions")
def versions(key: str, request: Request):
    s = _store(request)
    return [s.serializer.version_obj(v) for v in s.versions]


@router.get("/rest/api/2/project/{key}/statuses")
def project_statuses(key: str, request: Request):
    s = _store(request)
    sts = _statuses(request)
    return [{"id": t["id"], "name": t["name"], "subtask": t["subtask"], "statuses": sts}
            for t in [s.serializer.issuetype_obj(n) for n, _x in s.config.issue_types]]


# createmeta MUST be declared before /issue/{key}
@router.get("/rest/api/2/issue/createmeta")
def createmeta(request: Request):
    s = _store(request)
    fields_meta = {
        "summary": {"required": True, "name": "Summary", "schema": {"type": "string"}},
        "issuetype": {"required": True, "name": "Issue Type", "schema": {"type": "issuetype"}},
        "assignee": {"required": False, "name": "Assignee", "schema": {"type": "user"}},
        "description": {"required": False, "name": "Description", "schema": {"type": "string"}},
        "labels": {"required": False, "name": "Labels", "schema": {"type": "array"}},
        "duedate": {"required": False, "name": "Due Date", "schema": {"type": "date"}},
        s.config.sp_field: {"required": False, "name": "Story Points", "schema": {"type": "number"}},
    }
    itypes = [dict(s.serializer.issuetype_obj(n), fields=fields_meta) for n, _t in s.config.issue_types]
    return {"expand": "projects", "projects": [{
        "self": f"{_base(request)}/rest/api/2/project/{s.config.project_key}", "id": "10000",
        "key": s.config.project_key, "name": s.config.project_name, "issuetypes": itypes}]}


@router.get("/rest/api/2/issue/{key}/editmeta")
def editmeta(key: str, request: Request):
    s = _store(request)
    s.get_issue(key)
    return {"fields": {
        "summary": {"required": True, "name": "Summary", "schema": {"type": "string"}, "operations": ["set"]},
        "description": {"required": False, "name": "Description", "schema": {"type": "string"}, "operations": ["set"]},
        "assignee": {"required": False, "name": "Assignee", "schema": {"type": "user"}, "operations": ["set"]},
        "labels": {"required": False, "name": "Labels", "schema": {"type": "array"}, "operations": ["add", "set", "remove"]},
        "duedate": {"required": False, "name": "Due Date", "schema": {"type": "date"}, "operations": ["set"]},
        s.config.sp_field: {"required": False, "name": "Story Points", "schema": {"type": "number"}, "operations": ["set"]},
    }}


@router.get("/rest/api/2/search")
def search(request: Request, jql: str = Query(""), startAt: int = 0,
           maxResults: int = 50, fields: str = ""):
    s = _store(request)
    keys = jqlmod.filter_keys(s, jql)
    total = len(keys)
    page = keys[startAt:startAt + maxResults]
    base = _base(request)
    return {"expand": "schema,names", "startAt": startAt, "maxResults": maxResults, "total": total,
            "issues": [s.serializer.issue_res(s.issues[k], base, fields) for k in page]}


@router.get("/rest/api/2/issue/{key}")
def issue(key: str, request: Request, fields: str = "", expand: str = ""):
    s = _store(request)
    it = s.issues.get(key)
    if not it:
        return JSONResponse({"errorMessages": [f"Issue Does Not Exist: {key}"], "errors": {}}, status_code=404)
    return s.serializer.issue_res(it, _base(request), fields, expand)


@router.get("/rest/api/2/issue/{key}/comment")
def comments(key: str, request: Request, maxResults: int = 50, startAt: int = 0, orderBy: str = ""):
    s = _store(request)
    cs = s.jira_comments(key)
    return {"startAt": startAt, "maxResults": maxResults, "total": len(cs),
            "comments": cs[startAt:startAt + maxResults]}


@router.get("/rest/api/2/issue/{key}/worklog")
def worklog(key: str, request: Request):
    s = _store(request)
    it = s.get_issue(key)
    logs = [s.serializer.worklog_obj(key, i, w) for i, w in enumerate(it["worklog"])]
    return {"startAt": 0, "maxResults": len(logs), "total": len(logs), "worklogs": logs}


@router.get("/rest/api/2/issue/{key}/transitions")
def transitions(key: str, request: Request):
    s = _store(request)
    it = s.get_issue(key)
    return {"expand": "transitions",
            "transitions": s.workflow.available_transitions(s.serializer, it["statusName"])}


@router.get("/activity")
def activity(request: Request, streams: str = "", maxResults: int = 20):
    s = _store(request)
    m = re.search(r"user\s+IS\s+(\S+)", streams, re.I)
    user = m.group(1) if m else ""
    events = s.activity.get(user, [])
    dn = (s.users.get(user) or {}).get("displayName", user)
    xml = atom.feed(_base(request), user, events, maxResults, display_name=dn)
    return Response(content=xml, media_type="application/atom+xml; charset=utf-8")


@router.get("/rest/api/content/search")
def content_search(request: Request, cql: str = "", limit: int = 25, expand: str = ""):
    """Confluence 콘텐츠 검색 — CQL(space/title/text/siteSearch/contributor/lastmodified) 지원."""
    from . import cql as cqlmod
    from .serialize import conf_content_obj
    s = _store(request)
    base = _base(request)
    pages = cqlmod.search_pages(s, cql, limit)
    results = [conf_content_obj(p, base) for p in pages]
    return {"results": results, "start": 0, "limit": limit, "size": len(results),
            "_links": {"base": base, "context": ""}}


@router.get("/rest/api/search")
def cql_search(request: Request, cql: str = "", limit: int = 25, start: int = 0, expand: str = ""):
    """Confluence 통합 검색 — excerpt(스니펫) 포함 결과. DC 9.x /rest/api/search 형태."""
    from . import cql as cqlmod
    from .serialize import conf_search_result
    s = _store(request)
    base = _base(request)
    pages = cqlmod.search_pages(s, cql, start + limit)
    page_slice = pages[start:start + limit]
    results = [conf_search_result(p, base) for p in page_slice]
    return {"results": results, "start": start, "limit": limit, "size": len(results),
            "totalSize": len(pages), "cqlQuery": cql, "searchDuration": 1,
            "_links": {"base": base, "context": ""}}
