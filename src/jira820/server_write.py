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
    s.transition_issue(key, str(tid))
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


@router.put("/rest/api/2/issue/{key}/assignee")
async def set_assignee(key: str, request: Request):
    s = _store(request)
    body = await _json(request)
    s.set_assignee(key, body.get("name"))
    return Response(status_code=204)
