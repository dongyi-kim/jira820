"""Attachment endpoints — upload/download/list/delete files & images on issues.

Images/files in a description or comment are attachments referenced from the body via Jira
wiki markup (e.g. `!diagram.png|thumbnail!` or `[^spec.pdf]`). Upload the file here, then put
that markup in the description/comment body. Uploaded files also appear in `fields.attachment`.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

router = APIRouter()


def _store(request: Request):
    return request.app.state.store


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.post("/rest/api/2/issue/{key}/attachments")
async def upload(key: str, request: Request, file: List[UploadFile] = File(...)):
    s = _store(request)
    out = []
    for f in file:
        data = await f.read()
        att = s.add_attachment(key, f.filename, f.content_type, data)
        out.append(s.serializer.attachment_obj(att, _base(request)))
    return JSONResponse(out, status_code=200)


@router.get("/rest/api/2/attachment/{aid}")
def attachment_meta(aid: str, request: Request):
    s = _store(request)
    return s.serializer.attachment_obj(s.get_attachment(aid), _base(request))


@router.delete("/rest/api/2/attachment/{aid}")
def attachment_delete(aid: str, request: Request):
    _store(request).delete_attachment(aid)
    return Response(status_code=204)


@router.get("/secure/attachment/{aid}/{filename}")
@router.get("/secure/thumbnail/{aid}/{filename}")
def attachment_content(aid: str, filename: str, request: Request):
    a = _store(request).get_attachment(aid)
    return Response(content=a["data"], media_type=a.get("mimeType") or "application/octet-stream")
