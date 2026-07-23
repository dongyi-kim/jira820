"""Write (POST/PUT/DELETE) endpoints — Jira DC 8.20.8 REST v2 mutations."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()


def _store(request: Request):
    return request.app.state.store


async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@router.post("/rest/api/2/issue")
async def create_issue(request: Request):
    s = _store(request)
    body = await _json(request)
    res = s.create_issue(body.get("fields", {}))
    return JSONResponse(res, status_code=201)


@router.put("/rest/api/2/issue/{key}")
async def update_issue(key: str, request: Request):
    s = _store(request)
    body = await _json(request)
    s.update_issue(key, body.get("fields", {}))
    return Response(status_code=204)


@router.delete("/rest/api/2/issue/{key}")
async def delete_issue(key: str, request: Request):
    _store(request).delete_issue(key)
    return Response(status_code=204)


@router.post("/rest/api/2/issue/{key}/transitions")
async def do_transition(key: str, request: Request):
    s = _store(request)
    body = await _json(request)
    tid = (body.get("transition") or {}).get("id") or body.get("id")
    s.transition_issue(key, str(tid), fields=body.get("fields"), update=body.get("update"))
    return Response(status_code=204)


@router.post("/rest/api/2/issue/{key}/comment")
async def add_comment(key: str, request: Request):
    s = _store(request)
    body = await _json(request)
    obj = s.add_comment(key, body.get("body", ""))
    return JSONResponse(obj, status_code=201)


@router.put("/rest/api/2/issue/{key}/comment/{cid}")
async def edit_comment(key: str, cid: str, request: Request):
    s = _store(request)
    body = await _json(request)
    return s.update_comment(key, cid, body.get("body", ""))


@router.delete("/rest/api/2/issue/{key}/comment/{cid}")
async def remove_comment(key: str, cid: str, request: Request):
    _store(request).delete_comment(key, cid)
    return Response(status_code=204)


@router.post("/rest/api/2/issue/{key}/worklog")
async def add_worklog(key: str, request: Request):
    s = _store(request)
    body = await _json(request)
    secs = body.get("timeSpentSeconds") or 0
    obj = s.add_worklog(key, int(secs), started=body.get("started"), comment=body.get("comment", ""))
    return JSONResponse(obj, status_code=201)


@router.post("/rest/api/2/issueLink")
async def create_issue_link(request: Request):
    """이슈 링크 생성 — 실 Jira DC 형태의 바디:
    {"type": {"name": "Blocks"}, "inwardIssue": {"key": "X-1"}, "outwardIssue": {"key": "X-2"}}
    Jira 의미: outwardIssue 가 type.outward 관계의 대상이다(예: X-1 blocks X-2)."""
    s = _store(request)
    body = await _json(request)
    name = ((body.get("type") or {}).get("name") or "Relates")
    inw = ((body.get("inwardIssue") or {}).get("key") or "")
    outw = ((body.get("outwardIssue") or {}).get("key") or "")
    if not inw or not outw:
        return JSONResponse({"errorMessages": ["inwardIssue/outwardIssue required"],
                             "errors": {}}, status_code=400)
    try:
        s.add_issue_link(name, inw, outw)
    except ValueError as e:
        return JSONResponse({"errorMessages": [str(e)], "errors": {}}, status_code=400)
    return Response(status_code=201)


@router.delete("/rest/api/2/issueLink/{link_id}")
async def delete_issue_link(link_id: str, request: Request):
    _store(request).delete_issue_link(link_id)
    return Response(status_code=204)


@router.post("/rest/api/2/issue/{key}/remotelink")
async def create_remote_link(key: str, request: Request):
    """원격 링크(Confluence 문서·웹 링크) 생성/갱신 — 실 Jira 는 globalId 로 upsert 한다.
    바디: {"globalId": …, "relationship": …, "object": {"url": …, "title": …, "icon": {...}}}"""
    s = _store(request)
    body = await _json(request)
    obj = body.get("object") or {}
    url = (obj.get("url") or "").strip()
    if not url:
        return JSONResponse({"errorMessages": ["object.url required"], "errors": {}}, status_code=400)
    res = s.add_remote_link(key, url, obj.get("title") or "", body.get("relationship") or "",
                            ((obj.get("icon") or {}).get("url16x16") or ""),
                            body.get("globalId") or "")
    return JSONResponse(res, status_code=201)


@router.delete("/rest/api/2/issue/{key}/remotelink/{link_id}")
async def delete_remote_link(key: str, link_id: str, request: Request):
    _store(request).delete_remote_link(key, link_id)
    return Response(status_code=204)


@router.put("/rest/api/2/issue/{key}/assignee")
async def set_assignee(key: str, request: Request):
    s = _store(request)
    body = await _json(request)
    s.set_assignee(key, body.get("name"))
    return Response(status_code=204)
