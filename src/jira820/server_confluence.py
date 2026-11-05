"""Published Confluence DC 9.2.4 REST subset for standalone and embedded mocks."""
from __future__ import annotations

import copy
import html
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .confluence import ConfluenceError, ConfluenceState, _content_payload, _id


def install_confluence(app, *, reset=True):
    """Install once; explicit reinstallation resets fixture state for a new injected corpus."""
    if not reset and getattr(app.state, "confluence", None) is not None:
        return app.state.confluence
    app.state.confluence = ConfluenceState(app.state.store)
    if getattr(app.state, "confluence_routes_installed", False):
        return app.state.confluence
    app.state.confluence_routes_installed = True
    router = APIRouter()

    def state():
        return app.state.confluence

    @app.exception_handler(ConfluenceError)
    async def error(_request, exc):
        return JSONResponse({"statusCode": exc.status, "message": exc.message}, status_code=exc.status)

    def listing(request, rows, start, limit):
        if start < 0 or not 1 <= limit <= 100:
            raise ConfluenceError(400, "Invalid pagination")
        result = rows[start:start + limit]
        links = {"base": str(request.base_url).rstrip("/"), "context": ""}
        if start + len(result) < len(rows):
            links["next"] = request.url.path + "?" + request.url.include_query_params(start=start + len(result), limit=limit).query
        return {"results": result, "start": start, "limit": limit, "size": len(result), "totalSize": len(rows), "_links": links}

    def serialize(request, row, expand=""):
        return state().content(row, str(request.base_url).rstrip("/"), expand)

    def rows(kind="page", status="current"):
        state().seed()
        with state().lock:
            return [copy.deepcopy(row) for row in state().pages.values() if row["status"] == status
                    and row["type"] == kind and state()._allowed(row) and state()._container_current(row)]

    async def json_value(request):
        try:
            data = await request.json()
        except Exception as exc:
            raise ConfluenceError(400, "Expected a JSON request body") from exc
        return data

    async def payload(request):
        return _content_payload(await json_value(request))

    @router.get("/rest/api/search")
    @router.get("/rest/api/content/search")
    def search(request: Request, cql: str = "", start: int = 0, limit: int = 25, expand: str = ""):
        from .cql import search_terms
        from .serialize import _conf_excerpt
        results = []
        for row in state().search(cql):
            # Legacy unified-search consumers expect breadcrumbs by default; direct
            # content endpoints still project ancestors only when explicitly expanded.
            projection = expand + ",ancestors" if request.url.path == "/rest/api/search" else expand
            content = serialize(request, row, projection)
            if request.url.path.endswith("/content/search"):
                results.append(content)
                continue
            text = html.unescape(re.sub(r"<[^>]*>", " ", row["body"]["storage"]["value"]))
            excerpt = _conf_excerpt({"body": re.sub(r"\s+", " ", text).strip(), "title": row["title"]}, search_terms(cql))
            results.append({"content": content, "title": row["title"], "excerpt": excerpt,
                "url": content["_links"]["webui"], "lastModified": row["version"]["when"],
                "entityType": "content", "iconCssClass": "aui-iconfont-page-default"})
        return {**listing(request, results, start, limit), "cqlQuery": cql, "searchDuration": 1}

    @router.get("/rest/api/user")
    def user(username: str):
        value = state().store.users.get(username)
        if not value:
            raise ConfluenceError(404, "User not found")
        return {"type": "known", "username": username, "userKey": "conf-user-" + username,
                "displayName": value.get("displayName") or value.get("name") or username}

    @router.get("/rest/api/space")
    def spaces(request: Request, start: int = 0, limit: int = 50):
        values = {row["space"]["key"]: row["space"] for row in rows()}
        return listing(request, [values[key] for key in sorted(values)], start, limit)

    @router.get("/rest/api/space/{space}/content/page")
    def roots(space: str, request: Request, depth: str = "all", start: int = 0, limit: int = 50, expand: str = ""):
        if depth not in {"all", "root"}:
            raise ConfluenceError(400, "depth must be all or root")
        values = [row for row in rows() if row["space"]["key"] == space and (depth != "root" or not row["parent"])]
        values.sort(key=lambda r: (r["position"], r["title"], r["id"]))
        return listing(request, [serialize(request, row, expand) for row in values], start, limit)

    @router.get("/rest/api/space/{space}")
    def space_detail(space: str, request: Request, expand: str = ""):
        values = [row for row in rows() if row['space']['key'] == space and not row['parent']]
        if not values:
            raise ConfluenceError(404, 'Space not found')
        # The shared fixture's first root is its configured homepage; restricted
        # pages never become visible through this projection.
        values.sort(key=lambda row: (row['position'], row['id']))
        result = dict(values[0]['space'])
        if 'homepage' in expand.split(','):
            result['homepage'] = serialize(request, values[0], 'space,version')
        return result

    @router.get("/rest/api/content")
    def content_list(request: Request, spaceKey: str = "", title: str = "", type: str = "page",
                     status: str = "current", start: int = 0, limit: int = 50, expand: str = ""):
        values = [row for row in rows(type, status) if (not spaceKey or row["space"]["key"] == spaceKey)
                  and (not title or row["title"] == title)]
        return listing(request, [serialize(request, row, expand) for row in values], start, limit)

    @router.post("/rest/api/content")
    async def create(request: Request):
        value = await payload(request)
        with state().lock:
            state().writable()
            state().seed()
            kind = value.get("type", "page")
            if kind == "page" and not str(value.get("title", "")).strip():
                raise ConfluenceError(400, "Page title is required")
            if value.get("status", "current") != "current":
                raise ConfluenceError(400, "Only published content can be created")
            parent = str((value.get("ancestors") or [{}])[-1].get("id") or "")
            container = str((value.get("container") or {}).get("id") or "")
            if kind == "comment" and not container:
                raise ConfluenceError(400, "Comment container is required")
            if parent or container:
                target = state().get(_id(parent or container))
                if target["type"] != "page":
                    raise ConfluenceError(400, "Parent/container must be a page")
                if (value.get("space") or {}).get("key", target["space"]["key"]) != target["space"]["key"]:
                    raise ConfluenceError(400, "Parent must be in the same Space")
            # Authorship and publish time are server-owned. Direct State fixture seeds may set them.
            if "version" in value:
                value["version"] = {key: item for key, item in value["version"].items() if key not in {"when", "by"}}
            row = state().create(value)
            state().changed()
            return serialize(request, row, "body.storage")

    @router.get("/rest/api/content/{cid}")
    def get(cid: str, request: Request, expand: str = "", status: str = "current", version: int = None):
        return serialize(request, state().get(cid, status=status, version=version), expand)

    @router.put("/rest/api/content/{cid}")
    async def update(cid: str, request: Request):
        return serialize(request, state().update(cid, await payload(request)), "body.storage")

    @router.delete("/rest/api/content/{cid}")
    def delete(cid: str, status: str = "current"):
        with state().lock:
            state().writable()
            if status != "current":
                raise ConfluenceError(400, "Permanent purge is not modeled")
            row = state().get(cid)
            if row["type"] == "page" and any(r["parent"] == cid and r["status"] == "current" for r in state().pages.values()):
                raise ConfluenceError(409, "Move or trash child pages first")
            row["status"] = "trashed"
            state().changed()
        return Response(status_code=204)

    @router.get("/rest/api/content/{cid}/history")
    def history(cid: str):
        row = state().get(cid)
        return {**row["history"], "latest": True, "lastUpdated": row["version"],
                "previousVersion": state().versions[cid].get(row["version"]["number"] - 1, {}).get("version")}

    @router.get("/rest/api/content/{cid}/child/{kind}")
    def children(cid: str, kind: str, request: Request, start: int = 0, limit: int = 50, expand: str = ""):
        state().get(cid)
        values = [row for row in rows(kind) if (row["parent"] == cid if kind == "page" else row.get("container", {}).get("id") == cid)]
        values.sort(key=lambda r: (r["position"], r["title"], r["id"]))
        return listing(request, [serialize(request, row, expand) for row in values], start, limit)

    @router.post("/rest/api/content/{cid}/child/attachment")
    async def attach(cid: str, request: Request, allowDuplicated: bool = False):
        state().writable()
        state().get(cid)
        form = await request.form()
        upload = form.get("file")
        if not getattr(upload, "filename", None):
            raise ConfluenceError(400, "file upload is required")
        data = await upload.read()
        with state().lock:
            existing = next((r for r in rows("attachment") if r["container"].get("id") == cid and r["title"] == upload.filename), None)
            if existing and not allowDuplicated:
                raise ConfluenceError(409, "Attachment already exists")
            row = state().create({"type": "attachment", "title": upload.filename, "container": {"id": cid}})
            state().files[row["id"]] = (data, upload.content_type or "application/octet-stream")
            state().file_versions[row["id"]] = {1: state().files[row["id"]]}
            state().changed()
        return {"results": [serialize(request, row)]}

    @router.post("/rest/api/content/{cid}/child/attachment/{aid}/data")
    async def update_attachment(cid: str, aid: str, request: Request):
        state().writable()
        state().get(cid)
        form = await request.form()
        upload = form.get("file")
        if not getattr(upload, "filename", None):
            raise ConfluenceError(400, "file upload is required")
        data = await upload.read()
        with state().lock:
            row = state().get(aid)
            if row["type"] != "attachment" or row.get("container", {}).get("id") != cid:
                raise ConfluenceError(404, "Attachment is not in this page")
            version = row["version"]["number"] + 1
            row = copy.deepcopy(row)
            row["version"] = {"number": version, "when": state().now(), "by": {"username": state().store.config.current_user}}
            state().pages[aid] = row
            state().versions[aid][version] = copy.deepcopy(row)
            state().files[aid] = (data, upload.content_type or "application/octet-stream")
            state().file_versions.setdefault(aid, {})[version] = state().files[aid]
            state().changed()
        return serialize(request, row)

    @router.delete("/rest/api/content/{cid}/child/attachment/{aid}")
    def delete_attachment(cid: str, aid: str):
        state().get(cid)
        row = state().get(aid)
        if row["type"] != "attachment" or row.get("container", {}).get("id") != cid:
            raise ConfluenceError(404, "Attachment is not in this page")
        return delete(aid)

    @router.get("/download/attachments/{cid}/{filename}")
    def download(cid: str, filename: str, version: int = None):
        state().get(cid)
        row = next((r for r in rows("attachment") if r.get("container", {}).get("id") == cid and r["title"] == filename), None)
        if row is None:
            raise ConfluenceError(404, "Attachment not found")
        version = version if version is not None else row["version"]["number"]
        state().get(row["id"], version=version)
        value = state().file_versions.get(row["id"], {}).get(version)
        if value is None and version == row["version"]["number"]:
            value = state().files.get(row["id"])
        if value is None:
            raise ConfluenceError(404, "Attachment version not found")
        return Response(value[0], media_type=value[1])

    @router.get("/rest/api/content/{cid}/label")
    def labels(cid: str, request: Request, start: int = 0, limit: int = 50):
        state().get(cid)
        return listing(request, [{"prefix": "global", "name": name} for name in sorted(state().labels.get(cid, set()))], start, limit)

    @router.post("/rest/api/content/{cid}/label")
    async def add_labels(cid: str, request: Request):
        state().writable()
        state().get(cid)
        value = await json_value(request)
        if not isinstance(value, list) or any(not isinstance(r, dict) or not isinstance(r.get("name"), str) or not r["name"].strip() for r in value):
            raise ConfluenceError(400, "Labels must contain nonempty names")
        with state().lock:
            state().labels.setdefault(cid, set()).update(row["name"] for row in value)
            state().changed()
        return labels(cid, request)

    @router.delete("/rest/api/content/{cid}/label")
    def delete_label(cid: str, name: str):
        state().writable()
        state().get(cid)
        with state().lock:
            state().labels.setdefault(cid, set()).discard(name)
            state().changed()
        return Response(status_code=204)

    @router.get("/rest/api/content/{cid}/restriction/byOperation")
    def restrictions(cid: str):
        state().get(cid)
        return copy.deepcopy(state().restrictions.get(cid) or {
            op: {"operation": op, "restrictions": {"user": {"results": [], "size": 0}, "group": {"results": [], "size": 0}}}
            for op in ("read", "update")})

    @router.put("/rest/api/content/{cid}/restriction")
    async def set_restrictions(cid: str, request: Request):
        state().writable()
        changes = await json_value(request)
        if not isinstance(changes, list) or any(not isinstance(row, dict) or row.get("operation") not in {"read", "update"} for row in changes):
            raise ConfluenceError(400, "Specify read/update restrictions")
        for row in changes:
            subjects = row.get("restrictions", {})
            if not isinstance(subjects, dict) or any(not isinstance(subjects.get(kind, []), list) or
                    any(not isinstance(item, dict) for item in subjects.get(kind, [])) for kind in ("user", "group")):
                raise ConfluenceError(400, "Restriction subjects must be lists of objects")
        with state().lock:
            value = restrictions(cid)
            for row in changes:
                subjects = row.get("restrictions") or {}
                value[row["operation"]] = {"operation": row["operation"], "restrictions": {
                    kind: {"results": subjects.get(kind, []), "size": len(subjects.get(kind, []))} for kind in ("user", "group")}}
            state().restrictions[cid] = value
            state().changed()
        return value

    app.include_router(router)
    return app.state.confluence
