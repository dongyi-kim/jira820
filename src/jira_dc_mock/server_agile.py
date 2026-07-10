"""Agile (/rest/agile/1.0/) endpoints — boards, sprints, backlog, kanban. Read + write."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from . import agile

router = APIRouter()


def _store(request: Request):
    return request.app.state.store


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _page(values, start, mx):
    total = len(values)
    chunk = values[start:start + mx]
    return {"maxResults": mx, "startAt": start, "total": total,
            "isLast": start + len(chunk) >= total, "values": chunk}


def _issues(store, keys, base, start, mx, fields=""):
    page = keys[start:start + mx]
    return {"expand": "schema,names", "startAt": start, "maxResults": mx, "total": len(keys),
            "issues": [store.serializer.issue_res(store.issues[k], base, fields) for k in page]}


# ── boards ──
@router.get("/rest/agile/1.0/board")
def boards(request: Request, startAt: int = 0, maxResults: int = 50, type: str = ""):
    s = _store(request)
    base = _base(request)
    vals = [agile.board_json(s, bid, base) for bid in sorted(s.boards)
            if not type or s.boards[bid]["type"] == type]
    return _page(vals, startAt, maxResults)


@router.get("/rest/agile/1.0/board/{board_id}")
def board(board_id: int, request: Request):
    s = _store(request)
    if board_id not in s.boards:
        return JSONResponse({"errorMessages": [f"Board {board_id} does not exist."]}, status_code=404)
    return agile.board_json(s, board_id, _base(request))


@router.get("/rest/agile/1.0/board/{board_id}/configuration")
def board_config(board_id: int, request: Request):
    s = _store(request)
    if board_id not in s.boards:
        return JSONResponse({"errorMessages": [f"Board {board_id} does not exist."]}, status_code=404)
    return agile.board_configuration(s, board_id, _base(request))


@router.get("/rest/agile/1.0/board/{board_id}/issue")
def board_issues(board_id: int, request: Request, startAt: int = 0, maxResults: int = 50, fields: str = ""):
    s = _store(request)
    return _issues(s, agile.board_issue_keys(s, board_id), _base(request), startAt, maxResults, fields)


@router.get("/rest/agile/1.0/board/{board_id}/backlog")
def board_backlog(board_id: int, request: Request, startAt: int = 0, maxResults: int = 50, fields: str = ""):
    s = _store(request)
    return _issues(s, agile.backlog_keys(s, board_id), _base(request), startAt, maxResults, fields)


@router.get("/rest/agile/1.0/board/{board_id}/sprint")
def board_sprints(board_id: int, request: Request, startAt: int = 0, maxResults: int = 50, state: str = ""):
    s = _store(request)
    ids = agile.board_sprint_ids(s, board_id)
    if state:
        wanted = {x.strip().lower() for x in state.split(",")}
        ids = [sid for sid in ids if s.sprints[sid]["state"] in wanted]
    return _page([s.sprint_json(sid) for sid in ids], startAt, maxResults)


@router.get("/rest/agile/1.0/board/{board_id}/epic")
def board_epics(board_id: int, request: Request, startAt: int = 0, maxResults: int = 50):
    s = _store(request)
    from .serialize import iid
    vals = [{"id": int(iid(k)) % 100000, "key": k, "name": s.issues[k]["summary"],
             "summary": s.issues[k]["summary"], "done": s.issues[k]["statusCategory"] == "done"}
            for k in agile.board_epic_keys(s, board_id)]
    return _page(vals, startAt, maxResults)


@router.get("/rest/agile/1.0/epic/{key}/issue")
def epic_issues(key: str, request: Request, startAt: int = 0, maxResults: int = 50, fields: str = ""):
    s = _store(request)
    keys = sorted(s.epic_children.get(key, []))
    return _issues(s, keys, _base(request), startAt, maxResults, fields)


# ── sprints ──
@router.get("/rest/agile/1.0/sprint/{sid}")
def sprint(sid: int, request: Request):
    s = _store(request)
    if sid not in s.sprints:
        return JSONResponse({"errorMessages": [f"Sprint {sid} does not exist."]}, status_code=404)
    return s.sprint_json(sid)


@router.get("/rest/agile/1.0/sprint/{sid}/issue")
def sprint_issues(sid: int, request: Request, startAt: int = 0, maxResults: int = 50, fields: str = ""):
    s = _store(request)
    return _issues(s, agile.sprint_issue_keys(s, sid), _base(request), startAt, maxResults, fields)


async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@router.post("/rest/agile/1.0/sprint")
async def create_sprint(request: Request):
    s = _store(request)
    body = await _json(request)
    obj = s.create_sprint(int(body.get("originBoardId") or body.get("boardId")),
                          body.get("name", ""), body.get("goal", ""))
    return JSONResponse(obj, status_code=201)


@router.put("/rest/agile/1.0/sprint/{sid}")
async def update_sprint(sid: int, request: Request):
    s = _store(request)
    body = await _json(request)
    return s.update_sprint(sid, body)


@router.post("/rest/agile/1.0/sprint/{sid}/issue")
async def move_to_sprint(sid: int, request: Request):
    s = _store(request)
    body = await _json(request)
    s.move_issues_to_sprint(sid, body.get("issues", []))
    return Response(status_code=204)


@router.post("/rest/agile/1.0/backlog/issue")
async def move_to_backlog(request: Request):
    s = _store(request)
    body = await _json(request)
    s.move_issues_to_backlog(body.get("issues", []))
    return Response(status_code=204)
